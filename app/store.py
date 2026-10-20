"""SQLite storage: conversations, practice cards, reviews, promises, settings."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY,            -- Bee conversation id
  day TEXT NOT NULL,                 -- local date, YYYY-MM-DD
  start_ms INTEGER, end_ms INTEGER,
  language TEXT, title_en TEXT, title_parent TEXT, summary_en TEXT, summary_parent TEXT,
  bee_summary TEXT,
  speakers TEXT NOT NULL DEFAULT '[]',     -- [{label, name_en, name_parent, is_parent}]
  utterances TEXT NOT NULL DEFAULT '[]',   -- [{speaker, text, at}]
  lines_en TEXT NOT NULL DEFAULT '[]',     -- English, one per utterance
  status TEXT NOT NULL,              -- digested | skipped | waiting | error
  error TEXT, source TEXT,
  private INTEGER NOT NULL DEFAULT 0,
  updated_ms INTEGER
);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  kind TEXT, importance INTEGER, health INTEGER NOT NULL DEFAULT 0,
  question_parent TEXT, question_en TEXT, answer_parent TEXT, answer_en TEXT,
  hint_parent TEXT, hint_en TEXT, evidence TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'active',   -- active | pending (health: waits for family OK)
  box INTEGER NOT NULL DEFAULT 1,    -- Leitner box 1..5
  due TEXT NOT NULL,                 -- next day to ask, YYYY-MM-DD
  created_day TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id INTEGER NOT NULL, day TEXT NOT NULL, at_ms INTEGER NOT NULL,
  result TEXT NOT NULL,              -- remembered | hint | forgot
  prev_box INTEGER, prev_due TEXT    -- so a practice can be undone
);
CREATE TABLE IF NOT EXISTS promises (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  by_parent INTEGER, who TEXT, text_parent TEXT, text_en TEXT, due_date TEXT,
  evidence TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'suggested',   -- suggested | reminder | dismissed
  bee_todo_id TEXT, updated_ms INTEGER
);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  text_en TEXT, text_parent TEXT, evidence TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'suggested',   -- suggested | saved (in Bee) | dismissed
  bee_fact_id TEXT, updated_ms INTEGER
);
CREATE TABLE IF NOT EXISTS live_reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at_ms INTEGER NOT NULL, day TEXT NOT NULL,
  text_parent TEXT, text_en TEXT, said TEXT, alarm_at TEXT,
  bee_todo_id TEXT, status TEXT NOT NULL DEFAULT 'set'   -- set | undone
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS cards_due ON cards(due, deleted);
CREATE INDEX IF NOT EXISTS reviews_day ON reviews(day);
"""

# Columns added after the first version; created on open if missing.
MIGRATIONS = {
    "conversations": {"speakers": "TEXT NOT NULL DEFAULT '[]'",
                      "lines_parent": "TEXT NOT NULL DEFAULT '[]'",   # each line in correct parent language
                      "background": "TEXT NOT NULL DEFAULT '[]'"},    # line numbers that were TV / background
    "cards": {"health": "INTEGER NOT NULL DEFAULT 0", "status": "TEXT NOT NULL DEFAULT 'active'",
              "media": "TEXT",          # {"photo": "<file name in DATA/photos>"}
              "source_key": "TEXT",     # e.g. "photo:501", so a re-sync doesn't add it twice
              "voice": "TEXT"},         # file name in DATA/voice: the question in a family member's voice
    "reviews": {"prev_box": "INTEGER", "prev_due": "TEXT"},
}

JSON_COLUMNS = {"utterances", "lines_en", "lines_parent", "background", "evidence", "speakers"}


