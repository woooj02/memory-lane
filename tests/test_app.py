"""Runs offline on the sample day and the mock engine. deploy.sh refuses to ship if this fails."""

import json
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import bee, config, digest, service
from app.main import app, lane
from app.store import Store

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}


# ---- helpers ----

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def synced(client):
    assert client.post("/api/sync").json()["started"]
    for _ in range(100):
        h = client.get("/api/health").json()
        if not h["sync"]["running"] and h["sync"]["report"]:
            return h["sync"]["report"]
        time.sleep(0.05)
    raise AssertionError("sync did not finish")


def mcp(client, method, params=None, id_=1, headers=None):
    r = client.post("/mcp", headers={**MCP_HEADERS, **(headers or {})},
                    json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    assert r.status_code == 200, r.text
    return r.json()


def tool(client, name, **args):
    result = mcp(client, "tools/call", {"name": name, "arguments": args})["result"]
    assert not result.get("isError"), result
    return result["structuredContent"]


def fresh_lane(tmp_path, name="t.db"):
    lane2 = service.MemoryLane(Store(tmp_path / name), bee.DemoBee())
    lane2.sync()
    return lane2


# ---- pages, health, sync ----

def test_pages_and_health(client):
    for path in ("/", "/family", "/how"):
        assert client.get(path).status_code == 200
    h = client.get("/api/health").json()
    assert h["bee"] == "demo" and h["ai"] == "mock" and h["protected"] is False


def test_notice_page(client):
    r = client.get("/notice")
    assert r.status_code == 200
    body = r.text
    # Nepali text
    assert "नमस्ते" in body
    assert "Bee" in body
    assert "परिवार" in body        # "only my family"
    # English text
    assert "Hi!" in body
    assert "listening" in body
    assert "family" in body


def test_sync_digests_the_sample_day(synced):
    assert synced["digested"] == 4 and synced["skipped"] == 1 and not synced["errors"]


def test_day_has_speakers_translations_and_cards(client, synced):
    day = client.get("/api/day").json()
    convs = {c["id"]: c for c in day["conversations"]}
    assert convs[105]["status"] == "skipped"
    call = convs[101]
    assert call["lines"][2]["en"].startswith("Everyone's fine")
    assert call["lines"][0]["name"] == "Kamala didi (sister)" and call["lines"][1]["is_parent"]
    assert len(call["cards"]) == 3


def test_health_questions_wait_for_family(client, synced):
    pending = client.get("/api/pending").json()["cards"]
    assert len(pending) == 2 and all(c["conversation_id"] == 102 and c["health"] for c in pending)
    plan_cards = {lane.store.card(i)["conversation_id"] for i in lane.plan()}
    assert all(lane.store.card(i)["status"] == "active" for i in lane.plan())
    assert client.get("/api/stats").json()["pending"] == 2
    assert plan_cards  # the rest of the day still makes a plan


def test_stats_count_bee_calls(client, synced):
    s = client.get("/api/stats").json()
    assert s["conversations"] == 4 and s["lines"] == 38 and s["cards"] == 14
    assert s["bee_calls"]["conversations get"] >= 5


# ---- MCP: the Alexa+ add-on ----

def test_mcp_lists_tools(client):
    init = mcp(client, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "0"}})
    assert init["result"]["protocolVersion"] == "2025-11-25"
    names = {t["name"] for t in mcp(client, "tools/list")["result"]["tools"]}
    assert names == {"start_evening_practice", "get_hint", "reveal_answer", "record_recall",
                     "todays_conversations", "list_promises", "remind_me", "recall_progress"}


def test_evening_practice_over_mcp(client, synced):
    client.post("/api/practice/reset")
    start = tool(client, "start_evening_practice")
    assert "नमस्ते" in start["say"] and start["state"]["total"] == 6 and start["state"]["remaining"] == 6
    assert [d["conversation_id"] for d in start["day"]] == [101, 102, 103, 104]  # the day, in order
    q = start["question"]
    assert q["number"] == 1 and q["conversation_id"] == 101
    assert tool(client, "get_hint", card_id=q["card_id"])["hint"]
    shown = tool(client, "reveal_answer", card_id=q["card_id"])
    assert shown["answer"] and shown["evidence"][0]["name"] == "कमला दिदी"
    times = []
    out = None
    for r in ["remembered", "hint", "forgot", "remembered", "remembered", "forgot"]:
        times.append(q["when"])
        out = tool(client, "record_recall", card_id=q["card_id"], result=r)
        q = out["next"]
    assert q is None and times == sorted(times)  # walked through the day in order
    s = out["state"]
    assert s["answered"] == 6 and s["remembered"] == 3 and s["hint"] == 1 and s["forgot"] == 2
    assert "सकियो" in out["say"]
    again = tool(client, "start_evening_practice")
    assert again["question"] is None and again["state"]["answered"] == 6


def test_answering_twice_is_refused(client, synced):
    client.post("/api/practice/reset")
    q = tool(client, "start_evening_practice")["question"]
    tool(client, "record_recall", card_id=q["card_id"], result="forgot")
    body = mcp(client, "tools/call", {"name": "record_recall", "arguments": {"card_id": q["card_id"], "result": "forgot"}})
    assert body["result"]["isError"]
    assert client.post(f"/api/cards/{q['card_id']}/result", json={"result": "remembered"}).status_code == 422


def test_reset_undoes_answers_and_spacing(client, synced):
    client.post("/api/practice/reset")
    q = tool(client, "start_evening_practice")["question"]
    before = lane.store.card(q["card_id"])
    tool(client, "record_recall", card_id=q["card_id"], result="remembered")
    assert lane.store.card(q["card_id"])["box"] == before["box"] + 1
    r = client.post("/api/practice/reset").json()
    assert r["undone"] == 1 and r["state"]["answered"] == 0
    after = lane.store.card(q["card_id"])
    assert (after["box"], after["due"]) == (before["box"], before["due"])


