"""Digest conversations by hand instead of with a model (LLM_PROVIDER=manual).

    ./run.sh manual sync              read new conversations from Bee; they wait to be read
    ./run.sh manual export [id ...]   write data/manual/<id>.md: the same prompts the model gets
    ./run.sh manual apply <id> ...    load data/manual/<id>.json and store it like a model's digest

The answer file has every UNDERSTAND_SCHEMA field plus lines_parent, lines_en and background
(TRANSLATE_SCHEMA), one entry per transcript line. It goes through digest.clean(), the same
checks a model's answer gets: cards need real evidence lines, never TV lines.
"""

from __future__ import annotations

import json
import sys

from . import bee, config, digest
from .service import MemoryLane

DIR = config.DATA / "manual"
REQUIRED = set(digest.UNDERSTAND_SCHEMA["required"]) | set(digest.TRANSLATE_SCHEMA["required"])


def _waiting(lane: MemoryLane) -> list[int]:
    return [r["id"] for r in lane.store._rows("SELECT id FROM conversations WHERE status='waiting' ORDER BY start_ms")]


def export(lane: MemoryLane, ids: list[int]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    facts = lane.bee.facts() if ids else []
    for cid in ids:
        conv = lane.bee.get_conversation(cid)
        items = bee.utterances(conv)
        texts = [u["text"] for u in items]
        (DIR / f"{cid}.md").write_text(
            f"# Conversation {cid}\n\n## Understand ({digest.UNDERSTAND_SYSTEM[:60]}...)\n\n"
            f"{digest.understand_prompt(conv, items, facts)}\n\n## Translate\n\n{digest.translate_prompt(texts)}\n")
        print(f"{cid}: {len(items)} lines -> {DIR / f'{cid}.md'}")


def apply(lane: MemoryLane, cid: int) -> None:
    data = json.loads((DIR / f"{cid}.json").read_text())
    missing = REQUIRED - data.keys()
    if missing:
        raise SystemExit(f"{cid}: missing {sorted(missing)}")
    conv = lane.bee.get_conversation(cid)
    items = bee.utterances(conv)
    for key in ("lines_parent", "lines_en"):
        if len(data[key]) != len(items):
            raise SystemExit(f"{cid}: {key} has {len(data[key])} lines, the transcript has {len(items)}")
    d = digest.clean(data, len(items), source="manual", known_facts=lane.bee.facts())
    lane.store.save_conversation(conv, d, "digested", None, items)
    if lane.reminders:
        lane.reminders.link(cid)
    print(f"{cid}: {len(d['cards'])} cards, {len(d['promises'])} promises, {len(d['facts'])} facts, "
          f"{len(d['background'])} background lines")


def main(argv: list[str]) -> None:
    lane = MemoryLane()
    cmd, args = (argv[0] if argv else "export"), [int(a) for a in argv[1:]]
    if cmd == "sync":
        print(json.dumps(lane.sync(), ensure_ascii=False))
        print("waiting:", _waiting(lane))
    elif cmd == "export":
        export(lane, args or _waiting(lane))
    elif cmd == "apply":
        for cid in args or [int(p.stem) for p in sorted(DIR.glob("*.json"))]:
            apply(lane, cid)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
