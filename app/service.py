"""What the app does, independent of HTTP or MCP: sync the day from Bee,
run the evening practice, keep promises, and report progress."""

from __future__ import annotations

import asyncio
import itertools
import json
import queue
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from . import bee, config, digest, llm
from .store import Store

RESULTS = ("remembered", "hint", "forgot")
# Days until a card comes back, by Leitner box after a correct answer.
INTERVALS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}
MAX_REVIEWS_PER_NIGHT = 2  # older cards mixed into tonight's practice


def today() -> str:
    return datetime.now(config.TZ).date().isoformat()


def _plus(day: str, n: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def clock(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, config.TZ).strftime("%H:%M") if ms else ""


class Live:
    """What Bee is hearing right now, fanned out to every open page (SSE).
    Each line goes out at once, and again with its English when that's ready."""

    def __init__(self, translate=None, size: int = 60, on_line=None, paused_check=None):
        self.recent: deque[dict] = deque(maxlen=size)
        self.on_line = on_line  # called with each new line (real-time reminders listen here)
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.connected = False
        self.last_event_ms: int | None = None
        self._ids = itertools.count(1)
        self._translate = translate
        self._pending: queue.Queue = queue.Queue()
        self._paused_check = paused_check  # callable(ms) -> bool; None means never paused
        if translate:
            threading.Thread(target=self._translator, name="live-translate", daemon=True).start()

    def _send(self, item: dict) -> None:
        if not self.loop:
            return
        for q in list(self.subscribers):
            self.loop.call_soon_threadsafe(q.put_nowait, item)

    def line(self, speaker: str, text: str, at: int | None = None, demo: bool = False,
             conversation=None, index: int | None = None) -> dict:
        now_ms = at or int(time.time() * 1000)
        if self._paused_check and self._paused_check(now_ms):
            paused_item = {"type": "paused", "at": now_ms}
            self._send(paused_item)
            return paused_item
        item = {"type": "line", "id": next(self._ids), "speaker": speaker, "text": text,
                "at": now_ms, "en": None, "demo": demo,
                "conversation": conversation, "index": index}
        self.recent.append(item)
        self.last_event_ms = int(time.time() * 1000)
        self._send(item)
        if self._translate:
            self._pending.put(item)
        if self.on_line:
            self.on_line(item)
        return item

    def event(self, item: dict) -> None:
        """Anything else the family page should see live (a reminder that was just set)."""
        self.recent.append(item)
        self._send(item)

    def _translator(self) -> None:
        while True:
            batch = [self._pending.get()]
            time.sleep(1.0)  # gather a few lines into one call
            while not self._pending.empty() and len(batch) < 12:
                batch.append(self._pending.get_nowait())
            try:
                out = self._translate([b["text"] for b in batch])
            except Exception:  # live English is a bonus; never break the feed
                continue
            for item, line in zip(batch, out):
                line = line if isinstance(line, dict) else {"en": line}
                if line.get("en"):
                    fixed = line.get("parent") if line.get("parent") and line["parent"] != item["text"] else None
                    item |= {"en": line["en"], "fixed": fixed, "background": bool(line.get("background"))}
                    self._send({"type": "translation", "id": item["id"], "en": line["en"], "fixed": fixed,
                                "background": item["background"]})


def _fixed(conv: dict, i: int) -> str:
    """Line i as the AI rebuilt it in the parent's language ("" if there's none)."""
    fixed = conv.get("lines_parent") or []
    return (fixed[i] if i < len(fixed) else "") or ""


class MemoryLane:
    def __init__(self, store: Store | None = None, source=None, background: bool = False):
        self.store = store or Store()
        self.bee = source or bee.source()
        self.live = Live(self._live_translator(), on_line=self._heard, paused_check=self.paused_at)
        self.reminders = LiveReminders(self) if config.LIVE_REMINDERS else None
        self.sync_lock = threading.Lock()
        self.job = {"running": False, "total": 0, "done": 0, "current": None, "report": None}
        self.last_sync: dict | None = None
        self._stop = threading.Event()
        self._resync = threading.Event()
        if background:
            self.start_background()

    def _live_translator(self):
        if not config.LIVE_TRANSLATE:
            return None
        if self.bee.mode == "demo" and llm.engine() == "mock":
            known = digest.sample_translations()
            return lambda texts: [known.get(t, "") for t in texts]
        if llm.engine() in ("mock", "manual"):
            return None
        return lambda texts: digest.translate_full(texts, effort="low")  # speed matters more than polish here

    # ---- status ----
    def status(self) -> dict:
        ps = self.pause_state()
        return {
            "bee": self.bee.mode,
            "ai": llm.engine(),
            "model": llm.model() if llm.engine() != "mock" else None,
            "parent": config.PARENT_NAME,
            "parent_en": config.PARENT_NAME_EN,
            "parent_lang": config.PARENT_LANG,
            "today": today(),
            "last_sync": self.last_sync or json.loads(self.store.setting("last_sync", "null")),
            "sync": self.job,
            "live_connected": self.live.connected,
            "pending_review": len(self.store.pending_cards()),
            "protected": bool(config.ACCESS_TOKEN),
            "paused_until": ps["paused_until"],
        }

    # ---- pause ----
    def _load_pauses(self) -> list[dict]:
        raw = self.store.setting("pauses")
        return json.loads(raw) if raw else []

    def _save_pauses(self, pauses: list[dict]) -> None:
        self.store.set_setting("pauses", json.dumps(pauses))

    def pause(self, minutes: int | None = None, until: str | None = None) -> dict:
        """Add a pause window.  Pass minutes=60, or until='tomorrow'."""
        now_ms = int(time.time() * 1000)
        if until == "tomorrow":
            tz = config.TZ
            tomorrow = (datetime.now(tz).date() + timedelta(days=1))
            end_ms = int(datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=tz).timestamp() * 1000)
        elif minutes is not None and minutes > 0:
            end_ms = now_ms + minutes * 60_000
        else:
            raise ValueError("provide minutes or until='tomorrow'")
        pauses = self._load_pauses()
        pauses.append({"start_ms": now_ms, "end_ms": end_ms})
        self._save_pauses(pauses)
        return self.pause_state()

    def resume(self) -> dict:
        """End any active pause by setting its end_ms to now."""
        now_ms = int(time.time() * 1000)
        pauses = self._load_pauses()
        changed = False
        for p in pauses:
            if p["start_ms"] <= now_ms < p["end_ms"]:
                p["end_ms"] = now_ms
                changed = True
        if changed:
            self._save_pauses(pauses)
        return self.pause_state()

    def paused_at(self, ms: int) -> bool:
        """True if the given timestamp (milliseconds) falls inside any pause window."""
        for p in self._load_pauses():
            if p["start_ms"] <= ms < p["end_ms"]:
                return True
        return False

    def pause_state(self) -> dict:
        """Current pause state: whether paused, when the pause ends (ms + ISO string)."""
        now_ms = int(time.time() * 1000)
        for p in self._load_pauses():
            if p["start_ms"] <= now_ms < p["end_ms"]:
                end_iso = datetime.fromtimestamp(p["end_ms"] / 1000, config.TZ).isoformat()
                return {"paused": True, "paused_until_ms": p["end_ms"], "paused_until": end_iso}
        return {"paused": False, "paused_until_ms": None, "paused_until": None}

    def stats(self) -> dict:
        s = self.store.scalar
        return {
            "conversations": s("SELECT COUNT(*) FROM conversations WHERE status='digested'") or 0,
            "skipped": s("SELECT COUNT(*) FROM conversations WHERE status='skipped'") or 0,
            "lines": s("SELECT COALESCE(SUM(json_array_length(utterances)),0) FROM conversations") or 0,
            "cards": s("SELECT COUNT(*) FROM cards WHERE deleted=0") or 0,
            "pending": s("SELECT COUNT(*) FROM cards WHERE deleted=0 AND status='pending'") or 0,
            "reviews": s("SELECT COUNT(*) FROM reviews") or 0,
            "reminders": s("SELECT COUNT(*) FROM promises WHERE status='reminder'") or 0,
            "live_reminders": s("SELECT COUNT(*) FROM live_reminders WHERE status='set'") or 0,
            "bee_calls": dict(self.bee.calls.counts),
            "bee": self.bee.mode, "ai": llm.engine(), "model": llm.model(),
        }

    # ---- sync: Bee -> digests -> cards ----
    def sync(self, redo: bool = False) -> dict:
        """Read recent conversations from Bee and digest the new ones. Blocks."""
        with self.sync_lock:
            report = {"seen": 0, "digested": 0, "skipped": 0, "errors": [], "at": int(time.time() * 1000)}
            since = bee.days_ago(config.LOOKBACK_DAYS)
            todo = []
            try:
                summaries = self.bee.list_conversations(limit=30)
            except bee.BeeError as exc:
                report["errors"].append(str(exc))
                summaries = []
            for summary in summaries:
                start = bee.to_ms(summary.get("start_time")) or bee.to_ms(summary.get("created_at")) or 0
                if start < since or not summary.get("end_time"):
                    continue  # too old, or still being recorded
                report["seen"] += 1
                known = self.store.conversation(summary["id"])
                if known and known["status"] == "deleted":
                    continue  # tombstone: never re-sync a deleted conversation
                if known and not redo and (known["status"] in ("digested", "skipped")
                                          or known["status"] == "waiting" and llm.engine() == "manual"):
                    continue
                todo.append(summary["id"])
            self.job.update(running=True, total=len(todo), done=0, current=None)
            try:
                facts = self._known_facts(report) if todo else []
                with ThreadPoolExecutor(max_workers=3) as pool:
                    for _ in pool.map(lambda cid: self._digest_one(cid, report, facts), todo):
                        self.job["done"] += 1
                self._photo_cards(report)
            finally:
                self.job.update(running=False, current=None, report=report)
            self.last_sync = report
            self.store.set_setting("last_sync", json.dumps(report))
            return report

    def start_sync(self, redo: bool = False) -> dict:
        """Sync in the background; poll status()['sync'] for progress."""
        if self.job["running"] or self.sync_lock.locked():
            return {"started": False, "running": True}
        self.job.update(running=True, total=0, done=0)
        threading.Thread(target=self.sync, kwargs={"redo": redo}, name="sync", daemon=True).start()
        return {"started": True, "running": True}

    def _known_facts(self, report: dict) -> list[str]:
        """What Bee already knows about her, so the AI can name the people she talks to."""
        try:
            return self.bee.facts()
        except bee.BeeError as exc:
            report["errors"].append(f"facts: {exc}")
            return []

    def _digest_one(self, cid: int, report: dict, facts: list[str] | None = None) -> None:
        self.job["current"] = cid
        try:
            conv = self.bee.get_conversation(cid)
        except bee.BeeError as exc:
            report["errors"].append(f"{cid}: {exc}")
            return
        start = bee.to_ms(conv.get("start_time")) or bee.to_ms(conv.get("created_at")) or 0
        if self.paused_at(start):
            self.store.save_conversation(conv, None, "skipped", "paused", [])
            report["skipped"] += 1
            return
        items = bee.utterances(conv)
        if bee.word_count(items) < config.MIN_WORDS:
            self.store.save_conversation(conv, None, "skipped", "too short to practise", items)
            report["skipped"] += 1
            return
        if llm.engine() == "manual":  # no model: the transcript waits to be read by hand (app/manual.py)
            self.store.save_conversation(conv, None, "waiting", "waiting to be read", items)
            report["waiting"] = report.get("waiting", 0) + 1
            return
        try:
            d = digest.build(conv, facts=facts)
        except Exception as exc:  # keep the transcript even when the AI step fails
            self.store.save_conversation(conv, None, "error", str(exc)[:300], items)
            report["errors"].append(f"{cid}: {exc}")
            return
        self.store.save_conversation(conv, d, "digested", None, items)
        report["digested"] += 1
        if self.reminders:
            self.reminders.link(cid)

    def _photo_cards(self, report: dict, day: str | None = None) -> None:
        """'Who were you with when you took this photo?' for today's photos that
        were taken during a conversation. At most PHOTO_CARDS a day."""
        day = day or today()
        if config.PHOTO_CARDS <= 0 or self.store.count_cards("photo", day) >= config.PHOTO_CARDS:
            return
        try:
            photos = self.bee.photos(day)
        except bee.BeeError as exc:
            report["errors"].append(f"photos: {exc}")
            return
        convs = [c for c in self.store.conversations(day) if c["status"] == "digested" and not c["private"]]
        slack = 10 * 60_000
        for ph in sorted(photos, key=lambda p: p["at"] or 0):
            if not ph["at"] or self.store.count_cards("photo", day) >= config.PHOTO_CARDS:
                continue
            conv = next((c for c in convs if c["start_ms"] - slack <= ph["at"] <= (c["end_ms"] or c["start_ms"]) + slack), None)
            card = digest.photo_card(conv, ph["at"]) if conv else None
            if not card or self.store.scalar("SELECT 1 FROM cards WHERE source_key=?", (f"photo:{ph['id']}",)):
                continue
            raw = ph.get("raw") or {}
            ext = Path(str(raw.get("file") or raw.get("filename") or "x.jpg")).suffix.lower() or ".jpg"
            name = re.sub(r"[^A-Za-z0-9_-]", "", str(ph["id"]))[:40] + ext
            try:
                self.bee.save_photo(ph["id"], config.DATA / "photos" / name)
            except (bee.BeeError, OSError, StopIteration) as exc:
                report["errors"].append(f"photo {ph['id']}: {exc}")
                continue
            if self.store.add_card(conv["id"], card, day, media={"photo": name}, source_key=f"photo:{ph['id']}"):
                report["photos"] = report.get("photos", 0) + 1

    # ---- background: live stream + periodic sync (real Bee only) ----
    def start_background(self) -> None:
        if self.bee.mode != "cli":
            return
        threading.Thread(target=self._live_loop, name="bee-stream", daemon=True).start()
        threading.Thread(target=self._sync_loop, name="bee-sync", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._resync.set()

    def _sync_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sync()
            except Exception:
                pass
            self._resync.wait(config.SYNC_MINUTES * 60)
            self._resync.clear()

    def _live_loop(self) -> None:
        for kind, data in self.bee.stream(self._stop):
            self.live.connected = True
            if kind == "new-utterance":
                u = data.get("utterance") or {}
                if (u.get("text") or "").strip():
                    self.live.line(str(u.get("speaker") or ""), u["text"].strip(),
                                   bee.to_ms(u.get("spoken_at")) or bee.to_ms(u.get("start")),
                                   conversation=data.get("conversation_uuid") or data.get("conversation_id"))
            elif kind == "conversation-ended":
                self._resync.set()  # digest it now so tonight's practice includes it

    def replay_demo(self, conversation_id: int) -> None:
        """Play one sample conversation into the live feed (sample day only)."""
        if not hasattr(self.bee, "replay"):
            return

        def run():
            for i, (_, data) in enumerate(self.bee.replay(conversation_id)):
                u = data["utterance"]
                self.live.line(u["speaker"], u["text"], demo=True, conversation=conversation_id, index=i)
        threading.Thread(target=run, daemon=True).start()

    def _heard(self, item: dict) -> None:
        reminders = getattr(self, "reminders", None)  # lines can't arrive before __init__ ends, but be safe
        if reminders:
            reminders.heard(item)

    # ---- the day, for the family page ----
    def day(self, day: str | None = None) -> dict:
        day = day or today()
        out = []
        for c in self.store.conversations(day):
            names = {s["label"]: s for s in c["speakers"]}
            lines = [{"i": i, "speaker": u["speaker"], "name": (names.get(u["speaker"]) or {}).get("name_en"),
                      "is_parent": (names.get(u["speaker"]) or {}).get("is_parent", False),
                      "text": _fixed(c, i) or u["text"], "heard": u["text"], "at": clock(u["at"]),
                      "background": i in (c.get("background") or []),
                      "en": (c["lines_en"][i] if i < len(c["lines_en"]) else "")}
                     for i, u in enumerate(c["utterances"])]
            out.append({
                "id": c["id"], "start": clock(c["start_ms"]), "end": clock(c["end_ms"]),
                "title_en": c["title_en"] or c["bee_summary"] or "Conversation", "title_parent": c["title_parent"],
                "summary_en": c["summary_en"], "summary_parent": c["summary_parent"], "language": c["language"],
                "status": c["status"], "error": c["error"], "source": c["source"], "private": bool(c["private"]),
                "speakers": c["speakers"], "lines": lines, "cards": self.store.cards_for(c["id"]),
            })
        return {"day": day, "conversations": out}

    def set_private(self, cid: int, private: bool) -> None:
        self.store.set_private(cid, private)

    def delete_conversation(self, cid: int) -> None:
        """Remove everything Memory Lane has for a conversation; keep a tombstone."""
        conv = self.store.conversation(cid)
        if not conv or conv["status"] == "deleted":
            raise KeyError(f"no conversation {cid}")
        self.store.delete_conversation(cid)

    def delete_card(self, card_id: int) -> None:
        self._card(card_id)
        self.store.update_card(card_id, deleted=1)

    def approve_card(self, card_id: int) -> dict:
        """A family member checked a health question against the transcript."""
        card = self._card(card_id)
        self.store.update_card(card_id, status="active", due=min(card["due"], today()))
        return {"card_id": card_id, "status": "active"}

    def pending(self) -> list[dict]:
        return [c | {"when": clock(c["start_ms"])} for c in self.store.pending_cards()]

    # ---- evening practice ----
    def plan(self, day: str | None = None, create: bool = False) -> list[int]:
        """Tonight's questions, fixed once practice starts so the order never jumps.
        A couple of older cards first, then today's most important ones, in the
        order the day happened: a walk down memory lane."""
        day = day or today()
        key = f"plan:{day}"
        due = {c["id"]: c for c in self.store.due_cards(day)}
        reviewed = {r["card_id"] for r in self.store.reviews_on(day)}
        saved = self.store.setting(key)
        if saved:
            ids = [i for i in json.loads(saved) if i in due or i in reviewed]
            room = config.SESSION_SIZE - len(ids)
            if room > 0:
                ids += [i for i in self._choose(list(due.values()), day) if i not in ids][:room]
        else:
            ids = self._choose(list(due.values()), day)
        if create and ids:
            self.store.set_setting(key, json.dumps(ids))
        return ids

    def _choose(self, due: list[dict], day: str) -> list[int]:
        # Older cards: ones she actually missed first, then ones never asked.
        older = sorted((c for c in due if c["created_day"] < day),
                       key=lambda c: (c["seen"] == 0, c["box"], -c["importance"], c["id"]))
        fresh = [c for c in due if c["created_day"] >= day]
        take_older = older[:MAX_REVIEWS_PER_NIGHT]
        room = config.SESSION_SIZE - len(take_older)
        ranked = sorted(fresh, key=lambda c: (-c["importance"], c["start_ms"] or 0, c["id"]))
        picked = ranked[:room]
        photo = next((c for c in ranked if c["kind"] == "photo"), None)
        if photo and room > 1 and photo not in picked:  # one photo a night: the easiest way in to a memory
            picked[-1] = photo
        if len(picked) < room:
            take_older = older[: config.SESSION_SIZE - len(picked)]
        picked.sort(key=lambda c: (c["start_ms"] or 0, c["id"]))
        return [c["id"] for c in take_older] + [c["id"] for c in picked]

    def practice_state(self, day: str | None = None) -> dict:
        day = day or today()
        plan = self.plan(day)
        done = {r["card_id"]: r["result"] for r in self.store.reviews_on(day)}
        results = [done.get(i) for i in plan]
        items = []
        for i, r in zip(plan, results):
            card = self.store.card(i)
            if card and r:
                items.append({"card_id": i, "question": card["question_parent"], "question_en": card["question_en"],
                              "result": r})
        return {"day": day, "total": len(plan), "answered": sum(r is not None for r in results),
                "remaining": sum(r is None for r in results), "results": results, "answered_items": items,
                "remembered": sum(r == "remembered" for r in results),
                "hint": sum(r == "hint" for r in results),
                "forgot": sum(r == "forgot" for r in results)}

    def outline(self, day: str | None = None) -> list[dict]:
        """Tonight's conversations in order, for the day ribbon on the evening screen."""
        day = day or today()
        plan = set(self.plan(day))
        convs = {}
        for cid in plan:
            card = self.store.card(cid)
            if card:
                convs.setdefault(card["conversation_id"], 0)
                convs[card["conversation_id"]] += 1
        out = []
        for c in self.store.conversations(day):
            if c["id"] in convs:
                out.append({"conversation_id": c["id"], "time": clock(c["start_ms"]), "title": c["title_parent"],
                            "title_en": c["title_en"], "questions": convs[c["id"]]})
        return out

    def next_card(self, day: str | None = None) -> dict | None:
        day = day or today()
        plan = self.plan(day, create=True)
        done = {r["card_id"] for r in self.store.reviews_on(day)}
        for n, cid in enumerate(plan):
            if cid not in done:
                card = self.store.card(cid)
                if card:
                    return self.public_card(card, reveal=False, day=day) | {"number": n + 1, "total": len(plan)}
        return None

    def public_card(self, card: dict, reveal: bool, day: str | None = None) -> dict:
        conv = self.store.conversation(card["conversation_id"]) or {}
        out = {"card_id": card["id"], "kind": card["kind"], "conversation_id": card["conversation_id"],
               "question": card["question_parent"], "question_en": card["question_en"],
               "when": clock(conv.get("start_ms")), "about": conv.get("title_parent") or conv.get("title_en"),
               "about_en": conv.get("title_en"), "review": card["created_day"] < (day or today()),
               "photo": f"/media/photos/{card['media']['photo']}" if (card.get("media") or {}).get("photo") else None,
               "voice": f"/media/voice/{card['voice']}" if card.get("voice") else None}
        if reveal:
            utts = conv.get("utterances") or []
            lines_en = conv.get("lines_en") or []
            names = {s["label"]: s for s in conv.get("speakers") or []}
            out |= {"answer": card["answer_parent"], "answer_en": card["answer_en"],
                    "evidence": [{"speaker": utts[i]["speaker"],
                                  "name": (names.get(utts[i]["speaker"]) or {}).get("name_parent") or utts[i]["speaker"],
                                  "name_en": (names.get(utts[i]["speaker"]) or {}).get("name_en") or utts[i]["speaker"],
                                  "text": _fixed(conv, i) or utts[i]["text"], "heard": utts[i]["text"],
                                  "at": clock(utts[i]["at"]),
                                  "en": lines_en[i] if i < len(lines_en) else ""}
                                 for i in card["evidence"] if i < len(utts)]}
        return out

    def hint(self, card_id: int) -> dict:
        card = self._card(card_id)
        return {"card_id": card_id, "hint": card["hint_parent"], "hint_en": card["hint_en"]}

    def reveal(self, card_id: int) -> dict:
        return self.public_card(self._card(card_id), reveal=True)

    def record(self, card_id: int, result: str, day: str | None = None) -> dict:
        if result not in RESULTS:
            raise ValueError(f"result must be one of {', '.join(RESULTS)}")
        day = day or today()
        card = self._card(card_id)
        if any(r["card_id"] == card_id for r in self.store.reviews_on(day)):
            raise ValueError("this question was already answered tonight")
        if result == "remembered":
            box = min(5, card["box"] + 1)
            due = _plus(day, INTERVALS[box])
        elif result == "hint":
            box, due = card["box"], _plus(day, 1)
        else:
            box, due = 1, _plus(day, 1)
        self.store.add_review(card_id, day, result, card["box"], card["due"])
        self.store.update_card(card_id, box=box, due=due)
        return {"card_id": card_id, "result": result, "box": box, "next_due": due,
                "next": self.next_card(day), "state": self.practice_state(day)}

    def reset_practice(self, day: str | None = None) -> dict:
        """Undo tonight's answers and plan, e.g. to record the demo again."""
        day = day or today()
        undone = self.store.undo_reviews(day)
        self.store.delete_setting(f"plan:{day}")
        return {"undone": undone, "state": self.practice_state(day)}

    def _card(self, card_id: int) -> dict:
        card = self.store.card(int(card_id))
        if not card or card["deleted"]:
            raise KeyError(f"no question {card_id}")
        return card

    # ---- promises ----
    def promises(self) -> list[dict]:
        return [p | {"when": clock(p["start_ms"])} for p in self.store.promises()]

    def open_promises(self) -> list[dict]:
        return [p for p in self.promises() if p["status"] != "dismissed"]

    def remind(self, pid: int) -> dict:
        """Send a promise to the wearer's Bee as a todo, with a 9am alarm on its day."""
        p = self.store.promise(int(pid))
        if not p:
            raise KeyError(f"no promise {pid}")
        if p["status"] == "reminder":
            return {"promise_id": pid, "already": True, "bee_todo_id": p["bee_todo_id"], "alarm_at": None}
        alarm = None
        if p["due_date"]:
            try:
                alarm = datetime.fromisoformat(p["due_date"]).replace(hour=9, tzinfo=config.TZ).isoformat()
            except ValueError:
                alarm = None
        text = p["text_parent"] if p["by_parent"] else f"{p['who']}: {p['text_parent']}"
        todo = self.bee.create_todo(text, alarm)
        todo_id = str((todo.get("todo") or todo).get("id", ""))
        self.store.update_promise(int(pid), status="reminder", bee_todo_id=todo_id)
        return {"promise_id": pid, "bee_todo_id": todo_id, "alarm_at": alarm}

    def dismiss(self, pid: int) -> None:
        if not self.store.promise(int(pid)):
            raise KeyError(f"no promise {pid}")
        self.store.update_promise(int(pid), status="dismissed")

    # ---- facts for Bee's memory (family-approved write-back) ----
    def facts(self) -> list[dict]:
        return [f | {"when": clock(f["start_ms"])} for f in self.store.facts()]

    def save_fact(self, fid: int) -> dict:
        f = self.store.fact(int(fid))
        if not f:
            raise KeyError(f"no fact {fid}")
        if f["status"] == "saved":
            return {"fact_id": fid, "already": True, "bee_fact_id": f["bee_fact_id"]}
        out = self.bee.create_fact(f["text_en"])
        fact_id = str((out.get("fact") or out).get("id", "")) if isinstance(out, dict) else ""
        self.store.update_fact(int(fid), status="saved", bee_fact_id=fact_id)
        return {"fact_id": fid, "bee_fact_id": fact_id}

    def dismiss_fact(self, fid: int) -> None:
        if not self.store.fact(int(fid)):
            raise KeyError(f"no fact {fid}")
        self.store.update_fact(int(fid), status="dismissed")

    # ---- a family member's voice for a question ----
    VOICE_TYPES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
                   "audio/wav": ".wav", "audio/x-wav": ".wav"}

    def set_voice(self, card_id: int, data: bytes, content_type: str) -> dict:
        card = self._card(card_id)
        ext = self.VOICE_TYPES.get(content_type.split(";")[0].strip().lower())
        if not ext:
            raise ValueError(f"unsupported audio type {content_type!r}")
        if not data or len(data) > 5_000_000:
            raise ValueError("the recording is empty or longer than about a minute")
        folder = config.DATA / "voice"
        folder.mkdir(parents=True, exist_ok=True)
        if card.get("voice"):
            (folder / card["voice"]).unlink(missing_ok=True)
        name = f"card-{card_id}-{int(time.time())}{ext}"
        (folder / name).write_bytes(data)
        self.store.update_card(card_id, voice=name)
        return {"card_id": card_id, "voice": f"/media/voice/{name}"}

    def clear_voice(self, card_id: int) -> None:
        card = self._card(card_id)
        if card.get("voice"):
            (config.DATA / "voice" / card["voice"]).unlink(missing_ok=True)
        self.store.update_card(card_id, voice=None)

    # ---- reminders set while she was talking ----
    def live_reminders(self, day: str | None = None) -> list[dict]:
        return [r | {"when": clock(r["at_ms"])} for r in self.store.live_reminders(day or today())]

    def undo_live_reminder(self, rid: int) -> dict:
        r = self.store.live_reminder(int(rid))
        if not r:
            raise KeyError(f"no reminder {rid}")
        if r["status"] == "set" and r["bee_todo_id"]:
            self.bee.delete_todo(r["bee_todo_id"])
        self.store.set_live_reminder(int(rid), "undone")
        self.store._exec("UPDATE promises SET status='suggested', bee_todo_id=NULL WHERE bee_todo_id=? AND status='reminder'",
                         (r["bee_todo_id"],))
        return {"reminder_id": rid, "status": "undone"}

    # ---- progress ----
    def progress(self, days: int = 14) -> dict:
        start = _plus(today(), -(days - 1))
        rows = self.store.review_counts(start)
        by_day = {_plus(start, i): {"remembered": 0, "hint": 0, "forgot": 0} for i in range(days)}
        for r in rows:
            if r["day"] in by_day:
                by_day[r["day"]][r["result"]] = r["n"]
        total = sum(sum(v.values()) for v in by_day.values())
        remembered = sum(v["remembered"] for v in by_day.values())
        streak = 0
        for d in sorted(by_day, reverse=True):
            if sum(by_day[d].values()):
                streak += 1
            elif d != today():
                break
        return {"days": [{"day": d, **v} for d, v in by_day.items()], "total": total,
                "remembered": remembered, "rate": round(remembered / total, 2) if total else None,
                "streak": streak}


