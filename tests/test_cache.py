"""The search cache must close its connections and expire old rows."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from vouch import cache


class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(cache, "DB_PATH", Path(self.tmp.name) / "test.db")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()   # fails on Windows if a connection were left open

    def test_round_trip(self):
        cache.put({"q": "acme"}, {"results": [1]})
        self.assertEqual(cache.get({"q": "acme"}), {"results": [1]})
        self.assertIsNone(cache.get({"q": "other"}))

    def test_expired_entries_not_returned(self):
        cache.put({"q": "acme"}, {"results": []})
        with mock.patch.object(cache.time, "time", return_value=time.time() + 25 * 3600):
            self.assertIsNone(cache.get({"q": "acme"}))

    def test_old_rows_pruned_on_write(self):
        with mock.patch.object(cache.time, "time", return_value=time.time() - 8 * 86400):
            cache.put({"q": "old"}, {"results": []})
        cache.put({"q": "new"}, {"results": []})
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(cache.DB_PATH)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