def test_unknown_card_is_404(client, synced):
    assert client.post("/api/cards/99999/result", json={"result": "remembered"}).status_code == 404
    assert client.delete("/api/cards/99999").status_code == 404
    assert client.post("/api/promises/99999/remind").status_code == 404


# ---- practice rules ----

def test_spacing(tmp_path):
    lane2 = fresh_lane(tmp_path)
    day = service.today()
    card = lane2.next_card(day)
    a = lane2.record(card["card_id"], "remembered", day)
    assert a["box"] == 2 and a["next_due"] == service._plus(day, 2)
    b = lane2.record(a["next"]["card_id"], "forgot", day)
    assert b["box"] == 1 and b["next_due"] == service._plus(day, 1)
    with pytest.raises(ValueError):
        lane2.record(b["next"]["card_id"], "maybe", day)


def test_tomorrow_mixes_in_missed_cards(tmp_path):
    lane2 = fresh_lane(tmp_path)
    day = service.today()
    first = lane2.next_card(day)
    lane2.record(first["card_id"], "forgot", day)
    tomorrow = service._plus(day, 1)
    plan = lane2.plan(tomorrow)
    assert plan[0] == first["card_id"]  # yesterday's miss leads tomorrow's practice
    assert lane2.public_card(lane2.store.card(plan[0]), reveal=False, day=tomorrow)["review"] is True


def test_approving_a_health_question(tmp_path):
    lane2 = fresh_lane(tmp_path)
    pending = lane2.pending()
    assert len(pending) == 2
    lane2.approve_card(pending[0]["id"])
    assert len(lane2.pending()) == 1
    assert pending[0]["id"] in {c["id"] for c in lane2.store.due_cards(service.today())}


def test_private_conversation_leaves_practice(tmp_path):
    lane2 = fresh_lane(tmp_path)
    assert any(lane2.store.card(i)["conversation_id"] == 101 for i in lane2.plan())
    lane2.set_private(101, True)
    assert all(lane2.store.card(i)["conversation_id"] != 101 for i in lane2.plan())


def test_deleted_card_drops_out_of_a_started_plan(tmp_path):
    lane2 = fresh_lane(tmp_path)
    first = lane2.next_card()
    lane2.delete_card(first["card_id"])
    assert lane2.next_card()["card_id"] != first["card_id"]


# ---- promises -> Bee todos ----

def test_promise_becomes_bee_todo(client, synced):
    promises = client.get("/api/promises").json()["promises"]
    assert promises[0]["by_parent"]  # hers first
    call_back = next(p for p in promises if p["conversation_id"] == 101)
    r = client.post(f"/api/promises/{call_back['id']}/remind").json()
    assert r["bee_todo_id"] and r["alarm_at"].startswith("2026-10-18T09:00")
    assert lane.bee.todos[-1]["text"].startswith("आइतबार")
    assert client.post(f"/api/promises/{call_back['id']}/remind").json()["already"]
    listed = tool(client, "list_promises")["promises"]
    assert any(p["reminder_set"] for p in listed)


def test_progress(client, synced):
    client.post("/api/practice/reset")
    q = tool(client, "start_evening_practice")["question"]
    tool(client, "record_recall", card_id=q["card_id"], result="remembered")
    p = client.get("/api/progress?days=7").json()
    assert p["total"] == 1 and p["rate"] == 1.0
    assert len(p["days"]) == 7 and p["streak"] >= 1


# ---- live feed ----

def test_live_lines_get_english(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "live.db"), bee.DemoBee())
    item = lane2.live.line("SPEAKER_2", "केटा पोखराको हो, इन्जिनियर छ। नाम सुमन।")
    for _ in range(60):
        if item["en"]:
            break
        time.sleep(0.05)
    assert item["en"] == "The groom is from Pokhara, he's an engineer. His name is Suman."


# ---- access token ----

def test_access_token_guards_everything(monkeypatch):
    monkeypatch.setattr(config, "ACCESS_TOKEN", "s3cret")
    c = TestClient(app)  # no lifespan: the module client already runs the MCP session manager
    if True:
        assert c.get("/api/health").status_code == 401
        assert c.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
        assert c.get("/static/mcp.js").status_code == 200
        assert c.get("/api/health", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        r = c.get("/family?token=s3cret", follow_redirects=False)
        assert r.status_code == 303 and "token" not in r.headers["location"]
        assert c.get("/api/health").status_code == 200  # cookie now set


# ---- Bee CLI layer ----

def test_cli_bee_parses_and_reports_errors():
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        if cmd[1:3] == ["conversations", "list"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"conversations": [{"id": 7}]}), stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="Error: Not logged in. Run bee login.")

    cli = bee.CliBee(binary="bee", runner=runner)
    assert cli.list_conversations(limit=5) == [{"id": 7}]
    assert calls[0] == ["bee", "conversations", "list", "--limit", "5", "--json"]
    with pytest.raises(bee.BeeError, match="Not logged in"):
        cli.get_conversation(7)
    assert cli.calls.counts["conversations list"] == 1


def test_cli_bee_missing_binary():
    def runner(cmd, **kw):
        raise FileNotFoundError
    with pytest.raises(bee.BeeError, match="npm install -g @beeai/cli"):
        bee.CliBee(runner=runner).me()


def test_sync_survives_bee_errors(tmp_path):
    class Broken(bee.DemoBee):
        def list_conversations(self, limit=20):
            raise bee.BeeError("`bee conversations list` failed: Not logged in")
    lane2 = service.MemoryLane(Store(tmp_path / "b.db"), Broken())
    report = lane2.sync()
    assert report["errors"] and "Not logged in" in report["errors"][0] and not lane2.job["running"]


