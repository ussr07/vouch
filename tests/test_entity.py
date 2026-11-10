"""Tests for the entity decision rules (the model's output is faked here).

Run from the project folder:  python -m unittest -v
"""
import unittest
from datetime import date

from vouch.entity import decide
from vouch.filters import Kept
from vouch.research import Source


def kept(n):
    return Kept(Source(url=f"https://s{n}.com", title=f"Mercury story {n}", snippet="",
                       published_date=None, angle="news", score=0.5), date(2026, 10, n))


ARTICLES = [kept(n) for n in range(1, 9)]  # 8 articles


class Decide(unittest.TestCase):
    def test_single_entity_keeps_everything(self):
        d = decide({"entities": [{"label": "Mercury bank", "article_ids": list(range(1, 9))}]},
                   ARTICLES, "Mercury")
        self.assertEqual(len(d.kept), 8)
        self.assertFalse(d.needs_choice)

    def test_dominant_entity_kept_others_set_aside(self):
        d = decide({"entities": [{"label": "Mercury bank", "article_ids": [1, 2, 3, 4, 5, 6, 7]},
                                 {"label": "Mercury Records", "article_ids": [8]}]},
                   ARTICLES, "Mercury")
        self.assertEqual(len(d.kept), 7)
        self.assertEqual(d.set_aside[0][1], "about a different Mercury: Mercury Records")

    def test_mixed_entities_ask_the_user(self):
        d = decide({"entities": [{"label": "Mercury Records", "article_ids": [1, 2, 3]},
                                 {"label": "Phoenix Mercury", "article_ids": [4, 5]},
                                 {"label": "Mercury bank", "article_ids": [6, 7, 8]}]},
                   ARTICLES, "Mercury")
        self.assertTrue(d.needs_choice)
        self.assertEqual([c["count"] for c in d.choices], [3, 3, 2])
        self.assertEqual(d.kept, [])

    def test_user_hint_picks_the_matching_group(self):
        d = decide({"entities": [{"label": "Mercury Records", "article_ids": [1, 2, 3, 4, 5]},
                                 {"label": "Mercury bank", "article_ids": [6, 7, 8]}], "match": 1},
                   ARTICLES, "Mercury", about="the startup bank")
        self.assertEqual(len(d.kept), 3)
        self.assertEqual(d.chosen_label, "Mercury bank")
        self.assertIn("about a different Mercury: Mercury Records", d.set_aside[0][1])

    def test_match_index_survives_empty_group(self):
        # The model's first entity is empty; "match": 2 must still mean "Mercury bank".
        d = decide({"entities": [{"label": "Nothing", "article_ids": []},
                                 {"label": "Mercury Records", "article_ids": [1, 2, 3, 4, 5]},
                                 {"label": "Mercury bank", "article_ids": [6, 7, 8]}], "match": 2},
                   ARTICLES, "Mercury", about="the startup bank")
        self.assertEqual(d.chosen_label, "Mercury bank")

    def test_hint_matching_nothing_keeps_nothing(self):
        d = decide({"entities": [{"label": "Mercury Records", "article_ids": list(range(1, 9))}],
                    "match": None}, ARTICLES, "Mercury", about="the startup bank")
        self.assertEqual(d.kept, [])
        self.assertIn("doesn't match 'the startup bank'", d.set_aside[0][1])

    def test_unassigned_kept_when_only_one_entity(self):
        d = decide({"entities": [{"label": "Mercury bank", "article_ids": [1, 2, 3, 4, 5, 6, 7, 99]}]},
                   ARTICLES, "Mercury")
        self.assertEqual(len(d.kept), 8)   # article 8 unassigned, but nothing to confuse it with
        self.assertEqual(d.set_aside, [])

    def test_unassigned_set_aside_when_several_entities(self):
        d = decide({"entities": [{"label": "Mercury bank", "article_ids": [1, 2, 3, 4, 5, 6]},
                                 {"label": "Mercury Records", "article_ids": [7]}]},
                   ARTICLES, "Mercury")
        self.assertEqual(len(d.kept), 6)
        self.assertIn(("couldn't tell which Mercury it's about"), [r for _, r in d.set_aside])


if __name__ == "__main__":
    unittest.main()
