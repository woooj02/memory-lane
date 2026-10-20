"""Turn one Bee conversation into practice cards and an English translation.

Two kinds of AI call (Together AI, Claude or Bedrock; see llm.py), run in parallel:
  understand  the whole transcript -> who spoke, a title and summary in both
              languages, up to N practice cards, and promises.
  translate   the transcript in chunks -> one English line per spoken line.
              Chunked so a long conversation never overflows one answer.

Cards are the product: small, concrete questions about the parent's own day,
asked that evening in their language, each tied to the lines it came from so
the family can check it. Cards about health wait for a family member's OK.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import bee, config, llm

KINDS = ["person", "plan", "instruction", "place", "detail", "promise"]
CHUNK = 60  # transcript lines per translation call

_str = {"type": "string"}
_ints = {"type": "array", "items": {"type": "integer"}}

UNDERSTAND_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "description": "BCP-47 code of the main spoken language"},
        "title_en": _str, "title_parent": _str, "summary_en": _str, "summary_parent": _str,
        "speakers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": _str, "name_en": _str, "name_parent": _str, "is_parent": {"type": "boolean"}},
                "required": ["label", "name_en", "name_parent", "is_parent"],
                "additionalProperties": False,
            },
        },
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": KINDS},
                    "health": {"type": "boolean"},
                    "question_parent": _str, "question_en": _str,
                    "answer_parent": _str, "answer_en": _str,
                    "hint_parent": _str, "hint_en": _str,
                    "evidence": _ints,
                    "importance": {"type": "integer", "enum": [1, 2, 3]},
                },
                "required": ["kind", "health", "question_parent", "question_en", "answer_parent", "answer_en",
                             "hint_parent", "hint_en", "evidence", "importance"],
                "additionalProperties": False,
            },
        },
        "promises": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "by_parent": {"type": "boolean"}, "who": _str,
                    "text_parent": _str, "text_en": _str,
                    "due_date": {"type": "string", "description": "YYYY-MM-DD, or empty if no day was said"},
                    "evidence": _ints,
                },
                "required": ["by_parent", "who", "text_parent", "text_en", "due_date", "evidence"],
                "additionalProperties": False,
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text_en": _str, "text_parent": _str, "evidence": _ints},
                "required": ["text_en", "text_parent", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["language", "title_en", "title_parent", "summary_en", "summary_parent",
                 "speakers", "cards", "promises", "facts"],
    "additionalProperties": False,
}

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "lines_parent": {"type": "array", "items": _str},
        "lines_en": {"type": "array", "items": _str},
        "background": {"type": "array", "items": {"type": "integer"},
                       "description": "line numbers that are TV, radio, music or other background audio"},
    },
    "required": ["lines_parent", "lines_en", "background"],
    "additionalProperties": False,
}

# Bee has no Nepali recognizer. Set to Hindi, it writes Nepali speech in Devanagari with Hindi spellings and
# Hindi words swapped in ("मैंले बुच्छा" for "मैले बुझें"). The models are told so, and rebuild the Nepali.
HEARD_NOTE = (f"""
How the transcript was made: Bee has no {config.PARENT_LANG_NAME} speech recognition, so it runs its {config.BEE_HEARS}
recognizer. Most lines are {config.PARENT_LANG_NAME} speech written down as if it were {config.BEE_HEARS}: similar-sounding
{config.BEE_HEARS} words and spellings replace the {config.PARENT_LANG_NAME} ones, and grammar endings get bent. Read
every line as the {config.PARENT_LANG_NAME} that was most likely said. Lines that are fluent {config.BEE_HEARS} (often a TV
serial or film playing nearby) or English are background unless the conversation shows a person said them.
""" if config.rebuilding() else "")

UNDERSTAND_SYSTEM = f"""You help an older adult keep their memory active by practising recall of their own day.