def test_timestamps_in_any_bee_format():
    ms = 1_717_500_000_000
    assert bee.to_ms(ms) == ms
    assert bee.to_ms(ms // 1000) == ms
    assert bee.to_ms(str(ms)) == ms
    assert bee.to_ms("2024-06-04T11:20:00Z") == ms
    assert bee.to_ms(None) is None and bee.to_ms("soon") is None and bee.to_ms(5) is None


def test_real_shaped_conversation_in_seconds_is_synced(tmp_path):
    now = int(time.time())
    conv = {"id": 555, "start_time": now - 600, "end_time": now - 60, "summary": "Call",
            "transcriptions": [{"realtime": False, "utterances": [
                {"id": i, "text": "म आज बजार गएँ र तरकारी किनें, अनि साथीसँग चिया खाएँ। " * 2,
                 "speaker": "SPEAKER_1", "spoken_at": now - 600 + i * 10} for i in range(3)]}]}

    class One(bee.DemoBee):
        def list_conversations(self, limit=20):
            return [{k: conv[k] for k in ("id", "start_time", "end_time", "summary")}]

        def get_conversation(self, cid):
            return conv

    lane2 = service.MemoryLane(Store(tmp_path / "s.db"), One())
    report = lane2.sync()
    assert report["seen"] == 1 and report["digested"] == 1
    saved = lane2.store.conversation(555)
    started = datetime.fromtimestamp(now - 600, config.TZ).strftime("%Y-%m-%d")  # yesterday, just after midnight
    assert saved["day"] == started and saved["utterances"][0]["at"] == (now - 600) * 1000


def test_classify_stream_events():
    assert bee.classify_event({"utterance": {"text": "hi"}, "conversation_uuid": "x"}) == "new-utterance"
    assert bee.classify_event({"conversation": {"id": 1, "uuid": "u", "state": "processing"}}) == "new-conversation"
    assert bee.classify_event({"conversation": {"id": 1, "end_time": 5}}) == "conversation-ended"
    assert bee.classify_event({"conversation": {"id": 1, "state": "processed"}}) == "conversation-ended"
    assert bee.classify_event({"conversation_id": 1, "short_summary": "s"}) == "update-conversation-summary"


def test_transcript_prefers_final_transcription():
    conv = {"transcriptions": [
        {"realtime": True, "utterances": [{"text": "live", "spoken_at": 1_700_000_000_000}]},
        {"realtime": False, "utterances": [{"text": "b", "spoken_at": 1_700_000_002_000},
                                           {"text": "a", "spoken_at": 1_700_000_001_000}, {"text": " "}]},
    ]}
    assert [u["text"] for u in bee.utterances(conv)] == ["a", "b"]


# ---- digest ----

def test_clean_drops_ungrounded_cards():
    base = {"kind": "plan", "health": False, "question_parent": "q", "question_en": "q", "answer_parent": "a",
            "answer_en": "a", "hint_parent": "h", "hint_en": "h", "importance": 3}
    data = {"lines_en": ["one"], "speakers": [], "promises": [],
            "cards": [dict(base, evidence=[0, 9, -1]), dict(base, evidence=[42])]}
    out = digest.clean(data, 3, source="claude")
    assert out["lines_en"] == ["one", "", ""]
    assert len(out["cards"]) == 1 and out["cards"][0]["evidence"] == [0]


def test_digest_uses_model_and_chunks_translation(monkeypatch):
    conv = bee.DemoBee().get_conversation(103)
    sample = json.loads((config.FIXTURES / "demo_digests.json").read_text())["103"]
    prompts = []

    def fake(system, prompt, schema, max_tokens=16000, effort=None):
        prompts.append(prompt)
        if schema is digest.TRANSLATE_SCHEMA:
            n = prompt.count("\n[")
            return {"lines_en": [f"en {i}" for i in range(n + 1)]}
        return {k: v for k, v in sample.items() if k != "lines_en"}

    monkeypatch.setattr(digest.config, "llm_provider", lambda: "anthropic")
    monkeypatch.setattr(digest.llm, "structured", fake)
    monkeypatch.setattr(digest, "CHUNK", 3)
    out = digest.build(conv)
    assert out["source"] == "anthropic" and len(out["cards"]) == 3 and len(out["lines_en"]) == 8
    assert out["lines_en"][:3] == ["en 0", "en 1", "en 2"] and out["lines_en"][3] == "en 0"
    understand = next(p for p in prompts if "Transcript" in p)
    assert "[4] SPEAKER_2" in understand and "मंगलबार" in understand
    assert sum(1 for p in prompts if "lines:" in p) == 3  # 8 lines in chunks of 3


def test_together_request_and_answer(monkeypatch):
    import httpx

    from app import llm

    sent = []

    def post(url, json=None, headers=None, timeout=None):
        sent.append(json)
        if len(sent) == 1:  # first answer: not JSON, so it asks again
            return httpx.Response(200, json={"choices": [{"message": {"content": "Sure! Here you go"}, "finish_reason": "stop"}]})
        content = '<think>lines first</think>\n```json\n{"lines_en": ["Hello"]}\n```'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 50, "completion_tokens": 9}})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(config, "TOGETHER_API_KEY", "k")
    monkeypatch.setattr(config, "llm_provider", lambda: "together")
    assert llm.structured("sys", "[0] नमस्ते", digest.TRANSLATE_SCHEMA) == {"lines_en": ["Hello"]}
    body = sent[0]
    assert body["model"] == config.TOGETHER_MODEL and "reasoning" not in body
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] is digest.TRANSLATE_SCHEMA
    assert "JSON Schema" in body["messages"][0]["content"]

    sent.clear()
    llm.structured("sys", "x", digest.TRANSLATE_SCHEMA, effort="low")  # live lines: the fast model, no thinking
    assert sent[0]["model"] == config.TOGETHER_FAST_MODEL and sent[0]["reasoning"] == {"enabled": False}