class LiveReminders:
    """Real time: when she promises something while still talking ("I'll call
    Kamala on Sunday"), it lands in her Bee as a todo with an alarm within
    seconds. The family can undo it. Later, the full digest of the same
    conversation links its promise to this todo instead of suggesting it again.

    With an AI engine, a fast model reads the last few lines after each pause.
    On the sample day without one, the hand-written promises fire when the
    replay reaches the line they came from."""

    QUIET_SECONDS = 2.5   # wait for a pause before asking the model
    WINDOW = 8            # lines of context

    def __init__(self, lane: "MemoryLane"):
        self.lane = lane
        self.buffers: dict = {}
        self.timers: dict = {}
        self.lock = threading.Lock()
        self._samples = None

    # -- input --
    def heard(self, item: dict) -> None:
        if self.lane.paused_at(item.get("at") or int(time.time() * 1000)):
            return
        if item.get("demo") and llm.engine() == "mock":
            return self._sample(item)
        if llm.engine() in ("mock", "manual"):
            return
        key = item.get("conversation") or "live"
        with self.lock:
            buf = self.buffers.setdefault(key, deque(maxlen=self.WINDOW))
            buf.append(item)
            if key in self.timers:
                self.timers[key].cancel()
            t = threading.Timer(self.QUIET_SECONDS, self._check, args=(key,))
            t.daemon = True
            self.timers[key] = t
            t.start()

    def _check(self, key) -> None:
        with self.lock:
            lines = list(self.buffers.get(key) or [])
            self.timers.pop(key, None)
        if not lines:
            return
        already = [r["text_en"] for r in self.lane.store.live_reminders(today()) if r["status"] == "set"]
        try:
            found = digest.live_promises(lines, already)
        except Exception:  # a missed live reminder is fine; the evening digest still suggests it
            return
        for p in found:
            said = lines[p["line"]]["text"] if 0 <= p["line"] < len(lines) else ""
            self.set(p["text_parent"], p["text_en"], p["due_date"], p["due_time"], said, conversation=key)

    def _sample(self, item: dict) -> None:
        if self._samples is None:
            self._samples = json.loads((config.FIXTURES / "demo_digests.json").read_text())
        sample = self._samples.get(str(item.get("conversation"))) or {}
        for p in sample.get("promises", []):
            if p.get("by_parent") and p.get("evidence") and min(p["evidence"]) == item.get("index"):
                self.set(p["text_parent"], p["text_en"], p.get("due_date") or "", "", item["text"],
                         conversation=item.get("conversation"))

    # -- output --
    def set(self, text_parent: str, text_en: str, due_date: str, due_time: str, said: str,
            conversation=None) -> dict | None:
        day = today()
        for r in self.lane.store.live_reminders(day):  # the same promise twice in a minute
            if r["status"] == "set" and (r["text_en"] or "").lower() == text_en.lower():
                return None
        alarm = None
        if due_date:
            try:
                hh, mm = (int(x) for x in (due_time or "09:00").split(":")[:2])
                alarm = datetime.fromisoformat(due_date).replace(hour=hh, minute=mm, tzinfo=config.TZ).isoformat()
            except ValueError:
                alarm = None
        try:
            todo = self.lane.bee.create_todo(text_parent, alarm)
        except bee.BeeError:
            return None
        todo_id = str((todo.get("todo") or todo).get("id", ""))
        rid = self.lane.store.add_live_reminder(int(time.time() * 1000), day, text_parent, text_en, said, alarm, todo_id)
        item = {"type": "reminder", "id": rid, "text": text_parent, "en": text_en, "alarm_at": alarm, "said": said,
                "at": int(time.time() * 1000)}
        self.lane.live.event(item)
        if isinstance(conversation, int):  # already digested (e.g. a replay): link it now
            self.link(conversation, anytime=True)
        return item

    def link(self, cid: int, anytime: bool = False) -> None:
        """After a conversation is digested: its promises that were already set
        live become 'in Bee' instead of new suggestions."""
        conv = self.lane.store.conversation(cid)
        if not conv:
            return
        live = [r for r in self.lane.store.live_reminders(today() if anytime else conv["day"]) if r["status"] == "set"
                and (anytime or conv["start_ms"] - 60_000 <= r["at_ms"] <= (conv["end_ms"] or conv["start_ms"]) + 5 * 60_000)]
        if not live:
            return
        for p in self.lane.store._rows("SELECT * FROM promises WHERE conversation_id=? AND status='suggested'", (cid,)):
            match = next((r for r in live if _same(p, r)), None)
            if match:
                self.lane.store.update_promise(p["id"], status="reminder", bee_todo_id=match["bee_todo_id"])


def _same(promise: dict, reminder: dict) -> bool:
    """The digest's promise and the live reminder are the same thing."""
    if promise["due_date"] and reminder["alarm_at"] and reminder["alarm_at"].startswith(promise["due_date"]):
        return True
    a = set((promise["text_en"] or "").lower().split())
    b = set((reminder["text_en"] or "").lower().split())
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= 0.5

