"""Runs the whole pipeline: search -> filter -> draft -> verify.

This is the one function the website calls. `on_step` lets the website show
each stage as it really finishes, instead of a fake progress bar.
"""
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from vouch.draft import MAX_ARTICLES, draft
from vouch.entity import EntityDecision, resolve
from vouch.filters import FilterResult, filter_run
from vouch.llm import CallInfo, PRIMARY_MODEL
from vouch.research import SearchRun, search
from vouch.verify import Verified, verify

StepCallback = Callable[[str, dict], None]


class Cancelled(Exception):
    """Raised from on_step when the person closed the page: stop spending tokens."""


def is_cancelled(error: Exception) -> bool:
    return isinstance(error, Cancelled)


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
    about: str = ""
    entity: EntityDecision | None = None
    entity_call: CallInfo | None = None
    draft_raw: dict | None = None          # the model's draft before checking
    draft_articles: list | None = None     # the numbered articles it saw
    not_read: list | None = None           # kept articles past the reading limit
    warnings: list | None = None           # things the reader should know about this brief


def make_brief(name: str, kind: str, meeting_at: datetime, goal: str = "general",
               on_step: StepCallback | None = None, about: str = "") -> Brief:
    step = on_step or (lambda stage, data: None)
    start = time.time()

    step("search", {"status": "running"})
    run = search(name, kind, meeting_at, about=about)
    warnings = [f"The {angle} search failed, so this brief may miss {angle} news."
                for angle, _ in run.failed]
    step("search", {"status": "done", "found": len(run.sources),
                    "credits": run.credits_used, "cached": run.cache_hits,
                    "failed": [a for a, _ in run.failed]})

    filtered = filter_run(run)
    step("filter", {"status": "done", "kept": len(filtered.kept),
                    "rejected": len(filtered.rejected)})

    entity, entity_call = None, None
    usable = filtered.kept
    if filtered.kept:
        step("entity", {"status": "running"})
        try:
            entity, entity_call = resolve(name, kind, about, filtered.kept)
        except Exception as e:
            # The entity check is a safeguard, not the product: if it fails, carry on
            # with the filtered articles and say so, rather than failing the brief.
            if is_cancelled(e):
                raise
            warnings.append(f"Couldn't check whether every article is about the same {name} "
                            f"({type(e).__name__}); read the sources with that in mind.")
            step("entity", {"status": "done", "skipped": True})
        else:
            usable = entity.kept
            step("entity", {"status": "done", "groups": entity.groups_found,
                            "kept": len(entity.kept), "set_aside": len(entity.set_aside),
                            "needs_choice": entity.needs_choice, "label": entity.chosen_label})
            if entity.needs_choice:  # several different entities: ask the user, don't guess
                return Brief(name, kind, goal, meeting_at, run, filtered, 0, Verified(), None,
                             round(time.time() - start, 1), about, entity, entity_call,
                             warnings=warnings)

    if usable:
        step("draft", {"status": "running", "model": PRIMARY_MODEL})
        raw, articles, call = draft(name, kind, goal, meeting_at.date(), usable)
        step("draft", {"status": "done", "served_by": call.served_by,
                       "fallback": call.used_fallback, "seconds": call.seconds})
        checked = verify(raw, articles, subject=name, window_start=run.window_start)
        step("verify", {"status": "done", "verified": len(checked.stories),
                        "removed": len(checked.removed)})
    else:  # nothing survived filtering: say so honestly instead of calling the model
        articles, call, checked = [], None, Verified()

    # The model reads at most MAX_ARTICLES (the newest). The rest are listed in
    # the ledger rather than dropped silently.
    not_read = usable[MAX_ARTICLES:] if usable else []
    return Brief(name, kind, goal, meeting_at, run, filtered, len(articles),
                 checked, call, round(time.time() - start, 1), about, entity, entity_call,
                 raw if usable else None, articles, not_read, warnings)
