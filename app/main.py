"""The Vouch web server.

Start it from the project folder, with the .venv active (Bifrost must already be running):
    python -m uvicorn app.main:app --port 8000
Then open http://localhost:8000
"""
import asyncio
import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import openai
from tavily import errors as tavily_errors
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from app.serialize import brief_to_dict  # noqa: E402
from vouch.draft import GOALS  # noqa: E402
from vouch import gateway, store  # noqa: E402
from vouch.pipeline import Cancelled, make_brief  # noqa: E402
from vouch.research import ANGLES, meeting_problem  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"

# One brief at a time: each uses search credits and model quota, so a second
# request waits its turn instead of doubling the spend.
BUSY = threading.Semaphore(1)
HEARTBEAT_SECONDS = 15


class _Slot:
    """One request's hold on BUSY. Released by whichever finishes first: the
    worker, or the page going away. Releasing twice is harmless."""

    def __init__(self):
        self._held = False
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        self._held = BUSY.acquire(blocking=False)
        return self._held

    def release(self) -> None:
        with self._lock:
            if self._held:
                self._held = False
                BUSY.release()
app = FastAPI(title="Vouch")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/brief/{brief_id}")
def brief_page(brief_id: str):
    """A saved brief's own link: the same page, which loads it by id."""
    return FileResponse(STATIC / "index.html")


@app.get("/api/gateway")
def gateway_usage():
    """Today's usage of Vouch's Bifrost virtual key: requests, tokens, spend."""
    return gateway.usage()


@app.get("/api/briefs")
def list_briefs(limit: int = Query(50, ge=1, le=200)):
    return {"briefs": store.recent(limit)}


@app.get("/api/briefs/{brief_id}")
def get_brief(brief_id: str):
    brief = store.get(brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="No saved brief with that id.")
    return brief


def _event(kind: str, data: dict) -> str:
    """One Server-Sent Event: the browser receives these as they happen."""
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


def _bifrost_type(error: Exception) -> str:
    """Bifrost labels its own refusals ("request_limited", "token_limited", "budget_exceeded"...).

    The label sits at the top of Bifrost's reply, but the OpenAI library hands us only the
    inner "error" part as `body`, so read the full reply as well."""
    body = getattr(error, "body", None)
    if isinstance(body, dict) and body.get("type"):
        return str(body["type"])
    try:
        data = error.response.json()
    except Exception:
        return ""
    return str(data.get("type", "")) if isinstance(data, dict) else ""


def _friendly(error: Exception) -> str:
    """Errors say what went wrong and how to fix it, recognised by their type."""
    if isinstance(error, (tavily_errors.InvalidAPIKeyError, tavily_errors.MissingAPIKeyError)):
        return "Tavily rejected the API key. Check TAVILY_API_KEY in .env (run: python scripts/set_keys.py)."
    if isinstance(error, KeyError) and "TAVILY" in str(error):
        return "TAVILY_API_KEY is missing from .env. Run: python scripts/set_keys.py"
    if isinstance(error, tavily_errors.UsageLimitExceededError):
        return "Tavily's free credits are used up for this month."
    if isinstance(error, (tavily_errors.TimeoutError, TimeoutError)):
        return "The news search timed out. Try again in a moment."
    if isinstance(error, (tavily_errors.ForbiddenError, tavily_errors.BadRequestError)):
        return f"Tavily refused the search ({type(error).__name__}). Try a simpler name."
    if isinstance(error, openai.APITimeoutError):
        return "The model took too long to answer. Try again; Bifrost may switch to a faster model."
    if isinstance(error, (openai.APIConnectionError, httpx.ConnectError)):
        return ("Can't reach the model gateway. Start Bifrost with "
                "python scripts/start_bifrost.py, then try again.")
    if isinstance(error, openai.APIStatusError) and error.status_code == 402:
        return ("Vouch's daily model budget in Bifrost is used up. It resets tomorrow; "
                "the limit is set in bifrost/config.json.")
    if isinstance(error, openai.RateLimitError) and _bifrost_type(error) in ("request_limited", "token_limited"):
        return ("Vouch has reached its daily limit in Bifrost (bifrost/config.json: 1,000 requests, "
                "1,000,000 tokens a day). It resets tomorrow.")
    if isinstance(error, openai.RateLimitError):
        return "Every model is rate-limited right now. Wait a minute and try again."
    if isinstance(error, openai.APIStatusError):
        return f"The model gateway returned an error ({error.status_code}). Try again in a moment."
    if isinstance(error, RuntimeError):   # our own messages from vouch/llm.py
        return f"The model's answer couldn't be used: {error}. Try again."
    return f"Something failed while making the brief: {type(error).__name__}: {str(error)[:160]}"


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
    if not name:
        problems.append("Enter a company or person to brief on.")
    if kind not in ANGLES:
        problems.append(f"Choose company or person, not '{kind}'.")
    if goal not in GOALS:
        problems.append(f"Choose a meeting type from: {', '.join(GOALS)}.")
    try:
        meeting_at = datetime.fromisoformat(meeting)
    except ValueError:
        problems.append("Give the meeting date and time, for example 2026-11-14T10:30.")
    else:
        if problem := meeting_problem(meeting_at):
            problems.append(problem)

    events: queue.Queue = queue.Queue()
    cancel = threading.Event()   # set when the person closes the page
    slot = _Slot()               # this request's hold on BUSY, released exactly once

    def on_step(stage, data):
        if cancel.is_set():
            raise Cancelled()    # stop before the next paid step
        events.put(("step", {"stage": stage, **data}))

    def worker():
        try:
            b = make_brief(name, kind, meeting_at, goal, about=about, on_step=on_step)
            result = brief_to_dict(b)
            if not result["choices"]:            # a finished brief, not a which-one question
                result["id"] = store.save(result)
            events.put(("brief", result))
        except Cancelled:
            pass                 # nobody is listening any more
        except Exception as e:   # report every failure to the page, never hang
            events.put(("failure", {"message": _friendly(e)}))
        finally:
            slot.release()
            events.put(None)

    async def stream():
        if problems:
            yield _event("failure", {"message": " ".join(problems)})
            return
        if not slot.acquire():
            yield _event("failure", {"message": "Another brief is being made right now. "
                                                "Try again when it finishes."})
            return
        threading.Thread(target=worker, daemon=True).start()
        quiet_since = time.monotonic()
        try:
            while True:
                try:
                    item = events.get_nowait()
                except queue.Empty:
                    if time.monotonic() - quiet_since > HEARTBEAT_SECONDS:
                        yield ": still working\n\n"   # a comment line keeps the connection open
                        quiet_since = time.monotonic()
                    await asyncio.sleep(0.1)
                    continue
                if item is None:
                    return
                quiet_since = time.monotonic()
                yield _event(*item)
        finally:
            # Page closed or stream ended: the worker stops at its next step. A model
            # call already in flight can't be interrupted (one took 30 s in testing),
            # so the slot is freed now rather than making the next person wait for it.
            cancel.set()
            slot.release()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
