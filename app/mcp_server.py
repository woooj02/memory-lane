"""Memory Lane as an Alexa+ add-on: a self-hosted MCP server over Streamable
HTTP (protocol 2025-11-25). Any MCP client can run the evening practice:
the web Echo Show page in web/index.html, any MCP client, or an Alexa+ add-on host.

Every tool returns structured data plus `say`, one short line in the
parent's language for a voice surface to speak.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import config
from .service import MemoryLane

SAY = {
    "ne": {
        "hello": "नमस्ते {name}! आजको सम्झना अभ्यास: {n} वटा प्रश्न।",
        "none": "नमस्ते {name}! आज अभ्यास गर्ने कुरा छैन। भोलि फेरि भेटौँ।",
        "remembered": "धेरै राम्रो!",
        "hint": "ठीक छ, सँगै सम्झियौँ।",
        "forgot": "केही छैन, भोलि फेरि सोध्छु।",
        "done": "आजको अभ्यास सकियो। {n} मध्ये {r} वटा सम्झनुभयो।",
        "reminder": "Bee मा सम्झाउने राखेँ।",
    },
    "en": {
        "hello": "Hello {name}! Tonight's memory practice has {n} questions.",
        "none": "Hello {name}! Nothing to practise tonight. See you tomorrow.",
        "remembered": "Well done!",
        "hint": "Good, we remembered it together.",
        "forgot": "That's fine, I'll ask again tomorrow.",
        "done": "That's tonight's practice. You remembered {r} of {n}.",
        "reminder": "I added a reminder in Bee.",
    },
}


def say(key: str, **kw) -> str:
    table = SAY.get(config.PARENT_LANG, SAY["en"])
    return table[key].format(name=config.PARENT_NAME, **kw)


def build(app: MemoryLane) -> FastMCP:
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*", "testserver"] + config.MCP_ALLOWED_HOSTS
    origins = ["http://127.0.0.1:*", "http://localhost:*"] + [f"https://{h}" for h in config.MCP_ALLOWED_HOSTS]
    mcp = FastMCP(
        "Memory Lane",
        instructions=(
            f"Evening memory practice for {config.PARENT_NAME}, built from today's conversations captured by "
            f"their Bee wearable. Questions and the `say` lines are in {config.PARENT_LANG_NAME}. "
            "Start with start_evening_practice, ask the question aloud, then call get_hint or reveal_answer "
            "as the person asks, and record_recall with how it went. Never answer for them."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins),
    )

    @mcp.tool()
    def start_evening_practice() -> dict[str, Any]:
        """Start (or resume) tonight's recall practice. Returns the first question,
        or none when everything due has been practised."""
        card = app.next_card()
        state = app.practice_state()
        line = say("hello", n=state["remaining"]) if card else say("none")
        return {"say": line, "state": state, "question": card, "day": app.outline()}

    @mcp.tool()
    def get_hint(card_id: int) -> dict[str, Any]:
        """A partial clue for the current question, without the answer."""
        h = app.hint(card_id)
        return h | {"say": h["hint"]}

    @mcp.tool()
    def reveal_answer(card_id: int) -> dict[str, Any]:
        """The answer, with the exact lines from today's conversation it came from."""
        r = app.reveal(card_id)
        return r | {"say": r["answer"]}

    @mcp.tool()
    def record_recall(card_id: int, result: Literal["remembered", "hint", "forgot"]) -> dict[str, Any]:
        """Record how the person did: remembered on their own, remembered after a hint,
        or forgot. Remembered questions come back after a longer gap; the rest come back tomorrow.
        Returns the next question, or the evening's summary when practice is done."""
        out = app.record(card_id, result)
        line = say(result)
        if out["next"] is None:
            s = out["state"]
            line += " " + say("done", n=s["answered"], r=s["remembered"])
        return out | {"say": line}

    @mcp.tool()
    def todays_conversations() -> dict[str, Any]:
        """Who the person talked with today and what about, in their language and in English."""
        day = app.day()
        items = [{"id": c["id"], "time": c["start"], "title": c["title_parent"], "title_en": c["title_en"],
                  "summary": c["summary_parent"], "summary_en": c["summary_en"]}
                 for c in day["conversations"] if not c["private"] and c["status"] == "digested"]
        return {"day": day["day"], "conversations": items,
                "say": "; ".join(f"{i['time']} {i['title']}" for i in items if i["title"])}

    @mcp.tool()
    def list_promises() -> dict[str, Any]:
        """Things the person or someone they talked with promised to do, and whether a reminder is set."""
        items = [{"promise_id": p["id"], "who": p["who"], "by_parent": bool(p["by_parent"]),
                  "text": p["text_parent"], "text_en": p["text_en"], "due_date": p["due_date"],
                  "reminder_set": p["status"] == "reminder"} for p in app.open_promises()]
        return {"promises": items, "say": "; ".join(i["text"] for i in items)}

    @mcp.tool()
    def remind_me(promise_id: int) -> dict[str, Any]:
        """Add a promise to the person's Bee as a todo, with a 9am alarm on its day if one was said."""
        out = app.remind(promise_id)
        return out | {"say": say("reminder")}

    @mcp.tool()
    def recall_progress(days: int = 7) -> dict[str, Any]:
        """How practice went over the last few days: answers per day, recall rate and streak."""
        p = app.progress(max(1, min(days, 60)))
        return p | {"say": f"{p['remembered']}/{p['total']}"}

    return mcp