You get the transcript of one real conversation the person had today, captured by their Bee wearable.
The person wearing the Bee is the parent. They speak {config.PARENT_LANG_NAME}; their family reads {config.FAMILY_LANG_NAME}.
Speech recognition makes mistakes. When a line is unclear, do not build a card on it.
{HEARD_NOTE}
Return:
- speakers: for each speaker label, who it is (a name or a role like "son", "doctor") in {config.FAMILY_LANG_NAME} and {config.PARENT_LANG_NAME}, and which one is the parent.
- A short title and a 1-2 sentence summary, in {config.FAMILY_LANG_NAME} and in {config.PARENT_LANG_NAME}.
- Up to {config.MAX_CARDS_PER_CONVERSATION} practice cards about details worth remembering: who they talked to, plans and dates,
  instructions they were given, places, and things they promised. Skip small talk and the obvious.
  - Questions are short (under 14 words), warm and spoken-style, addressed to the parent in {config.PARENT_LANG_NAME},
    using respectful forms (तपाईं, not तिमी, in Nepali). Name the day ("सोमबार", "on Monday") instead of
    saying "today": a question comes back days later.
  - Answers are a few words. Hints give a partial clue without giving the answer away.
  - evidence lists the transcript line numbers the answer comes from. Never invent anything that is not in the lines.
  - health is true for anything about medicine, doses, symptoms or treatment. Those questions only ask what the person
    was told ("What did the doctor say about the new tablet?") and quote it as said. Never add advice.
  - importance: 3 for dates, appointments, medicine instructions and promises; 2 for people and plans; 1 for nice details.
