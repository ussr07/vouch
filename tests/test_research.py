"""Tests for the search window and meeting-date rules. No network."""
import unittest
from datetime import date, datetime

from vouch.research import meeting_problem, window_for

TODAY = date(2026, 11, 10)


class MeetingDate(unittest.TestCase):
    def test_normal_dates_are_fine(self):
        for d in ["2026-11-14T10:30", "2026-01-05", "2027-11-01"]:
            self.assertIsNone(meeting_problem(datetime.fromisoformat(d), TODAY), d)

    def test_year_one_is_refused_not_crashed(self):
        self.assertIn("from 2000", meeting_problem(datetime(1, 1, 5), TODAY))

    def test_far_future_refused(self):
        self.assertIn("within the next year", meeting_problem(datetime(2030, 1, 1), TODAY))

    def test_timezone_in_input_is_fine(self):
        self.assertIsNone(meeting_problem(datetime.fromisoformat("2026-11-14T10:30+05:30"), TODAY))


class Window(unittest.TestCase):
    def test_future_meeting_window_ends_today(self):
        self.assertEqual(window_for(datetime(2026, 11, 14), TODAY), (date(2026, 10, 11), TODAY))

    def test_past_meeting_window_ends_on_the_meeting(self):
        self.assertEqual(window_for(datetime(2026, 9, 30), TODAY), (date(2026, 8, 31), date(2026, 9, 30)))



class PartialFailure(unittest.TestCase):
    """One Tavily search failing must not sink the brief; all failing must raise."""

    def setUp(self):
        import os
        os.environ.setdefault("TAVILY_API_KEY", "test-key")

    def fake_client(self, fail_on):
        from unittest import mock

        def search(**params):
            if any(word in params["query"] for word in fail_on):
                raise TimeoutError("Tavily timed out")
            return {"results": [{"url": "https://a.com/" + params["query"][:8].replace(" ", "-"),
                                 "title": "Acme news", "content": "Acme did a thing.",
                                 "published_date": "2026-11-01", "score": 0.9}]}
        client = mock.MagicMock()
        client.search.side_effect = search
        return mock.patch("vouch.research.TavilyClient", return_value=client)

    def test_one_failed_search_is_recorded_and_others_kept(self):
        from unittest import mock
        from vouch import research
        with self.fake_client(fail_on=["funding"]), \
             mock.patch.object(research.cache, "get", return_value=None), \
             mock.patch.object(research.cache, "put"):
            run = research.search("Acme", "company", datetime(2026, 11, 14))
        self.assertEqual([a for a, _ in run.failed], ["deals"])
        self.assertEqual(len(run.sources), 3)
        self.assertEqual(run.credits_used, 3)

    def test_every_search_failing_raises_the_real_error(self):
        from unittest import mock
        from vouch import research
        with self.fake_client(fail_on=["Acme"]), \
             mock.patch.object(research.cache, "get", return_value=None), \
             mock.patch.object(research.cache, "put"):
            with self.assertRaises(TimeoutError):
                research.search("Acme", "company", datetime(2026, 11, 14))


if __name__ == "__main__":
    unittest.main()
