"""Bee data, through the official `bee` CLI, via the bee-cli-python library
(https://github.com/woooj02/bee-cli-python, our Open Source add-on).

Every call shells out to `bee ... --json`, so authentication, the API host and
its certificates stay inside Bee's own client. Two sources share one shape:

  CliBee   the real thing: conversations, transcripts, facts, photos, todos
           and the live event stream from the wearer's Bee account.
  DemoBee  a recorded sample day from fixtures/demo_day.json, shifted to
           today, so the app runs (and the tests pass) without a device.

A conversation has `transcriptions[].utterances[]`, each utterance has `text`,
`speaker` (e.g. "SPEAKER_1") and `spoken_at`. Times arrive as epoch ms,
seconds or ISO strings, so everything goes through `to_ms`.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator

import beecli
from beecli import BeeError, infer_type, to_ms, utterances, word_count  # noqa: F401  (re-exported)

from . import config


def classify_event(data: dict) -> str:
    """The app's name for a stream payload: new-utterance, conversation-ended, or
    the library's inferred type."""
    ev = beecli.Event(infer_type(data), data, exact=False)
    return "conversation-ended" if ev.ended else ev.type


def photo_time(photo: dict) -> int | None:
    """When a photo was taken. The JSON shape of `bee photos list` isn't
    documented, so try the likely fields in order."""
    for key in ("taken_at", "takenAt", "captured_at", "created_at", "createdAt", "timestamp", "date", "time"):
        ms = to_ms(photo.get(key))
        if ms:
            return ms
    return None


def fact_texts(payload) -> list[str]:
    """Confirmed fact texts from `bee facts list --json`, whatever the wrapper."""
    rows = beecli.unwrap(payload, "facts") or []
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    out = []
    for f in rows if isinstance(rows, list) else []:
        if isinstance(f, dict) and f.get("confirmed", True) is not False and (f.get("text") or "").strip():
            out.append(f["text"].strip())
    return out


class _Calls:
    """Counts the Bee calls made, for the /how page and the logs."""

    def __init__(self):
        self.counts: Counter = Counter()
        self.lock = threading.Lock()

    def add(self, name: str, n: int = 1) -> None:
        with self.lock:
            self.counts[name] += n


# ---- the real source --------------------------------------------------------

