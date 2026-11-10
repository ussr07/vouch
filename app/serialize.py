"""Turn a Brief into plain JSON for the browser."""
from vouch.pipeline import Brief


def _site(url: str) -> str:
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    for prefix in ("www.", "m.", "amp."):
        host = host.removeprefix(prefix)
    return host


def brief_to_dict(b: Brief) -> dict:
    c = b.checked
    return {
        "subject": {"name": b.name, "kind": b.kind, "goal": b.goal, "about": b.about,
                    "meeting": b.meeting_at.date().isoformat(),
                    "meeting_time": b.meeting_at.strftime("%H:%M") if b.meeting_at.time() != b.meeting_at.min.time() else None,
                    "identified_as": b.entity.chosen_label if b.entity else None},
        "choices": b.entity.choices if b.entity else [],
        "window": {"start": b.run.window_start.isoformat(), "end": b.run.window_end.isoformat()},
        "counts": {"found": len(b.run.sources),
                   "kept": len(b.entity.kept) if b.entity and not b.entity.needs_choice else len(b.filtered.kept),
                   "shown_to_model": b.articles_shown_to_model, "verified": len(c.stories),
                   "credits": b.run.credits_used},
        "model": None if b.model_call is None else {
            "served_by": b.model_call.served_by, "fallback": b.model_call.used_fallback,
            "prompt_tokens": b.model_call.prompt_tokens,
            "completion_tokens": b.model_call.completion_tokens,
            "seconds": b.model_call.seconds,
            "entity_check_by": b.entity_call.served_by if b.entity_call else None,
            "entity_check_tokens": (b.entity_call.prompt_tokens + b.entity_call.completion_tokens)
                                   if b.entity_call else 0},
        "seconds": b.seconds,
        "stories": [{
            "headline": s.headline, "summary": s.summary, "category": s.category,
            "date": s.date.isoformat(), "outlets": s.outlets,
            "quote": s.quote, "quote_url": s.quote_source.source.url,
            "older_event": s.older_event,
            "quote_site": _site(s.quote_source.source.url),
            "sources": [{"title": k.source.title, "url": k.source.url, "site": _site(k.source.url),
                         "date": k.published.isoformat()} for k in s.sources],
        } for s in c.stories],
        "talking_points": [{"text": p.text, "stories": p.story_numbers} for p in c.talking_points],
        "open_questions": [{"text": p.text, "stories": p.story_numbers} for p in c.open_questions],
        "ledger": {
            "articles": [{"title": r.source.title or r.source.url, "url": r.source.url,
                          "site": _site(r.source.url), "reason": r.reason}
                         for r in b.filtered.rejected] +
                        [{"title": k.source.title, "url": k.source.url, "site": _site(k.source.url),
                          "reason": reason} for k, reason in (b.entity.set_aside if b.entity else [])],
            "draft": [{"item": item, "reason": reason} for item, reason in c.removed],
        },
    }
