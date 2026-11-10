"""Runs the whole pipeline: search -> filter -> draft -> verify.

This is the one function the website will call.
"""
import time
from dataclasses import dataclass
from datetime import datetime

from vouch.draft import draft
from vouch.filters import FilterResult, filter_run
from vouch.llm import CallInfo
from vouch.research import SearchRun, search
from vouch.verify import Verified, verify


@dataclass
class Brief:
    name: str
    kind: str
    goal: str
    meeting_at: datetime
    run: SearchRun
    filtered: FilterResult
    articles_shown_to_model: int
    checked: Verified
    model_call: CallInfo | None
    seconds: float


def make_brief(name: str, kind: str, meeting_at: datetime, goal: str = "general") -> Brief:
    start = time.time()
    run = search(name, kind, meeting_at)
    filtered = filter_run(run)

    if filtered.kept:
        raw, articles, call = draft(name, kind, goal, meeting_at.date(), filtered.kept)
        checked = verify(raw, articles, subject=name)
    else:  # nothing survived filtering: say so honestly instead of calling the model
        articles, call, checked = [], None, Verified()

    return Brief(name, kind, goal, meeting_at, run, filtered, len(articles),
                 checked, call, round(time.time() - start, 1))
