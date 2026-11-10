"""Saved briefs: round trip, listing, and refusing malformed ids."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vouch import cache, store


def brief(name, stories=2):
    return {"subject": {"name": name, "kind": "company", "goal": "sales", "meeting": "2026-11-14"},
            "stories": [{"headline": f"h{i}"} for i in range(stories)]}


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(cache, "DB_PATH", Path(self.tmp.name) / "test.db")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_save_and_get(self):
        brief_id = store.save(brief("Acme"))
        self.assertRegex(brief_id, r"^[0-9a-f]{12}$")
        self.assertEqual(store.get(brief_id)["subject"]["name"], "Acme")

    def test_recent_is_newest_first_without_stories(self):
        first = store.save(brief("First"))
        second = store.save(brief("Second", stories=5))
        rows = store.recent()
        self.assertEqual([r["id"] for r in rows][:2], [second, first])
        self.assertEqual(rows[0]["verified"], 5)
        self.assertNotIn("stories", rows[0])

    def test_bad_ids_refused(self):
        for bad in ["", "../../etc/passwd", "ABCDEF123456", "1' OR '1'='1", "x" * 12, None]:
            self.assertIsNone(store.get(bad))


if __name__ == "__main__":
    unittest.main()