class Store:
    def __init__(self, path: Path | str | None = None):
        path = Path(path or config.DATA / "memory-lane.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            for table, cols in MIGRATIONS.items():
                have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
                for col, decl in cols.items():
                    if col not in have:
                        self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            self.db.commit()

    # -- generic helpers --
    def _rows(self, sql: str, args=()) -> list[dict]:
        with self.lock:
            out = []
            for r in self.db.execute(sql, args).fetchall():
                d = dict(r)
                for k in JSON_COLUMNS & d.keys():
                    d[k] = json.loads(d[k] or "[]")
                if "media" in d:
                    d["media"] = json.loads(d["media"]) if d["media"] else None
                out.append(d)
            return out

    def _one(self, sql: str, args=()) -> dict | None:
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    def _exec(self, sql: str, args=()) -> int:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    def scalar(self, sql: str, args=()):
        with self.lock:
            row = self.db.execute(sql, args).fetchone()
            return row[0] if row else None

    # -- conversations --
    def conversation(self, cid: int) -> dict | None:
        return self._one("SELECT * FROM conversations WHERE id=?", (cid,))

    def conversations(self, day: str) -> list[dict]:
        return self._rows("SELECT * FROM conversations WHERE day=? AND status!='deleted' ORDER BY start_ms", (day,))

    def save_conversation(self, conv: dict, digest: dict | None, status: str, error: str | None = None,
                          utterances: list[dict] | None = None) -> None:
        from .bee import local_day, to_ms

        d = digest or {}
        start = to_ms(conv.get("start_time")) or to_ms(conv.get("created_at")) or 0
        end = to_ms(conv.get("end_time"))
        day = local_day(start)
        utts = [{"speaker": u.get("speaker"), "text": u.get("text"), "at": u.get("at")} for u in (utterances or [])]
        with self.lock:
            self.db.execute(
                """INSERT INTO conversations (id, day, start_ms, end_ms, language, title_en, title_parent,
                     summary_en, summary_parent, bee_summary, speakers, utterances, lines_en, lines_parent,
                     background, status, error, source, updated_ms)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET day=excluded.day, start_ms=excluded.start_ms, end_ms=excluded.end_ms,
                     language=excluded.language, title_en=excluded.title_en, title_parent=excluded.title_parent,
                     summary_en=excluded.summary_en, summary_parent=excluded.summary_parent,
                     bee_summary=excluded.bee_summary, speakers=excluded.speakers, utterances=excluded.utterances,
                     lines_en=excluded.lines_en, lines_parent=excluded.lines_parent,
                     background=excluded.background, status=excluded.status, error=excluded.error,
                     source=excluded.source, updated_ms=excluded.updated_ms""",
                (conv["id"], day, start, end, d.get("language"), d.get("title_en"), d.get("title_parent"),
                 d.get("summary_en"), d.get("summary_parent"), conv.get("summary"),
                 json.dumps(d.get("speakers", []), ensure_ascii=False), json.dumps(utts, ensure_ascii=False),
                 json.dumps(d.get("lines_en", []), ensure_ascii=False),
                 json.dumps(d.get("lines_parent", []), ensure_ascii=False), json.dumps(d.get("background", [])),
                 status, error, d.get("source"), _now()))
            if digest:
                # A re-digest replaces this conversation's cards that were never practised,
                # and its open suggestions. Practised cards keep their history.
                self.db.execute("""DELETE FROM cards WHERE conversation_id=? AND id NOT IN
                                   (SELECT DISTINCT card_id FROM reviews)""", (conv["id"],))
                self.db.execute("DELETE FROM promises WHERE conversation_id=? AND status='suggested'", (conv["id"],))
                self.db.execute("DELETE FROM facts WHERE conversation_id=? AND status='suggested'", (conv["id"],))
                for f in digest.get("facts", []):
                    self.db.execute(
                        "INSERT INTO facts (conversation_id, text_en, text_parent, evidence, updated_ms) VALUES (?,?,?,?,?)",
                        (conv["id"], f["text_en"], f["text_parent"], json.dumps(f["evidence"]), _now()))
                for c in digest["cards"]:
                    self.db.execute(
                        """INSERT INTO cards (conversation_id, kind, importance, health, status, question_parent,
                             question_en, answer_parent, answer_en, hint_parent, hint_en, evidence, due, created_day)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (conv["id"], c["kind"], c["importance"], int(bool(c.get("health"))),
                         "pending" if c.get("health") else "active",
                         c["question_parent"], c["question_en"], c["answer_parent"], c["answer_en"],
                         c["hint_parent"], c["hint_en"], json.dumps(c["evidence"]), day, day))
                for p in digest["promises"]:
                    self.db.execute(
                        """INSERT INTO promises (conversation_id, by_parent, who, text_parent, text_en, due_date,
                             evidence, updated_ms) VALUES (?,?,?,?,?,?,?,?)""",
                        (conv["id"], int(bool(p["by_parent"])), p["who"], p["text_parent"], p["text_en"],
                         p["due_date"], json.dumps(p["evidence"]), _now()))
            self.db.commit()

    def set_private(self, cid: int, private: bool) -> None:
        self._exec("UPDATE conversations SET private=? WHERE id=?", (int(private), cid))

    def delete_conversation(self, cid: int) -> None:
        """Remove all content for a conversation and mark it as a tombstone (status='deleted').
        Photo files and voice files are removed from disk; cards, reviews, promises and facts are
        deleted. The row is kept so a re-sync won't restore it."""
        with self.lock:
            # Collect card ids for this conversation so we can delete their reviews
            card_rows = self.db.execute(
                "SELECT id, media FROM cards WHERE conversation_id=?", (cid,)).fetchall()
            card_ids = [r[0] for r in card_rows]
            # Delete photo files referenced by cards
            for r in card_rows:
                media_json = r[1]
                if media_json:
                    try:
                        media = json.loads(media_json)
                        if media and media.get("photo"):
                            try:
                                (config.DATA / "photos" / media["photo"]).unlink(missing_ok=True)
                            except OSError:
                                pass
                    except (json.JSONDecodeError, TypeError):
                        pass
            # Delete voice files referenced by cards
            voice_rows = self.db.execute(
                "SELECT voice FROM cards WHERE conversation_id=? AND voice IS NOT NULL", (cid,)).fetchall()
            for r in voice_rows:
                if r[0]:
                    try:
                        (config.DATA / "voice" / r[0]).unlink(missing_ok=True)
                    except OSError:
                        pass
            # Delete reviews for these cards
            if card_ids:
                placeholders = ",".join("?" * len(card_ids))
                self.db.execute(f"DELETE FROM reviews WHERE card_id IN ({placeholders})", card_ids)
            # Delete cards
            self.db.execute("DELETE FROM cards WHERE conversation_id=?", (cid,))
            # Delete promises
            self.db.execute("DELETE FROM promises WHERE conversation_id=?", (cid,))
            # Delete facts
            self.db.execute("DELETE FROM facts WHERE conversation_id=?", (cid,))
            # Nullify transcript and translated text; keep the tombstone row
            self.db.execute(
                """UPDATE conversations SET
                     utterances='[]', lines_en='[]', lines_parent='[]', background='[]',
                     speakers='[]',
                     title_en=NULL, title_parent=NULL,
                     summary_en=NULL, summary_parent=NULL,
                     bee_summary=NULL,
                     status='deleted',
                     updated_ms=?
                   WHERE id=?""",
                (_now(), cid))
            self.db.commit()

    # -- cards --
    def card(self, card_id: int) -> dict | None:
        return self._one("SELECT * FROM cards WHERE id=?", (card_id,))

    def cards_for(self, cid: int) -> list[dict]:
        return self._rows("SELECT * FROM cards WHERE conversation_id=? AND deleted=0 ORDER BY id", (cid,))

    def due_cards(self, day: str) -> list[dict]:
        """Cards that may be asked on `day`, with their conversation's start time."""
        return self._rows(
            """SELECT c.*, v.start_ms, (SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id) AS seen
               FROM cards c JOIN conversations v ON v.id=c.conversation_id
               WHERE c.deleted=0 AND c.status='active' AND v.private=0 AND v.status!='deleted' AND c.due<=?
               ORDER BY c.id""", (day,))

    def pending_cards(self) -> list[dict]:
        return self._rows(
            """SELECT c.*, v.start_ms, v.title_en FROM cards c JOIN conversations v ON v.id=c.conversation_id
               WHERE c.deleted=0 AND c.status='pending' AND v.private=0 AND v.status!='deleted' ORDER BY v.start_ms, c.id""")

    def add_card(self, conversation_id: int, c: dict, day: str, media: dict | None = None,
                 source_key: str | None = None) -> int | None:
        """A card made outside the digest (photo cards). Skipped if source_key is already there."""
        with self.lock:
            if source_key and self.db.execute("SELECT 1 FROM cards WHERE source_key=?", (source_key,)).fetchone():
                return None
            cur = self.db.execute(
                """INSERT INTO cards (conversation_id, kind, importance, health, status, question_parent, question_en,
                     answer_parent, answer_en, hint_parent, hint_en, evidence, due, created_day, media, source_key)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (conversation_id, c["kind"], c["importance"], int(bool(c.get("health"))),
                 "pending" if c.get("health") else "active", c["question_parent"], c["question_en"],
                 c["answer_parent"], c["answer_en"], c["hint_parent"], c["hint_en"], json.dumps(c["evidence"]),
                 day, day, json.dumps(media) if media else None, source_key))
            self.db.commit()
            return cur.lastrowid

    def count_cards(self, kind: str, day: str) -> int:
        return self.scalar("SELECT COUNT(*) FROM cards WHERE kind=? AND created_day=? AND deleted=0", (kind, day)) or 0

    def update_card(self, card_id: int, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE cards SET {cols} WHERE id=?", (*fields.values(), card_id))

    # -- reviews --
    def add_review(self, card_id: int, day: str, result: str, prev_box: int, prev_due: str) -> None:
        self._exec("INSERT INTO reviews (card_id, day, at_ms, result, prev_box, prev_due) VALUES (?,?,?,?,?,?)",
                   (card_id, day, _now(), result, prev_box, prev_due))

    def reviews_on(self, day: str) -> list[dict]:
        return self._rows("SELECT * FROM reviews WHERE day=? ORDER BY at_ms, id", (day,))

    def undo_reviews(self, day: str) -> int:
        """Delete the day's reviews, newest first, restoring each card's box and due date."""
        with self.lock:
            rows = self.db.execute("SELECT * FROM reviews WHERE day=? ORDER BY at_ms DESC, id DESC", (day,)).fetchall()
            for r in rows:
                if r["prev_due"]:
                    self.db.execute("UPDATE cards SET box=?, due=? WHERE id=?", (r["prev_box"], r["prev_due"], r["card_id"]))
            self.db.execute("DELETE FROM reviews WHERE day=?", (day,))
            self.db.commit()
            return len(rows)

    def review_counts(self, since_day: str) -> list[dict]:
        return self._rows("""SELECT day, result, COUNT(*) AS n FROM reviews WHERE day>=?
                             GROUP BY day, result ORDER BY day""", (since_day,))

    # -- promises --
    def promises(self) -> list[dict]:
        return self._rows("""SELECT p.*, v.start_ms, v.title_en, v.title_parent FROM promises p
                             JOIN conversations v ON v.id=p.conversation_id WHERE v.private=0
                             AND v.status!='deleted'
                             ORDER BY p.status='dismissed', p.by_parent DESC, p.due_date='', p.due_date, p.id""")

    def promise(self, pid: int) -> dict | None:
        return self._one("SELECT * FROM promises WHERE id=?", (pid,))

    def update_promise(self, pid: int, **fields) -> None:
        fields["updated_ms"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE promises SET {cols} WHERE id=?", (*fields.values(), pid))

    # -- facts (suggested for Bee's memory) --
    def facts(self) -> list[dict]:
        return self._rows("""SELECT f.*, v.start_ms, v.title_en FROM facts f JOIN conversations v ON v.id=f.conversation_id
                             WHERE v.private=0 AND f.status!='dismissed' AND v.status!='deleted'
                             ORDER BY f.status='saved', v.start_ms, f.id""")

    def fact(self, fid: int) -> dict | None:
        return self._one("SELECT * FROM facts WHERE id=?", (fid,))

    def update_fact(self, fid: int, **fields) -> None:
        fields["updated_ms"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE facts SET {cols} WHERE id=?", (*fields.values(), fid))

    # -- reminders set while she was talking --
    def add_live_reminder(self, at_ms: int, day: str, text_parent: str, text_en: str, said: str,
                          alarm_at: str | None, bee_todo_id: str) -> int:
        return self._exec("""INSERT INTO live_reminders (at_ms, day, text_parent, text_en, said, alarm_at, bee_todo_id)
                             VALUES (?,?,?,?,?,?,?)""", (at_ms, day, text_parent, text_en, said, alarm_at, bee_todo_id))

    def live_reminders(self, day: str) -> list[dict]:
        return self._rows("SELECT * FROM live_reminders WHERE day=? ORDER BY at_ms", (day,))

    def live_reminder(self, rid: int) -> dict | None:
        return self._one("SELECT * FROM live_reminders WHERE id=?", (rid,))

    def set_live_reminder(self, rid: int, status: str) -> None:
        self._exec("UPDATE live_reminders SET status=? WHERE id=?", (status, rid))

    # -- settings --
    def setting(self, key: str, default: str | None = None) -> str | None:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._exec("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, value))

    def delete_setting(self, key: str) -> None:
        self._exec("DELETE FROM settings WHERE key=?", (key,))


def _now() -> int:
    return int(time.time() * 1000)
