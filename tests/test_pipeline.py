"""Pipeline tests with Tavily and the model replaced by fakes. No network, no credits.

Run from the project folder:  python -m unittest -v
"""
import unittest
from datetime import date, datetime
from unittest import mock

from vouch import pipeline
from vouch.draft import MAX_ARTICLES
from vouch.entity import EntityDecision
from vouch.filters import Kept
from vouch.llm import CallInfo
from vouch.research import SearchRun, Source

CALL = CallInfo("fake/model", False, 10, 10, 0.1)


def fake_run(n):
    sources = [Source(url=f"https://site{i}.com/a", title=f"Acme story {i}",
                      snippet=f"Acme did thing number {i} this week, the company said.",
                      published_date=f"2026-10-{(i % 28) + 1:02d}", angle="news", score=0.5)
               for i in range(1, n + 1)]
    return SearchRun("Acme", "company", date(2026, 10, 1), date(2026, 10, 31), sources, 0, 4)


def fake_resolve(name, kind, about, kept):
    return EntityDecision(kept=list(kept), chosen_label="Acme", groups_found=1), CALL


def fake_draft(name, kind, goal, day, kept):
    articles = kept[:MAX_ARTICLES]
    return {"stories": []}, articles, CALL


class NothingDroppedSilently(unittest.TestCase):
    def test_articles_past_the_limit_are_recorded(self):
        with mock.patch.object(pipeline, "search", return_value=fake_run(25)), \
             mock.patch.object(pipeline, "resolve", side_effect=fake_resolve), \
             mock.patch.object(pipeline, "draft", side_effect=fake_draft):
            b = pipeline.make_brief("Acme", "company", datetime(2026, 11, 1))
        self.assertEqual(b.articles_shown_to_model, MAX_ARTICLES)
        self.assertEqual(len(b.not_read), 25 - MAX_ARTICLES)
        # every kept article is either shown to the model or recorded as not read
        shown = {k.source.url for k in b.draft_articles}
        missing = {k.source.url for k in b.not_read}
        self.assertEqual(shown | missing, {s.url for s in fake_run(25).sources})
        self.assertFalse(shown & missing)



class EntityStepDegrades(unittest.TestCase):
    def test_entity_failure_continues_with_a_warning(self):
        def broken_resolve(*args):
            raise ConnectionError("gateway hiccup")
        with mock.patch.object(pipeline, "search", return_value=fake_run(5)), \
             mock.patch.object(pipeline, "resolve", side_effect=broken_resolve), \
             mock.patch.object(pipeline, "draft", side_effect=fake_draft):
            b = pipeline.make_brief("Acme", "company", datetime(2026, 11, 1))
        self.assertEqual(b.articles_shown_to_model, 5)          # the brief still got made
        self.assertTrue(any("same Acme" in w for w in b.warnings))

    def test_failed_search_angle_becomes_a_warning(self):
        run = fake_run(3)
        run.failed = [("deals", "TimeoutError: slow")]
        with mock.patch.object(pipeline, "search", return_value=run), \
             mock.patch.object(pipeline, "resolve", side_effect=fake_resolve), \
             mock.patch.object(pipeline, "draft", side_effect=fake_draft):
            b = pipeline.make_brief("Acme", "company", datetime(2026, 11, 1))
        self.assertIn("The deals search failed, so this brief may miss deals news.", b.warnings)


if __name__ == "__main__":
    unittest.main()
