"""The Vouch web server.

Start it from the project folder (Bifrost must already be running):
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000
Then open http://localhost:8000
"""
import asyncio
import json
import queue
import threading
from datetime import datetime
from pathlib import Path

import httpx
import openai
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from app.serialize import brief_to_dict  # noqa: E402
from vouch.draft import GOALS  # noqa: E402
from vouch.pipeline import make_brief  # noqa: E402
from vouch.research import ANGLES  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="Vouch")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


def _event(kind: str, data: dict) -> str:
    """One Server-Sent Event: the browser receives these as they happen."""
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


def _friendly(error: Exception) -> str:
    """Errors say what went wrong and how to fix it."""
    if isinstance(error, (openai.APIConnectionError, httpx.ConnectError)):
        return ("Can't reach the model gateway. Start Bifrost with "
                "scripts\\start_bifrost.py, then try again.")
    if isinstance(error, openai.RateLimitError):
        return "Both models are rate-limited right now. Wait a minute and try again."
    if isinstance(error, KeyError) and "TAVILY" in str(error):
        return "TAVILY_API_KEY is missing from .env. Run scripts\\set_keys.py."
    text = str(error)
    if "Unauthorized" in text or "401" in text:
        return "Tavily rejected the API key. Check TAVILY_API_KEY in .env."
    if "usage limit" in text.lower() or "432" in text:
        return "Tavily's free credits are used up for this month."
    if "valid JSON" in text:
        return "The model replied in a broken format twice. Try again."
    return f"Something failed while making the brief: {text[:200]}"


@app.get("/api/brief")
async def brief_stream(
    name: str = Query(..., min_length=1, max_length=80),
    kind: str = Query("company"),
    goal: str = Query("general"),
    meeting: str = Query(...),
    about: str = Query("", max_length=80),
):
    name = " ".join(name.split())
    about = " ".join(about.split())
    problems = []
    if kind not in ANGLES:
        problems.append(f"Choose company or person, not '{kind}'.")
    if goal not in GOALS:
        problems.append(f"Choose a meeting type from: {', '.join(GOALS)}.")
    try:
        meeting_at = datetime.fromisoformat(meeting)
    except ValueError:
        problems.append("Give the meeting date as YYYY-MM-DD.")

    events: queue.Queue = queue.Queue()

    def worker():
        try:
            b = make_brief(name, kind, meeting_at, goal, about=about,
                           on_step=lambda stage, data: events.put(("step", {"stage": stage, **data})))
            events.put(("brief", brief_to_dict(b)))
        except Exception as e:  # report every failure to the page, never hang
            events.put(("failure", {"message": _friendly(e)}))
        events.put(None)

    async def stream():
        if problems:
            yield _event("failure", {"message": " ".join(problems)})
            return
        threading.Thread(target=worker, daemon=True).start()
        while True:
            try:
                item = events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            if item is None:
                return
            yield _event(*item)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