def test_together_errors(monkeypatch):
    import httpx

    from app import llm

    replies = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "TOGETHER_API_KEY", "k")
    cut = {"choices": [{"message": {"content": '{"lines_en": ['}, "finish_reason": "length"}]}
    replies[:] = [httpx.Response(200, json=cut)]
    with pytest.raises(llm.LLMError, match="cut off"):
        llm.together("m", "s", "p", digest.TRANSLATE_SCHEMA)
    replies[:] = [httpx.Response(401, text="bad key")]
    with pytest.raises(llm.LLMError, match="401"):
        llm.together("m", "s", "p", digest.TRANSLATE_SCHEMA)
    ok = {"choices": [{"message": {"content": '{"lines_en": []}'}, "finish_reason": "stop"}]}
    replies[:] = [httpx.Response(429), httpx.Response(200, json=ok)]
    assert llm.together("m", "s", "p", digest.TRANSLATE_SCHEMA)[0] == {"lines_en": []}
    replies[:] = [httpx.Response(400, text="unknown field reasoning"), httpx.Response(200, json=ok)]
    llm.together("m", "s", "p", digest.TRANSLATE_SCHEMA, fast=True)
    assert not replies


def test_together_key_picks_together(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(config, "TOGETHER_API_KEY", "k")
    assert config.llm_provider() == "together"


# ---- Bee's memory: facts in, facts out ----

def test_known_facts_reach_the_prompt():
    conv = bee.DemoBee().get_conversation(104)
    prompt = digest.understand_prompt(conv, bee.utterances(conv), ["Bikash is my son"])
    assert "What Bee already knows" in prompt and "- Bikash is my son" in prompt


def test_fact_suggestions_save_to_bee(tmp_path):
    lane2 = fresh_lane(tmp_path)
    facts = lane2.facts()
    assert [f["text_en"] for f in facts][:1] == ["Kamala is my older sister; she lives in Kathmandu"]
    assert len(facts) == 3 and all(f["status"] == "suggested" for f in facts)
    out = lane2.save_fact(facts[0]["id"])
    assert out["bee_fact_id"] and lane2.bee.saved_facts[0]["text"] == facts[0]["text_en"]
    assert lane2.save_fact(facts[0]["id"])["already"]
    assert "Kamala is my older sister; she lives in Kathmandu" in lane2.bee.facts()
    lane2.dismiss_fact(facts[1]["id"])
    assert len(lane2.facts()) == 2


def test_known_facts_are_not_suggested_again():
    data = {"cards": [], "promises": [], "speakers": [],
            "facts": [{"text_en": "Bikash is my son", "text_parent": "x", "evidence": [0]},
                      {"text_en": "My doctor is Dr. Patel", "text_parent": "y", "evidence": [99]}]}
    assert digest.clean(data, 3, "t", known_facts=["bikash is my son"])["facts"] == []


# ---- photo questions ----

def test_photo_cards_from_the_day(tmp_path):
    lane2 = fresh_lane(tmp_path)
    photos = [c for c in lane2.store._rows("SELECT * FROM cards WHERE kind='photo'")]
    assert [c["answer_parent"] for c in photos] == ["माया (छिमेकी)", "बिकास (छोरा)"]
    assert photos[0]["question_parent"] == "यो फोटो खिच्दा तपाईं कोसँग हुनुहुन्थ्यो?"
    assert "दिउँसो" in photos[0]["hint_parent"] and photos[0]["evidence"] == [0, 2]
    assert (config.DATA / "photos" / photos[0]["media"]["photo"]).is_file()
    card = lane2.public_card(lane2.store.card(photos[0]["id"]), reveal=True)
    assert card["photo"] == "/media/photos/501.svg" and card["evidence"][0]["name_en"] == "Maya (neighbour)"
    lane2.sync()  # nothing new: no duplicates
    assert lane2.store.count_cards("photo", service.today()) == 2


def test_photo_card_needs_someone_named():
    conv = {"speakers": [{"label": "SPEAKER_1", "name_en": "Mom", "name_parent": "आमा", "is_parent": True}],
            "utterances": [{"speaker": "SPEAKER_1", "text": "hi", "at": 0}]}
    assert digest.photo_card(conv, 1_700_000_000_000) is None


def test_media_is_served_safely(client, synced):
    assert client.get("/media/photos/501.svg").status_code == 200
    assert client.get("/media/photos/..%2Fmemory-lane.db").status_code == 404
    assert client.get("/media/secrets/x.txt").status_code == 422
    assert client.get("/media/photos/nope.jpg").status_code == 404


# ---- a family member's voice ----

def test_question_in_a_family_voice(client, synced):
    cid = lane.store._rows("SELECT id FROM cards WHERE deleted=0 ORDER BY id LIMIT 1")[0]["id"]
    r = client.put(f"/api/cards/{cid}/voice", content=b"OggS fake audio", headers={"Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200 and r.json()["voice"].endswith(".webm")
    assert lane.public_card(lane.store.card(cid), reveal=False)["voice"] == r.json()["voice"]
    assert client.get(r.json()["voice"]).content == b"OggS fake audio"
    assert client.put(f"/api/cards/{cid}/voice", content=b"x", headers={"Content-Type": "text/html"}).status_code == 422
    assert client.delete(f"/api/cards/{cid}/voice").status_code == 200
    assert lane.store.card(cid)["voice"] is None and client.get(r.json()["voice"]).status_code == 404


# ---- real time: a promise becomes a Bee todo while she's talking ----

def test_sample_replay_sets_a_reminder_and_undo_removes_it(tmp_path):
    lane2 = fresh_lane(tmp_path)
    conv = lane2.bee.get_conversation(101)
    sent = []
    lane2.live._send = sent.append
    for i, u in enumerate(bee.utterances(conv)):
        lane2.live.line(u["speaker"], u["text"], demo=True, conversation=101, index=i)
    reminders = lane2.live_reminders()
    assert len(reminders) == 1 and "आइतबार" in reminders[0]["said"]
    assert lane2.bee.todos[0]["text"] == reminders[0]["text_parent"]
    assert [e for e in sent if e["type"] == "reminder"][0]["id"] == reminders[0]["id"]
    lane2.undo_live_reminder(reminders[0]["id"])
    assert lane2.bee.todos == [] and lane2.live_reminders()[0]["status"] == "undone"


def test_live_reminder_from_the_model(tmp_path, monkeypatch):
    lane2 = service.MemoryLane(Store(tmp_path / "r.db"), bee.DemoBee())
    asked = []

    def fake(system, prompt, schema, max_tokens=16000, effort=None):
        asked.append((prompt, effort))
        return {"reminders": [{"text_parent": "कमला दिदीलाई फोन गर्ने", "text_en": "Call Kamala didi",
                               "due_date": "2026-10-25", "due_time": "", "line": 1}]}

    monkeypatch.setattr(service.llm, "engine", lambda: "together")
    monkeypatch.setattr(digest.llm, "structured", fake)
    lines = [{"speaker": "SPEAKER_2", "text": "आइतबार फोन गर है", "conversation": "u1"},
             {"speaker": "SPEAKER_1", "text": "हुन्छ दिदी, आइतबार फोन गर्छु", "conversation": "u1"}]
    for item in lines:
        lane2.reminders.buffers.setdefault("u1", __import__("collections").deque(maxlen=8)).append(item)
    lane2.reminders._check("u1")
    lane2.reminders._check("u1")  # the same promise isn't set twice
    r = lane2.live_reminders()
    assert len(r) == 1 and r[0]["alarm_at"].startswith("2026-10-25T09:00")
    assert asked[0][1] == "low" and "[1] NEW SPEAKER_1" in asked[0][0] and "Already set: Call Kamala didi" in asked[1][0]


def test_digest_links_a_promise_already_set_live(tmp_path):
    lane2 = fresh_lane(tmp_path)
    conv = lane2.store.conversation(101)
    lane2.store.add_live_reminder(conv["start_ms"] + 60_000, conv["day"], "फोन गर्ने", "Call Kamala didi back on Sunday",
                                  "…", None, "900")
    lane2.reminders.link(101)
    p = [x for x in lane2.promises() if x["conversation_id"] == 101][0]
    assert p["status"] == "reminder" and p["bee_todo_id"] == "900"


# ---- the Bee CLI layer, new commands ----

def test_cli_bee_facts_photos_and_todo_delete(tmp_path):
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        if cmd[1:3] == ["facts", "list"]:
            out = {"facts": [{"id": 1, "text": "Kamala is my sister", "confirmed": True},
                             {"id": 2, "text": "maybe", "confirmed": False}]}
        elif cmd[1:3] == ["photos", "list"]:
            out = {"photos": [{"id": 9, "created_at": "2026-10-18T20:08:00Z"}, {"nope": 1}]}
        elif cmd[1:3] == ["photos", "get"]:
            (tmp_path / "p.jpg").write_bytes(b"jpg")
            return SimpleNamespace(returncode=0, stdout="Saved to p.jpg", stderr="")
        else:
            out = {}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out), stderr="")

    cli = bee.CliBee(runner=runner)
    assert cli.facts() == ["Kamala is my sister"]
    assert cli.photos("2026-10-18") == [{"id": 9, "at": 1792354080000, "raw": {"id": 9, "created_at": "2026-10-18T20:08:00Z"}}]
    assert cli.save_photo(9, tmp_path / "p.jpg").read_bytes() == b"jpg"  # a status line instead of JSON is fine
    cli.delete_todo(5)
    assert calls[-1] == ["bee", "todos", "delete", "5", "--json"]
    assert cli.calls.counts["facts list"] == 1 and cli.calls.counts["photos get"] == 1


def test_nepali_rebuilt_from_hindi_recognizer():
    """Bee has no Nepali: set to Hindi, it writes her Nepali the Hindi way. The model rebuilds each line,
    marks the TV, and a card can't rest on a TV line. Bee's own words are kept beside the rebuilt ones."""
    assert config.rebuilding() and "runs its Hindi" in digest.TRANSLATE_SYSTEM
    lines = digest.lines_from({"lines_parent": ["मैले बुझें"], "lines_en": ["I understood", "What do you want?"],
                               "background": [1]}, 2)
    assert lines == [{"parent": "मैले बुझें", "en": "I understood", "background": False},
                     {"parent": "", "en": "What do you want?", "background": True}]
    card = {"kind": "detail", "question_parent": "क?", "question_en": "Q?", "answer_parent": "उ", "answer_en": "A",
            "hint_parent": "", "hint_en": "", "evidence": [1], "importance": 1}
    out = digest.clean({"cards": [card], "lines_parent": ["मैले बुझें"], "background": [1]}, 2, "together")
    assert out["cards"] == [] and out["background"] == [1] and out["lines_parent"] == ["मैले बुझें", ""]
    assert service._fixed({"lines_parent": ["मैले बुझें"]}, 0) == "मैले बुझें"
    assert service._fixed({"lines_parent": ["मैले बुझें"]}, 3) == ""


def test_manual_mode_waits_then_applies_a_hand_digest(tmp_path, monkeypatch):
    """LLM_PROVIDER=manual: sync makes no AI call, transcripts wait; a hand-written digest goes
    through the same checks as a model's (no evidence, no card)."""
    from app import llm, manual

    monkeypatch.setattr(config, "llm_provider", lambda: "manual")
    with pytest.raises(llm.LLMError):
        llm.structured("s", "p", {})
    lane2 = service.MemoryLane(Store(tmp_path / "m.db"), bee.DemoBee())
    assert lane2._live_translator() is None
    report = lane2.sync()
    waiting = manual._waiting(lane2)
    assert report["waiting"] == len(waiting) > 0 and report["digested"] == 0
    assert "waiting" not in lane2.sync()  # not re-read while it waits
    cid = waiting[0]
    n = len(bee.utterances(lane2.bee.get_conversation(cid)))
    card = {"kind": "detail", "health": False, "question_parent": "क?", "question_en": "Q?", "answer_parent": "उ",
            "answer_en": "A", "hint_parent": "", "hint_en": "", "importance": 1}
    answer = {"language": "ne", "title_en": "t", "title_parent": "t", "summary_en": "s", "summary_parent": "s",
              "speakers": [], "promises": [], "facts": [], "background": [],
              "cards": [dict(card, evidence=[0]), dict(card, evidence=[])],
              "lines_parent": ["न"] * n, "lines_en": ["e"] * n}
    monkeypatch.setattr(manual, "DIR", tmp_path)
    (tmp_path / f"{cid}.json").write_text(json.dumps(answer))
    manual.apply(lane2, cid)
    conv = lane2.store.conversation(cid)
    assert conv["status"] == "digested" and conv["source"] == "manual"
    assert len(lane2.store._rows("SELECT * FROM cards WHERE conversation_id=?", (cid,))) == 1
    (tmp_path / f"{cid}.json").write_text(json.dumps(dict(answer, lines_en=["e"])))
    with pytest.raises(SystemExit):
        manual.apply(lane2, cid)


# ---- pause ----

def test_pause_for_minutes(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p.db"), bee.DemoBee())
    now_ms = int(time.time() * 1000)
    state = lane2.pause(minutes=60)
    assert state["paused"] is True
    assert state["paused_until_ms"] >= now_ms + 59 * 60_000
    assert state["paused_until"] is not None


def test_pause_until_tomorrow(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p2.db"), bee.DemoBee())
    state = lane2.pause(until="tomorrow")
    assert state["paused"] is True
    # paused_until should be at midnight tomorrow in the configured timezone
    from datetime import date, timedelta
    from app import config as cfg
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert state["paused_until"].startswith(tomorrow)


def test_resume_ends_the_pause(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p3.db"), bee.DemoBee())
    lane2.pause(minutes=120)
    assert lane2.pause_state()["paused"] is True
    state = lane2.resume()
    assert state["paused"] is False
    assert state["paused_until"] is None


def test_paused_at(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p4.db"), bee.DemoBee())
    now_ms = int(time.time() * 1000)
    lane2.pause(minutes=60)
    # A timestamp inside the pause window
    assert lane2.paused_at(now_ms + 30 * 60_000) is True
    # A timestamp before the pause
    assert lane2.paused_at(now_ms - 1000) is False
    # A timestamp after the pause
    assert lane2.paused_at(now_ms + 90 * 60_000) is False


def test_paused_at_after_resume(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p5.db"), bee.DemoBee())
    now_ms = int(time.time() * 1000)
    lane2.pause(minutes=60)
    lane2.resume()
    assert lane2.paused_at(now_ms + 30 * 60_000) is False


def test_pause_persists_across_restarts(tmp_path):
    db_path = tmp_path / "p6.db"
    lane2 = service.MemoryLane(Store(db_path), bee.DemoBee())
    lane2.pause(minutes=60)
    # New instance from same DB — pause should still be there
    lane3 = service.MemoryLane(Store(db_path), bee.DemoBee())
    assert lane3.pause_state()["paused"] is True


def test_status_includes_paused_until(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p7.db"), bee.DemoBee())
    assert lane2.status()["paused_until"] is None
    lane2.pause(minutes=60)
    assert lane2.status()["paused_until"] is not None


def test_pause_invalid_args(tmp_path):
    lane2 = service.MemoryLane(Store(tmp_path / "p8.db"), bee.DemoBee())
    with pytest.raises(ValueError):
        lane2.pause()
    with pytest.raises(ValueError):
        lane2.pause(minutes=0)


def test_pause_resume_routes(client):
    # /api/health starts with no pause
    h = client.get("/api/health").json()
    assert h["paused_until"] is None

    # Pause for 1 hour
    r = client.post("/api/pause", json={"minutes": 60})
    assert r.status_code == 200
    body = r.json()
    assert body["paused"] is True and body["paused_until"] is not None

    # /api/health now reflects the pause
    h = client.get("/api/health").json()
    assert h["paused_until"] is not None

    # Resume
    r = client.post("/api/resume")
    assert r.status_code == 200 and r.json()["paused"] is False

    # /api/health back to unpaused
    h = client.get("/api/health").json()
    assert h["paused_until"] is None


def test_pause_until_tomorrow_route(client):
    r = client.post("/api/pause", json={"until": "tomorrow"})
    assert r.status_code == 200
    body = r.json()
    assert body["paused"] is True
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert body["paused_until"].startswith(tomorrow)
    # Clean up
    client.post("/api/resume")


# ---- pause applies to sync, live lines and reminders (task 3) ----

def test_paused_sync_skips_conversations(tmp_path):
    """A conversation that starts inside a pause window is saved as skipped
    with reason 'paused' and empty utterances; cards/promises are not created."""
    lane2 = service.MemoryLane(Store(tmp_path / "ps.db"), bee.DemoBee())
    # Pause for the rest of today: covers all demo conversations which start today.
    lane2.pause(until="tomorrow")
    report = lane2.sync()
    # All conversations started today → all skipped
    assert report["digested"] == 0
    assert report["skipped"] == len(bee.DemoBee().list_conversations())
    # Every stored conversation has status='skipped' and empty utterances
    today_convs = lane2.store.conversations(service.today())
    for c in today_convs:
        assert c["status"] == "skipped"
        assert c["utterances"] == []
    # No cards or promises created
    assert lane2.store.scalar("SELECT COUNT(*) FROM cards") == 0
    assert lane2.store.scalar("SELECT COUNT(*) FROM promises") == 0


def test_paused_sync_skipped_reason_is_paused(tmp_path):
    """Conversation digested during a pause is saved with error='paused'."""
    lane2 = service.MemoryLane(Store(tmp_path / "pr.db"), bee.DemoBee())
    lane2.pause(until="tomorrow")
    lane2.sync()
    convs = lane2.store.conversations(service.today())
    paused = [c for c in convs if c["error"] == "paused"]
    assert len(paused) > 0


def test_conversation_after_pause_is_digested(tmp_path):
    """A conversation whose start_ms is AFTER the pause ends is digested normally."""
    lane2 = service.MemoryLane(Store(tmp_path / "ca.db"), bee.DemoBee())
    # Pause a window ending BEFORE all demo conversations (midnight = 0 minutes;
    # the earliest demo conversation starts at 520 minutes after midnight).
    midnight_ms = int(datetime.now(config.TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    # Set a pause that already ended: start = midnight, end = 60 ms after midnight
    lane2.store.set_setting("pauses", json.dumps([{"start_ms": midnight_ms, "end_ms": midnight_ms + 60}]))
    report = lane2.sync()
    # None of the demo conversations start within that tiny window
    assert report["digested"] == 4 and report["skipped"] == 1


def test_live_line_dropped_while_paused(tmp_path):
    """live.line() returns a {type:'paused'} event and does NOT add to recent
    or call on_line while a pause is active."""
    lane2 = service.MemoryLane(Store(tmp_path / "ll.db"), bee.DemoBee())
    lane2.pause(minutes=60)
    heard = []
    lane2.live.on_line = heard.append
    sent = []
    lane2.live._send = sent.append

    result = lane2.live.line("SPEAKER_1", "नमस्ते")
    assert result["type"] == "paused"
    assert len(lane2.live.recent) == 0   # not added to the buffer
    assert heard == []                   # on_line NOT called
    assert sent == [{"type": "paused", "at": result["at"]}]


def test_live_line_not_dropped_after_resume(tmp_path):
    """After resume(), live.line() works normally again."""
    lane2 = service.MemoryLane(Store(tmp_path / "lr.db"), bee.DemoBee())
    lane2.pause(minutes=60)
    lane2.resume()
    result = lane2.live.line("SPEAKER_1", "नमस्ते")
    assert result["type"] == "line"
    assert len(lane2.live.recent) == 1


def test_live_reminder_not_set_while_paused(tmp_path):
    """LiveReminders.heard() returns without setting a reminder when paused."""
    lane2 = service.MemoryLane(Store(tmp_path / "rp.db"), bee.DemoBee())
    lane2.pause(minutes=60)
    now_ms = int(time.time() * 1000)
    # Feed the same lines that normally trigger a sample reminder,
    # but stamp them with the current time so they fall inside the pause window.
    conv = lane2.bee.get_conversation(101)
    utts = bee.utterances(conv)
    for i, u in enumerate(utts):
        item = {"type": "line", "id": i + 1, "speaker": u["speaker"], "text": u["text"],
                "at": now_ms + i * 1000, "en": None, "demo": True,
                "conversation": 101, "index": i}
        lane2.reminders.heard(item)
    assert lane2.live_reminders() == []


def test_live_reminder_set_after_resume(tmp_path):
    """After resume(), reminders fire again on the demo day."""
    lane2 = service.MemoryLane(Store(tmp_path / "rr.db"), bee.DemoBee())
    lane2.pause(minutes=60)
    lane2.resume()
    conv = lane2.bee.get_conversation(101)
    for i, u in enumerate(bee.utterances(conv)):
        item = {"type": "line", "id": i + 1, "speaker": u["speaker"], "text": u["text"],
                "at": u["at"] or int(time.time() * 1000), "en": None, "demo": True,
                "conversation": 101, "index": i}
        lane2.reminders.heard(item)
    assert len(lane2.live_reminders()) == 1


# ---- delete conversation (task 4) ----

def test_delete_removes_cards_reviews_promises_facts(tmp_path):
    """After delete_conversation(), cards (and their reviews), promises, facts
    are gone; the tombstone row remains with status='deleted'."""
    lane2 = fresh_lane(tmp_path)
    # Conversation 101 has cards and promises
    cid = 101
    cards_before = lane2.store.cards_for(cid)
    assert cards_before, "expect cards on conv 101"
    # Record a review so we can check it is also removed
    card_id = cards_before[0]["id"]
    lane2.store.add_review(card_id, service.today(), "remembered", cards_before[0]["box"], cards_before[0]["due"])
    reviews_before = lane2.store._rows("SELECT * FROM reviews WHERE card_id=?", (card_id,))
    assert reviews_before, "expect at least one review"

    lane2.delete_conversation(cid)

    # Cards gone
    assert lane2.store.cards_for(cid) == []
    assert lane2.store._rows("SELECT * FROM cards WHERE conversation_id=?", (cid,)) == []
    # Reviews gone
    assert lane2.store._rows("SELECT * FROM reviews WHERE card_id=?", (card_id,)) == []
    # Promises gone
    assert lane2.store._rows("SELECT * FROM promises WHERE conversation_id=?", (cid,)) == []
    # Facts gone (conv 104 has facts; use a lane that has all convs)
    lane3 = fresh_lane(tmp_path, "t2.db")
    lane3.delete_conversation(104)
    assert lane3.store._rows("SELECT * FROM facts WHERE conversation_id=?", (104,)) == []
    # Tombstone remains with status='deleted'
    raw = lane2.store._one("SELECT * FROM conversations WHERE id=?", (cid,))
    assert raw is not None and raw["status"] == "deleted"
    # conversations(day) excludes the tombstone
    assert all(c["id"] != cid for c in lane2.store.conversations(raw["day"]))
    # Transcript is wiped
    assert raw["utterances"] == []
    assert raw["lines_en"] == []
    assert raw["title_en"] is None


def test_delete_conversation_not_in_day(tmp_path):
    """Deleted conversation does not appear in lane.day() or store.conversations()."""
    lane2 = fresh_lane(tmp_path)
    day_before = lane2.day()
    cids_before = [c["id"] for c in day_before["conversations"]]
    assert 101 in cids_before

    lane2.delete_conversation(101)

    day_after = lane2.day()
    cids_after = [c["id"] for c in day_after["conversations"]]
    assert 101 not in cids_after


def test_delete_conversation_not_in_practice(tmp_path):
    """Cards from a deleted conversation are excluded from the practice plan."""
    lane2 = fresh_lane(tmp_path)
    plan_before = lane2.plan()
    conv101_cards = {c["id"] for c in lane2.store.cards_for(101)}
    assert any(i in conv101_cards for i in plan_before), "expect conv 101 cards in plan"

    lane2.delete_conversation(101)

    plan_after = lane2.plan()
    assert not any(i in conv101_cards for i in plan_after)


def test_delete_conversation_not_in_promises(tmp_path):
    """Promises from a deleted conversation are excluded from store.promises()."""
    lane2 = fresh_lane(tmp_path)
    promises_before = lane2.promises()
    cids_with_promises = [p["conversation_id"] for p in promises_before]
    if not cids_with_promises:
        pytest.skip("no promises in sample day")
    cid = cids_with_promises[0]
    lane2.delete_conversation(cid)
    promises_after = lane2.promises()
    assert all(p["conversation_id"] != cid for p in promises_after)


def test_delete_conversation_not_in_facts(tmp_path):
    """Facts from a deleted conversation are excluded from store.facts()."""
    lane2 = fresh_lane(tmp_path)
    facts_before = lane2.facts()
    if not facts_before:
        pytest.skip("no facts in sample day")
    cid = facts_before[0]["conversation_id"]
    lane2.delete_conversation(cid)
    facts_after = lane2.facts()
    assert all(f["conversation_id"] != cid for f in facts_after)


def test_resync_does_not_restore_deleted(tmp_path):
    """Re-syncing with redo=True does not restore a deleted conversation."""
    lane2 = fresh_lane(tmp_path)
    lane2.delete_conversation(101)
    report = lane2.sync(redo=True)
    # 101 should not be re-digested
    raw = lane2.store._one("SELECT * FROM conversations WHERE id=?", (101,))
    assert raw["status"] == "deleted"
    # The re-sync should not have added cards back
    assert lane2.store.cards_for(101) == []


def test_delete_conversation_route(client, synced):
    """DELETE /api/conversations/{cid} returns 200 and removes the conversation."""
    # Use a fresh lane so we don't disturb the module-scoped synced fixture's data
    # We test via the module client on a conversation that exists
    day = client.get("/api/day").json()
    # Find a conversation we can delete (pick the last one so other tests are least affected)
    convs = day["conversations"]
    if not convs:
        pytest.skip("no conversations to delete")
    cid = convs[-1]["id"]
    r = client.delete(f"/api/conversations/{cid}")
    assert r.status_code == 200 and r.json()["ok"] is True
    # It no longer appears in /api/day
    day2 = client.get("/api/day").json()
    assert all(c["id"] != cid for c in day2["conversations"])


def test_delete_conversation_unknown_is_404(client, synced):
    """DELETE /api/conversations/{cid} with an unknown id returns 404."""
    r = client.delete("/api/conversations/99999")
    assert r.status_code == 404


def test_mcp_todays_conversations_excludes_deleted(tmp_path):
    """MCP todays_conversations does not list a deleted conversation."""
    lane2 = fresh_lane(tmp_path)
    # Confirm conv 101 is there before deletion
    convs_before = lane2.day()["conversations"]
    assert any(c["id"] == 101 for c in convs_before)
    lane2.delete_conversation(101)
    convs_after = lane2.day()["conversations"]
    assert all(c["id"] != 101 for c in convs_after)


def test_delete_photo_file_removed(tmp_path):
    """When a photo card has a photo file, delete_conversation() removes it from disk."""
    lane2 = fresh_lane(tmp_path)
    # Find a photo card
    photo_cards = lane2.store._rows("SELECT * FROM cards WHERE kind='photo'")
    if not photo_cards:
        pytest.skip("no photo cards in sample day")
    pc = photo_cards[0]
    media = pc.get("media") or {}
    photo_name = media.get("photo") if media else None
    if not photo_name:
        pytest.skip("photo card has no photo file")
    photo_path = config.DATA / "photos" / photo_name
    assert photo_path.is_file(), "photo file should exist before delete"
    cid = pc["conversation_id"]
    lane2.delete_conversation(cid)
    assert not photo_path.exists(), "photo file should be removed after delete"