- Promises: concrete things someone said they will do, with the day if one was said (resolve weekdays against today's date).
- Facts: at most 3 lasting facts about the parent's life that Bee should remember, written in the first person as the
  parent ("Kamala is my older sister; she lives in Kathmandu", "My doctor is Dr. Patel"): people and how they're related,
  regular routines, places they go. Not one-off events or plans. Skip anything already in "What Bee already knows".

If the conversation has nothing worth practising (a TV in the background, a purchase at a till), return no cards.
Write every {config.PARENT_LANG_NAME} field in correct {config.PARENT_LANG_NAME}, never in the transcript's spellings."""

TRANSLATE_SYSTEM = f"""You clean up and translate transcript lines from a family's conversations.
The main language is usually {config.PARENT_LANG_NAME}.
{HEARD_NOTE}
For each numbered line, in order, exactly one entry in each list:
- lines_parent: the line in correct {config.PARENT_LANG_NAME}, as it was most likely said. Fix recognition errors and
  spellings, but don't add anything that isn't there. A line already in correct {config.PARENT_LANG_NAME} is copied as is;
  a line in {config.FAMILY_LANG_NAME} stays in {config.FAMILY_LANG_NAME}.
- lines_en: natural {config.FAMILY_LANG_NAME}. Keep names, numbers, dates and medicine names exactly as spoken.
- If a line is too garbled to recover, give your best reading and end both versions with "(unclear)".
Also list in background the line numbers that are TV, radio, music or other background audio rather than the people
talking."""


def _clock(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, config.TZ).strftime("%H:%M") if ms else "--:--"


def _numbered(items: list[dict], start: int = 0) -> str:
    return "\n".join(f"[{start + i}] {u['speaker']} ({_clock(u.get('at'))}): {u['text']}" for i, u in enumerate(items))


def build(conversation: dict, facts: list[str] | None = None) -> dict:
    """The digest for one conversation, from the AI engine or (offline) from the
    sample digests. Always returns the same shape."""
    items = bee.utterances(conversation)
    if config.llm_provider() == "mock":
        return _mock(conversation, items, facts)
    with ThreadPoolExecutor(max_workers=4) as pool:
        understood = pool.submit(understand, conversation, items, facts)
        chunks = [pool.submit(translate_full, [u["text"] for u in items[i:i + CHUNK]])
                  for i in range(0, len(items), CHUNK)]
        data = understood.result()
        lines = [line for c in chunks for line in c.result()]
    return clean({**data, "lines_en": [x["en"] for x in lines], "lines_parent": [x["parent"] for x in lines],
                  "background": [i for i, x in enumerate(lines) if x["background"]]},
                 len(items), source=llm.engine(), known_facts=facts)


def understand_prompt(conversation: dict, items: list[dict], facts: list[str] | None = None) -> str:
    today = datetime.now(config.TZ)
    start = bee.to_ms(conversation.get("start_time"))
    known = "\n".join(f"- {f}" for f in (facts or [])[:40]) or "(nothing yet)"
    return (f"Today is {today:%A %Y-%m-%d}. The conversation started at {_clock(start)}.\n"
            f"Bee's own summary (may be in English): {conversation.get('summary') or '(none)'}\n\n"
            f"What Bee already knows about the parent (facts they confirmed; use them to name speakers):\n{known}\n\n"
            f"Transcript ({len(items)} lines):\n{_numbered(items)}")


def translate_prompt(texts: list[str]) -> str:
    return f"{len(texts)} lines:\n" + "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))


def understand(conversation: dict, items: list[dict], facts: list[str] | None = None) -> dict:
    return llm.structured(UNDERSTAND_SYSTEM, understand_prompt(conversation, items, facts), UNDERSTAND_SCHEMA)


def translate_full(texts: list[str], effort: str | None = None) -> list[dict]:
    """For each line, same count, same order: {"parent": the line in correct parent language,
    "en": English, "background": TV or other background audio}."""
    if not texts:
        return []
    out = llm.structured(TRANSLATE_SYSTEM, translate_prompt(texts), TRANSLATE_SCHEMA,
                         max_tokens=12000, effort=effort)
    return lines_from(out, len(texts))


def lines_from(out: dict, n: int) -> list[dict]:
    pad = lambda xs: (list(xs or []) + [""] * n)[:n]  # noqa: E731
    background = {i for i in out.get("background") or [] if isinstance(i, int)}
    return [{"parent": p or "", "en": e or "", "background": i in background}
            for i, (p, e) in enumerate(zip(pad(out.get("lines_parent")), pad(out.get("lines_en"))))]


def translate(texts: list[str], effort: str | None = None) -> list[str]:
    """English for each line, same count, same order."""
    return [line["en"] for line in translate_full(texts, effort)]


def clean(data: dict, n_lines: int, source: str, known_facts: list[str] | None = None) -> dict:
    """Clamp everything the model returned to what the transcript can back up."""
    lines = (list(data.get("lines_en") or []) + [""] * n_lines)[:n_lines]
    fixed = (list(data.get("lines_parent") or []) + [""] * n_lines)[:n_lines]
    background = {i for i in data.get("background") or [] if isinstance(i, int) and 0 <= i < n_lines}

    def ok(ev):  # real line numbers, never the TV
        return sorted({i for i in ev if isinstance(i, int) and 0 <= i < n_lines and i not in background})

    cards = []
    for c in data.get("cards", []):
        c = dict(c, evidence=ok(c.get("evidence", [])))
        c.setdefault("health", False)
        if c["question_parent"].strip() and c["answer_parent"].strip() and c["evidence"]:
            cards.append(c)
    promises = [dict(p, evidence=ok(p.get("evidence", []))) for p in data.get("promises", [])
                if (p.get("text_parent") or "").strip()]
    speakers = [s for s in data.get("speakers", []) if s.get("label")]
    known = {f.strip().lower() for f in known_facts or []}
    facts = [dict(f, evidence=ok(f.get("evidence", []))) for f in data.get("facts", [])
             if (f.get("text_en") or "").strip() and f["text_en"].strip().lower() not in known]
    facts = [f for f in facts if f["evidence"]][:3]
    return {**data, "lines_en": lines, "lines_parent": fixed, "background": sorted(background),
            "speakers": speakers, "facts": facts,
            "cards": cards[: config.MAX_CARDS_PER_CONVERSATION], "promises": promises, "source": source}


def _mock(conversation: dict, items: list[dict], facts: list[str] | None = None) -> dict:
    samples = json.loads((config.FIXTURES / "demo_digests.json").read_text())
    sample = samples.get(str(conversation["id"]))
    if sample and len(sample["lines_en"]) == len(items):
        return clean(sample, len(items), source="sample", known_facts=facts)
    # Unknown conversation and no model: keep it visible, honestly empty.
    summary = conversation.get("summary") or "A conversation"
    title = conversation.get("short_summary") or "Conversation"
    return {
        "language": config.PARENT_LANG, "title_en": title, "title_parent": title,
        "summary_en": summary, "summary_parent": summary, "speakers": [],
        "lines_en": [""] * len(items), "cards": [], "promises": [], "facts": [], "source": "offline",
    }


def sample_translations() -> dict[str, str]:
    """Original line -> English, from the sample digests (live replay of the sample day)."""
    day = json.loads((config.FIXTURES / "demo_day.json").read_text())
    samples = json.loads((config.FIXTURES / "demo_digests.json").read_text())
    out = {}
    for conv in day["conversations"]:
        s = samples.get(str(conv["id"]))
        if s:
            for u, en in zip(conv["utterances"], s["lines_en"]):
                out[u["text"]] = en
    return out


# ---- photo cards: no AI needed, the answer comes from who was talking ----

_PERIODS = {"ne": ["बिहान", "दिउँसो", "बेलुका", "राति"], "en": ["morning", "afternoon", "evening", "night"]}
_NE_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def _period(hour: int) -> int:
    return 0 if hour < 12 else 1 if hour < 17 else 2 if hour < 20 else 3


def photo_card(conversation: dict, at_ms: int) -> dict | None:
    """'Who were you with when you took this photo?', answered from the other
    speakers in the conversation happening when it was taken, with their first
    lines as evidence. None if nobody else was named."""
    names = {s["label"]: s for s in conversation.get("speakers") or [] if not s.get("is_parent")}
    if not names:
        return None
    utts = conversation.get("utterances") or []
    evidence = [i for i, u in enumerate(utts) if u.get("speaker") in names][:2]
    if not evidence:
        return None
    who = [names[label] for label in dict.fromkeys(utts[i]["speaker"] for i in evidence)]
    t = datetime.fromtimestamp(at_ms / 1000, config.TZ)
    hhmm = f"{t.hour % 12 or 12}:{t.minute:02d}"
    p = _period(t.hour)
    en = {"question": "Who were you with when you took this photo?",
          "answer": " and ".join(s["name_en"] for s in who),
          "hint": f"You took it in the {_PERIODS['en'][p]}, around {hhmm}."}
    if config.PARENT_LANG == "ne":
        parent = {"question": "यो फोटो खिच्दा तपाईं कोसँग हुनुहुन्थ्यो?",
                  "answer": " र ".join(s["name_parent"] for s in who),
                  "hint": f"{_PERIODS['ne'][p]} {hhmm.translate(_NE_DIGITS)} तिर खिचेको।"}
    else:
        parent = en
    return {"kind": "photo", "health": False, "importance": 2, "evidence": evidence,
            "question_parent": parent["question"], "question_en": en["question"],
            "answer_parent": parent["answer"], "answer_en": en["answer"],
            "hint_parent": parent["hint"], "hint_en": en["hint"]}


# ---- live: promises said out loud, caught while the conversation is still going ----

LIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "reminders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text_parent": _str, "text_en": _str,
                    "due_date": {"type": "string", "description": "YYYY-MM-DD, or empty"},
                    "due_time": {"type": "string", "description": "HH:MM 24h, or empty"},
                    "line": {"type": "integer"},
                },
                "required": ["text_parent", "text_en", "due_date", "due_time", "line"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reminders"],
    "additionalProperties": False,
}

