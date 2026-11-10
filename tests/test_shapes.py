"""The model's reply in odd shapes must never crash or silently drop a story."""
import unittest
from datetime import date

from vouch.entity import decide
from vouch.filters import Kept
from vouch.research import Source
from vouch.shapes import as_int, as_ints
from vouch.verify import verify

TEXT = "Acme opened a new plant in Pune on Monday, the company said."


def kept(n):
    return Kept(Source(url=f"https://s{n}.com/a", title=f"Acme story {n}", snippet=TEXT,
                       published_date=None, angle="news", score=0.5), date(2026, 10, n))


ARTS = [kept(1), kept(2)]
GOOD_QUOTE = "Acme opened a new plant in Pune on Monday"


class Coercion(unittest.TestCase):
    def test_as_int(self):
        self.assertEqual([as_int(v) for v in [3, "3", " 3 ", 3.0]], [3, 3, 3, 3])
        self.assertEqual([as_int(v) for v in [True, "three", 3.5, None, [3]]], [None] * 5)

    def test_as_ints(self):
        self.assertEqual(as_ints(["1", 2, "x", None]), [1, 2])
        self.assertEqual(as_ints("2"), [2])
        self.assertEqual(as_ints(None), [])


class OddReplies(unittest.TestCase):
    def test_ids_as_strings_still_verify(self):
        raw = {"stories": [{"id": "1", "headline": "Acme opens Pune plant", "summary": "New plant.",
                            "article_ids": ["1", "2"], "quote": {"article_id": "1", "text": GOOD_QUOTE}}],
               "talking_points": [{"text": "Ask about Pune", "story_ids": ["1"]}]}
        out = verify(raw, ARTS, "Acme")
        self.assertEqual(len(out.stories), 1)
        self.assertEqual(len(out.stories[0].outlets), 2)
        self.assertEqual([p.text for p in out.talking_points], ["Ask about Pune"])

    def test_garbage_shapes_do_not_crash(self):
        for raw in [None, [], "text", {"stories": "oops"}, {"stories": ["a story", 5, None]},
                    {"stories": [{"quote": "not a dict", "article_ids": 1}]},
                    {"talking_points": [{"text": 5, "story_ids": None}]}]:
            out = verify(raw, ARTS, "Acme")
            self.assertEqual(out.stories, [])

    def test_missing_and_duplicate_story_ids_link_correctly(self):
        story = {"headline": "Acme opens Pune plant", "summary": "s", "article_ids": [1],
                 "quote": {"article_id": 1, "text": GOOD_QUOTE}}
        raw = {"stories": [dict(story), dict(story, id=1)],   # first has no id, second claims id 1
               "open_questions": [{"text": "Q about the second", "story_ids": [2]}]}
        out = verify(raw, ARTS, "Acme")
        self.assertEqual(len(out.stories), 2)
        self.assertEqual(out.open_questions[0].story_numbers, [2])

    def test_entity_reply_with_strings_and_junk(self):
        d = decide({"entities": ["junk", {"label": "Acme", "article_ids": ["1", "2", "2"]}],
                    "match": "1"}, ARTS, "Acme", about="the Pune one")
        self.assertEqual(d.chosen_label, "Acme")
        self.assertEqual(len(d.kept), 2)

    def test_entity_reply_not_a_dict(self):
        d = decide("nonsense", ARTS, "Acme")
        self.assertEqual(d.kept, [])
        self.assertEqual(len(d.set_aside), 2)   # nothing classified, each recorded


if __name__ == "__main__":
    unittest.main()
