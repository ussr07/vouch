"""Turn a Brief into plain JSON for the browser."""
from vouch.draft import MAX_ARTICLES
from vouch.filters import is_web_link
from vouch.pipeline import Brief


def _link(url: str) -> str | None:
    """Only http(s) addresses leave the server as links; anything else becomes None."""
    return url if is_web_link(url) else None


def _site(url: str) -> str:
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    for prefix in ("www.", "m.", "amp."):
        host = host.removeprefix(prefix)
    return host


def _growth(b: Brief) -> dict | None:
    """Yearly figures, each with where it came from. None when the step didn't run."""
    g = b.growth
    if g is None:
        return None
    return {
        "company": g.company, "method": g.method, "symbol": g.symbol, "note": g.note,
        "person_role": g.person_role, "credits": g.credits, "seconds": g.seconds,
        "tokens": sum(c.prompt_tokens + c.completion_tokens for c in g.calls),
        "figures": [{"year": f.year, "metric": f.metric, "value": f.value, "currency": f.currency,
                     "source_url": _link(f.source_url), "source_name": f.source_name,
                     "quote": f.quote} for f in g.figures],
    }


def brief_to_dict(b: Brief) -> dict:
    c = b.checked
    return {
        "subject": {"name": b.name, "kind": b.kind, "goal": b.goal, "about": b.about,
                    "meeting": b.meeting_at.date().isoformat(),
                    "meeting_time": b.meeting_at.strftime("%H:%M") if b.meeting_at.time() != b.meeting_at.min.time() else None,
                    "identified_as": b.entity.chosen_label if b.entity else None},
        "choices": b.entity.choices if b.entity else [],
        "warnings": b.warnings or [],
        "window": {"start": b.run.window_start.isoformat(), "end": b.run.window_end.isoformat()},
        "counts": {"found": len(b.run.sources),
                   "kept": len(b.entity.kept) if b.entity and not b.entity.needs_choice else len(b.filtered.kept),
                   "shown_to_model": b.articles_shown_to_model, "verified": len(c.stories),
                   "credits": b.run.credits_used, "cache_hits": b.run.cache_hits},
        "model": None if b.model_call is None else {
            "served_by": b.model_call.served_by, "fallback": b.model_call.used_fallback,
            "prompt_tokens": b.model_call.prompt_tokens,
            "completion_tokens": b.model_call.completion_tokens,
            "seconds": b.model_call.seconds,
            "entity_check_by": b.entity_call.served_by if b.entity_call else None,
            "entity_check_tokens": (b.entity_call.prompt_tokens + b.entity_call.completion_tokens)
                                   if b.entity_call else 0},
        "seconds": b.seconds,
        "timings": b.timings or {},
        "growth": _growth(b),
        "stories": [{
            "headline": s.headline, "summary": s.summary, "category": s.category,
            "date": s.date.isoformat(), "outlets": s.outlets,
            "quote": s.quote, "quote_url": _link(s.quote_source.source.url),
            "older_event": s.older_event,
            "quote_site": _site(s.quote_source.source.url),
            "sources": [{"title": k.source.title, "url": _link(k.source.url), "site": _site(k.source.url),
                         "date": k.published.isoformat()} for k in s.sources],
        } for s in c.stories],
        "talking_points": [{"text": p.text, "stories": p.story_numbers} for p in c.talking_points],
        "open_questions": [{"text": p.text, "stories": p.story_numbers} for p in c.open_questions],
        "ledger": {
            "articles": [{"title": r.source.title or r.source.url, "url": _link(r.source.url),
                          "site": _site(r.source.url), "reason": r.reason}
                         for r in b.filtered.rejected] +
                        [{"title": k.source.title, "url": _link(k.source.url), "site": _site(k.source.url),
                          "reason": reason} for k, reason in (b.entity.set_aside if b.entity else [])] +
                        [{"title": k.source.title, "url": _link(k.source.url), "site": _site(k.source.url),
                          "reason": f"not read: the AI reads at most the {MAX_ARTICLES} newest articles"}
                         for k in (b.not_read or [])],
            "draft": [{"item": item, "reason": reason} for item, reason in c.removed],
        },
    }