LIVE_SYSTEM = f"""You listen along to a conversation an older adult is having right now, captured live by their Bee wearable.
They speak {config.PARENT_LANG_NAME}. Speaker labels are not names, and you don't know which one is the wearer.
{HEARD_NOTE}
Find firm commitments in the lines marked NEW that the wearer will need to remember: something they said they will do
("I'll call you back on Sunday"), or something they agreed to ("Yes, Tuesday at 7, I'll come"). Not wishes ("we should
meet sometime"), not questions, not other people's plans that don't involve the wearer.
For each, write a short reminder in {config.PARENT_LANG_NAME} addressed to the wearer (respectful forms; in Nepali a
verb-noun like "कमला दिदीलाई फोन गर्ने"), the same in {config.FAMILY_LANG_NAME}, the day (resolve weekdays against today's
date) and time if said, and the index of the line it came from.
Leave out anything already in "Already set". Most of the time the answer is no reminders."""


def live_promises(lines: list[dict], already: list[str]) -> list[dict]:
    """Reminders from the last few live lines. Uses the fast model."""
    today = datetime.now(config.TZ)
    newest = max(0, len(lines) - 3)
    body = "\n".join(f"[{i}]{' NEW' if i >= newest else ''} {u['speaker']}: {u['text']}" for i, u in enumerate(lines))
    prompt = (f"Today is {today:%A %Y-%m-%d}, {today:%H:%M}.\n"
              f"Already set: {'; '.join(already) or '(none)'}\n\nLines:\n{body}")
    out = llm.structured(LIVE_SYSTEM, prompt, LIVE_SCHEMA, max_tokens=1500, effort="low").get("reminders", [])
    return [r for r in out if (r.get("text_parent") or "").strip() and newest <= r.get("line", -1) < len(lines)]

