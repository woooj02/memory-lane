"""HTTP layer: the parent's evening screen, the family page, the how-it-works
page, a small REST API for the family page, a live feed (SSE), and the MCP
server at /mcp."""

from __future__ import annotations

import asyncio
import hmac
import json
import re
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bee, config, mcp_server
from .service import MemoryLane

lane = MemoryLane()
mcp = mcp_server.build(lane)
mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    lane.live.loop = asyncio.get_running_loop()
    lane.start_background()
    async with mcp.session_manager.run():
        yield
    lane.stop()


app = FastAPI(title="Memory Lane", lifespan=lifespan)


@app.middleware("http")
async def access(request: Request, call_next):
    """With ACCESS_TOKEN set, nothing is served without it (transcripts are private)."""
    token = config.ACCESS_TOKEN
    if not token or request.url.path.startswith("/static/"):
        return await call_next(request)
    given = request.query_params.get("token")
    if given and hmac.compare_digest(given, token):
        resp = RedirectResponse(request.url.remove_query_params("token"), status_code=303)
        resp.set_cookie("ml_token", token, httponly=True, samesite="strict", max_age=60 * 60 * 24 * 60,
                        secure=request.url.scheme == "https")
        return resp
    auth = request.headers.get("authorization", "")
    bearer = auth[7:] if auth.lower().startswith("bearer ") else ""
    cookie = request.cookies.get("ml_token", "")
    if hmac.compare_digest(bearer, token) or hmac.compare_digest(cookie, token):
        return await call_next(request)
    return JSONResponse({"detail": "Open the link with ?token=... first."}, status_code=401)


def _guard(fn, *args):
    try:
        return fn(*args)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except bee.BeeError as exc:
        raise HTTPException(502, f"Bee: {exc}") from exc


NO_CACHE = {"Cache-Control": "no-cache"}  # pages change while we work; always revalidate


@app.get("/")
def evening():
    return FileResponse(config.WEB / "index.html", headers=NO_CACHE)


@app.get("/family")
def family():
    return FileResponse(config.WEB / "family.html", headers=NO_CACHE)


@app.get("/how")
def how():
    return FileResponse(config.WEB / "how.html", headers=NO_CACHE)


@app.get("/notice")
def notice():
    return FileResponse(config.WEB / "notice.html", headers=NO_CACHE)


@app.get("/api/health")
def health():
    return {"ok": True, **lane.status()}


@app.get("/api/stats")
def stats():
    return lane.stats()


@app.post("/api/sync")
def sync(redo: bool = False):
    return lane.start_sync(redo)


@app.get("/api/day")
def day(day: str | None = None):
    return lane.day(day)


class Private(BaseModel):
    private: bool


class Pause(BaseModel):
    minutes: int | None = None
    until: str | None = None


@app.post("/api/pause")
def pause(body: Pause):
    return _guard(lane.pause, body.minutes, body.until)


@app.post("/api/resume")
def resume():
    return lane.resume()


@app.post("/api/conversations/{cid}/private")
def set_private(cid: int, body: Private):
    lane.set_private(cid, body.private)
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: int):
    _guard(lane.delete_conversation, cid)
    return {"ok": True}


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: int):
    _guard(lane.delete_card, card_id)
    return {"ok": True}


@app.post("/api/cards/{card_id}/approve")
def approve_card(card_id: int):
    return _guard(lane.approve_card, card_id)


@app.get("/api/pending")
def pending():
    return {"cards": lane.pending()}


@app.get("/api/practice")
def practice():
    nxt = lane.practice_state()
    return {"state": nxt, "outline": lane.outline()}


class Result(BaseModel):
    result: Literal["remembered", "hint", "forgot"]


@app.post("/api/cards/{card_id}/result")
def record(card_id: int, body: Result):
    return _guard(lane.record, card_id, body.result)


@app.post("/api/practice/reset")
def reset_practice():
    return lane.reset_practice()


@app.get("/api/promises")
def promises():
    return {"promises": lane.promises()}


@app.post("/api/promises/{pid}/remind")
def remind(pid: int):
    return _guard(lane.remind, pid)


@app.post("/api/promises/{pid}/dismiss")
def dismiss(pid: int):
    _guard(lane.dismiss, pid)
    return {"ok": True}


@app.get("/api/progress")
def progress(days: int = 14):
    return lane.progress(max(1, min(days, 90)))


@app.post("/api/demo/replay/{cid}")
def demo_replay(cid: int):
    if lane.bee.mode != "demo":
        raise HTTPException(409, "Replay is only for the sample day.")
    lane.replay_demo(cid)
    return {"ok": True}


@app.get("/api/facts")
def facts():
    return {"facts": lane.facts()}


@app.post("/api/facts/{fid}/save")
def save_fact(fid: int):
    return _guard(lane.save_fact, fid)


@app.post("/api/facts/{fid}/dismiss")
def dismiss_fact(fid: int):
    _guard(lane.dismiss_fact, fid)
    return {"ok": True}


@app.get("/api/reminders")
def live_reminders():
    return {"reminders": lane.live_reminders()}


@app.post("/api/reminders/{rid}/undo")
def undo_reminder(rid: int):
    return _guard(lane.undo_live_reminder, rid)


@app.put("/api/cards/{card_id}/voice")
async def set_voice(card_id: int, request: Request):
    """The question in a family member's voice: the raw recording as the body."""
    data = await request.body()
    return _guard(lane.set_voice, card_id, data, request.headers.get("content-type", ""))


@app.delete("/api/cards/{card_id}/voice")
def clear_voice(card_id: int):
    _guard(lane.clear_voice, card_id)
    return {"ok": True}


@app.get("/media/{kind}/{name}")
def media(kind: Literal["photos", "voice"], name: str):
    """Photos and recordings, behind the same access token as everything else."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name) or name.startswith("."):
        raise HTTPException(404, "not found")
    path = config.DATA / kind / name
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/live")
async def live(request: Request):
    """Server-sent events: each line Bee hears, then its English when ready."""
    queue: asyncio.Queue = asyncio.Queue()
    lane.live.subscribers.add(queue)

    async def events():
        try:
            for item in list(lane.live.recent)[-12:]:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            while not await request.is_disconnected():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            lane.live.subscribers.discard(queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/static", StaticFiles(directory=config.WEB), name="static")
# Last, so it only sees what the routes above didn't take: POST /mcp.
app.mount("/", mcp_app)