class CliBee:
    mode = "cli"

    def __init__(self, binary: str | None = None, runner: Callable[..., subprocess.CompletedProcess] | None = None):
        self.calls = _Calls()
        run = runner or subprocess.run

        def counted(cmd, **kw):
            words = [a for a in cmd[1:] if not a.startswith("-")][:2]
            if words and words[0] in ("me", "version", "today", "now", "search"):
                words = words[:1]
            self.calls.add(" ".join(words))
            return run(cmd, **kw)

        self.client = beecli.Bee(binary or config.BEE_BIN, runner=counted)
        self.binary = self.client.binary

    def me(self) -> dict:
        return self.client.me()

    def list_conversations(self, limit: int = 20) -> list[dict]:
        return (self.client.conversations.list(limit=limit) or {}).get("conversations", [])

    def get_conversation(self, conversation_id: int) -> dict:
        return beecli.unwrap(self.client.conversations.get(int(conversation_id)), "conversation") or {}

    def create_todo(self, text: str, alarm_at: str | None = None) -> dict:
        return self.client.todos.create(text, alarm_at=alarm_at) or {}

    def delete_todo(self, todo_id) -> None:
        self.client.todos.delete(todo_id)

    def facts(self) -> list[str]:
        return fact_texts(self.client.facts.list(limit=100))

    def create_fact(self, text: str) -> dict:
        return self.client.facts.create(text) or {}

    def photos(self, day: str) -> list[dict]:
        rows = beecli.unwrap(self.client.photos.list(date=day, limit=50), "photos") or []
        return [{"id": p.get("id"), "at": photo_time(p), "raw": p} for p in rows if isinstance(p, dict) and p.get("id")]

    def save_photo(self, photo_id, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client.photos.get(photo_id, str(path))
        except BeeError:
            if not path.exists():  # some versions print a status line instead of JSON
                raise
        return path

    def stream(self, stop: threading.Event) -> Iterator[tuple[str, dict]]:
        """Live events from `bee stream`, reconnecting with backoff until stopped."""
        s = self.client.stream(["new-utterance", "new-conversation", "update-conversation",
                                "update-conversation-summary"])
        threading.Thread(target=lambda: (stop.wait(), s.close()), daemon=True).start()
        try:
            for ev in s:
                kind = "conversation-ended" if ev.ended else ev.type
                self.calls.add(f"stream {kind}")
                yield kind, ev.data if isinstance(ev.data, dict) else {}
        except BeeError:
            return


# ---- the sample day ---------------------------------------------------------

class DemoBee:
    """A recorded day, replayed as if it happened today. Times in the fixture
    are minutes after local midnight; ids and text are kept as recorded."""

    mode = "demo"

    def __init__(self, path=None, today: datetime | None = None):
        self.path = path or config.FIXTURES / "demo_day.json"
        self.day = json.loads(self.path.read_text())
        self._today = today
        self.todos: list[dict] = []
        self.saved_facts: list[dict] = []
        self.calls = _Calls()

    def _midnight_ms(self) -> int:
        now = self._today or datetime.now(config.TZ)
        midnight = now.astimezone(config.TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp() * 1000)

    def _materialize(self, conv: dict) -> dict:
        base = self._midnight_ms()
        start = base + conv["start_minute"] * 60_000
        utts = []
        for n, u in enumerate(conv["utterances"]):
            at = start + u.get("second", n * 12) * 1000
            utts.append({"id": conv["id"] * 1000 + n, "realtime": False, "start": at, "end": at + 4000,
                         "spoken_at": at, "text": u["text"], "speaker": u["speaker"], "created_at": at})
        end = start + conv["minutes"] * 60_000
        return {
            "id": conv["id"], "start_time": start, "end_time": end, "created_at": start, "updated_at": end,
            "device_type": "apple_watch", "state": "COMPLETED",
            "summary": conv.get("bee_summary"), "short_summary": conv.get("bee_title"),
            "transcriptions": [{"id": conv["id"], "realtime": False, "utterances": utts}],
            "suggested_links": [], "primary_location": None,
        }

    def me(self) -> dict:
        return {"first_name": config.PARENT_NAME, "demo": True}

    def list_conversations(self, limit: int = 20) -> list[dict]:
        self.calls.add("conversations list")
        out = []
        for conv in self.day["conversations"][:limit]:
            full = self._materialize(conv)
            out.append({k: full[k] for k in ("id", "start_time", "end_time", "created_at", "summary", "state")})
        return out

    def get_conversation(self, conversation_id: int) -> dict:
        self.calls.add("conversations get")
        for conv in self.day["conversations"]:
            if conv["id"] == int(conversation_id):
                return self._materialize(conv)
        raise BeeError(f"conversation {conversation_id} not found")

    def create_todo(self, text: str, alarm_at: str | None = None) -> dict:
        self.calls.add("todos create")
        todo = {"id": 900 + len(self.todos), "text": text, "alarm_at": alarm_at, "completed": False, "demo": True}
        self.todos.append(todo)
        return todo

    def delete_todo(self, todo_id) -> None:
        self.calls.add("todos delete")
        self.todos = [t for t in self.todos if str(t["id"]) != str(todo_id)]

    def facts(self) -> list[str]:
        self.calls.add("facts list")
        return list(self.day.get("facts", [])) + [f["text"] for f in self.saved_facts]

    def create_fact(self, text: str) -> dict:
        self.calls.add("facts create")
        fact = {"id": 700 + len(self.saved_facts), "text": text, "confirmed": True, "demo": True}
        self.saved_facts.append(fact)
        return fact

    def photos(self, day: str) -> list[dict]:
        self.calls.add("photos list")
        base = self._midnight_ms()
        return [{"id": p["id"], "at": base + p["minute"] * 60_000, "raw": p} for p in self.day.get("photos", [])]

    def save_photo(self, photo_id, path: Path) -> Path:
        self.calls.add("photos get")
        p = next(p for p in self.day.get("photos", []) if str(p["id"]) == str(photo_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((config.FIXTURES / "photos" / p["file"]).read_bytes())
        return path

    def stream(self, stop: threading.Event) -> Iterator[tuple[str, dict]]:
        return iter(())

    def replay(self, conversation_id: int, speed: float = 4.0) -> Iterator[tuple[str, dict]]:
        """The utterances of one sample conversation as live events, sped up."""
        conv = self.get_conversation(conversation_id)
        prev = None
        for u in utterances(conv):
            if prev is not None:
                time.sleep(min(3.5, max(0.8, (u["at"] - prev) / 1000 / speed)))
            prev = u["at"]
            self.calls.add("stream new-utterance")
            yield "new-utterance", {"utterance": u, "conversation_id": conversation_id, "demo": True}


def source() -> CliBee | DemoBee:
    return CliBee() if config.bee_mode() == "cli" else DemoBee()


def local_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, config.TZ).date().isoformat()


def days_ago(n: int) -> int:
    return int((datetime.now(config.TZ) - timedelta(days=n)).timestamp() * 1000)
