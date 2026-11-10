"""Tests for the quote checker and draft verification. No internet needed.

Run from the project folder:  python -m unittest -v
"""
import unittest
from datetime import date

from vouch.filters import Kept
from vouch.research import Source
from vouch.verify import normalise, older_event, quote_found, verify

ARTICLE_TEXT = ("Infosys reported a 6% rise in quarterly profit to Rs 7,823 crore. "
                "The board declared an interim dividend of ₹26 per share.")


def kept(n, text=ARTICLE_TEXT, day=23, url=None):
    src = Source(url=url or f"https://site{n}.com/a", title=f"Article {n}",
                 snippet=text, published_date=None, angle="news", score=0.5)
    return Kept(src, date(2026, 10, day))


class QuoteFound(unittest.TestCase):
    def test_exact_quote(self):
        self.assertTrue(quote_found("The board declared an interim dividend of ₹26 per share.",
                                    ARTICLE_TEXT))

    def test_curly_quotes_and_spacing_are_ignored(self):
        self.assertEqual(normalise("It’s   “fine”"), "it's \"fine\"")

    def test_changed_number_fails(self):
        self.assertFalse(quote_found("Infosys reported a 9% rise in quarterly profit", ARTICLE_TEXT))

    def test_paraphrase_fails(self):
        self.assertFalse(quote_found("Infosys profit went up 6 percent", ARTICLE_TEXT))

    def test_unusual_hyphens_match(self):
        self.assertTrue(quote_found("an AI\u2011first centre in Hyderabad today",
                                    "It opened an AI-first centre in Hyderabad today."))

    def test_too_short_fails(self):
        self.assertFalse(quote_found("Infosys", ARTICLE_TEXT))


class Verify(unittest.TestCase):
    def setUp(self):
        self.articles = [kept(1, day=23), kept(2, day=21, url="https://www.site2.com/b")]

    def story(self, **overrides):
        s = {"id": 1, "headline": "Profit up", "summary": "s", "category": "results",
             "article_ids": [1, 2],
             "quote": {"article_id": 1, "text": "Infosys reported a 6% rise in quarterly profit"}}
        s.update(overrides)
        return s

    def test_good_story_kept_with_code_computed_fields(self):
        result = verify({"stories": [self.story()]}, self.articles)
        self.assertEqual(len(result.stories), 1)
        self.assertEqual(result.stories[0].date, date(2026, 10, 21))   # earliest source
        self.assertEqual(result.stories[0].outlets, ["site1.com", "site2.com"])

    def test_invented_quote_removed(self):
        bad = self.story(quote={"article_id": 1, "text": "Infosys will double revenue next year"})
        result = verify({"stories": [bad]}, self.articles)
        self.assertEqual(result.stories, [])
        self.assertIn("not found word for word", result.removed[0][1])

    def test_fake_article_number_removed(self):
        result = verify({"stories": [self.story(article_ids=[99])]}, self.articles)
        self.assertIn("cites no real article", result.removed[0][1])

    def test_points_must_link_to_surviving_story(self):
        raw = {"stories": [self.story()],
               "talking_points": [{"text": "Ask about dividend", "story_ids": [1]},
                                  {"text": "Unlinked claim", "story_ids": [5]}]}
        result = verify(raw, self.articles)
        self.assertEqual([p.text for p in result.talking_points], ["Ask about dividend"])
        self.assertIn("not linked", result.removed[0][1])

    def test_invented_figure_removed(self):
        bad = self.story(summary="Profit rose 9% to a record.")
        result = verify({"stories": [bad]}, self.articles)
        self.assertIn("figure(s) 9 not in any cited article", result.removed[0][1])

    def test_unrelated_quote_removed(self):
        # Real sentence from the article, but the story is about something else.
        bad = self.story(headline="Company announces buyback programme", summary="A buyback.",
                         quote={"article_id": 1,
                                "text": "The board declared an interim dividend of \u20b926 per share."})
        result = verify({"stories": [bad]}, self.articles, subject="Infosys")
        self.assertIn("doesn't back up this claim", result.removed[0][1])


class OlderEvent(unittest.TestCase):
    START = date(2026, 10, 11)

    def test_month_before_window_flagged(self):
        self.assertEqual(older_event("In May 2026, the company announced a Series D", self.START), "May 2026")

    def test_full_date_before_window_flagged(self):
        self.assertEqual(older_event("on July 4, 2026 he stepped down", self.START), "Jul 2026")

    def test_earlier_year_flagged(self):
        self.assertEqual(older_event("a deal signed in 2024", self.START), "2024")

    def test_same_month_as_window_not_flagged(self):
        self.assertIsNone(older_event("results for October 2026", self.START))

    def test_fiscal_year_names_not_flagged(self):
        self.assertIsNone(older_event("Q2 FY27 revenue rose 1.5%", self.START))


if __name__ == "__main__":
    unittest.main()
