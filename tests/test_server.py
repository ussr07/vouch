"""The web server, end to end, with the pipeline replaced by fakes.

No network, no credits. Covers: input checks, the streamed stages, saving and
reopening a brief, friendly errors for each failure type, and the busy rule.
"""
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import httpx
import openai
from fastapi.testclient import TestClient
from tavily import errors as tavily_errors

import app.main as server
from vouch import cache
from vouch.filters import FilterResult
from vouch.pipeline import Brief
from vouch.research import SearchRun
from vouch.verify import Verified

GOOD = {"name": "Acme", "kind": "company", "goal": "sales", "meeting": "2026-11-14T10:30"}


def events(response) -> list[tuple[str, dict]]:
    """Parse a Server-Sent Events body into (event, data) pairs."""
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = [l for l in block.splitlines() if not l.startswith(":")]
        kind = next((l[7:] for l in lines if l.startswith("event: ")), None)
        data = next((l[6:] for l in lines if l.startswith("data: ")), None)
        if kind:
            out.append((kind, json.loads(data)))
    return out


def fake_brief(name, kind, meeting_at, goal, about="", on_step=None):
    on_step("search", {"status": "done", "found": 0, "credits": 0, "cached": 4, "failed": []})
    run = SearchRun(name, kind, date(2026, 10, 11), date(2026, 11, 10))
    return Brief(name, kind, goal, meeting_at, run, FilterResult(), 0, Verified(), None, 0.1, about)


class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = mock.patch.object(cache, "DB_PATH", Path(self.tmp.name) / "test.db")
        self.db.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.db.stop()
        self.tmp.cleanup()

    def ask(self, **overrides):
        return events(self.client.get("/api/brief", params={**GOOD, **overrides}))

    # --- input checks -------------------------------------------------------
    def test_bad_inputs_get_clear_messages(self):
        cases = {"kind": ("robot", "Choose company or person"),
                 "goal": ("party", "Choose a meeting type"),
                 "meeting": ("next week", "Give the meeting date and time"),
                 "name": ("   ", "Enter a company or person")}
        for field, (value, expected) in cases.items():
            got = self.ask(**{field: value})
            self.assertEqual(got[0][0], "failure", field)
            self.assertIn(expected, got[0][1]["message"], field)

    def test_year_one_meeting_is_refused_not_crashed(self):
        got = self.ask(meeting="0001-01-05")
        self.assertIn("from 2000", got[0][1]["message"])

    def test_missing_name_is_a_validation_error(self):
        self.assertEqual(self.client.get("/api/brief", params={"meeting": "2026-11-14"}).status_code, 422)

    # --- success, saving, reopening ----------------------------------------
    def test_stages_then_saved_brief(self):
        with mock.patch.object(server, "make_brief", side_effect=fake_brief):
            got = self.ask()
        self.assertEqual([k for k, _ in got], ["step", "brief"])
        brief = got[-1][1]
        self.assertRegex(brief["id"], r"^[0-9a-f]{12}$")
        reopened = self.client.get(f"/api/briefs/{brief['id']}")
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["subject"]["name"], "Acme")
        listed = self.client.get("/api/briefs").json()["briefs"]
        self.assertEqual(listed[0]["id"], brief["id"])

    def test_unknown_or_malformed_brief_id_is_404(self):
        for bad in ["0123456789ab", "nope", "..%2F..%2Fetc"]:
            self.assertEqual(self.client.get(f"/api/briefs/{bad}").status_code, 404, bad)

    def test_page_routes_serve_the_app(self):
        for path in ["/", "/brief/0123456789ab"]:
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertIn("<title>Vouch</title>", r.text)

    # --- failures become friendly messages ---------------------------------
    def failure_for(self, error):
        def broken(*args, **kwargs):
            raise error
        with mock.patch.object(server, "make_brief", side_effect=broken):
            got = self.ask()
        self.assertEqual(got[-1][0], "failure")
        return got[-1][1]["message"]

    def test_each_failure_type_has_a_helpful_message(self):
        request = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")
        cases = [
            (tavily_errors.InvalidAPIKeyError("bad key"), "Tavily rejected the API key"),
            (tavily_errors.UsageLimitExceededError("limit"), "free credits are used up"),
            (tavily_errors.TimeoutError(10), "search timed out"),
            (openai.APIConnectionError(request=request), "Can't reach the model gateway"),
            (openai.APITimeoutError(request=request), "took too long"),
            (RuntimeError("the model's reply was cut off before it finished"), "couldn't be used"),
            (openai.RateLimitError("limited", response=httpx.Response(429, request=request),
                                   body={"type": "request_limited"}), "reached its daily limit in Bifrost"),
            (openai.RateLimitError("limited", response=httpx.Response(429, request=request),
                                   body={"type": "rate_limit_exceeded"}), "Every model is rate-limited"),
            (openai.APIStatusError("budget", response=httpx.Response(402, request=request),
                                   body={"type": "budget_exceeded"}), "daily model budget"),
            (ZeroDivisionError("boom"), "ZeroDivisionError"),
        ]
        for error, expected in cases:
            self.assertIn(expected, self.failure_for(error), type(error).__name__)

    def test_a_failure_frees_the_server_for_the_next_brief(self):
        self.failure_for(RuntimeError("x"))
        with mock.patch.object(server, "make_brief", side_effect=fake_brief):
            self.assertEqual(self.ask()[-1][0], "brief")

    # --- one brief at a time -----------------------------------------------
    def test_second_brief_while_busy_is_told_to_wait(self):
        self.assertTrue(server.BUSY.acquire(blocking=False))
        try:
            got = self.ask()
        finally:
            server.BUSY.release()
        self.assertIn("Another brief is being made", got[0][1]["message"])



class SlotRelease(unittest.TestCase):
    def test_slot_releases_once_and_frees_busy(self):
        slot = server._Slot()
        self.assertTrue(slot.acquire())
        self.assertFalse(server._Slot().acquire())     # someone else is told to wait
        slot.release()
        slot.release()                                   # second release does nothing
        other = server._Slot()
        self.assertTrue(other.acquire())                 # free again, and not over-released
        self.assertFalse(server._Slot().acquire())
        other.release()



class GatewayUsage(unittest.TestCase):
    def test_unavailable_bifrost_is_reported_not_raised(self):
        with mock.patch.dict("os.environ", {"BIFROST_ADMIN_USERNAME": "a", "BIFROST_ADMIN_PASSWORD": "b"}), \
             mock.patch("vouch.gateway.urllib.request.urlopen", side_effect=__import__("urllib.error").error.URLError("down")):
            body = TestClient(server.app).get("/api/gateway").json()
        self.assertFalse(body["available"])
        self.assertIn("didn't answer", body["reason"])

    def test_usage_numbers_are_read(self):
        payload = json.dumps({"virtual_key": {
            "rate_limit": {"request_current_usage": 5, "request_max_limit": 300,
                           "token_current_usage": 14396, "token_max_limit": 300000,
                           "request_reset_duration": "1d"},
            "budgets": [{"current_usage": 0.003045, "max_limit": 1}]}}).encode()
        fake = mock.MagicMock()
        fake.__enter__.return_value.read.return_value = payload
        with mock.patch.dict("os.environ", {"BIFROST_ADMIN_USERNAME": "a", "BIFROST_ADMIN_PASSWORD": "b"}), \
             mock.patch("vouch.gateway.urllib.request.urlopen", return_value=fake), \
             mock.patch("vouch.gateway.json.load", return_value=json.loads(payload)):
            body = TestClient(server.app).get("/api/gateway").json()
        self.assertEqual((body["requests_used"], body["tokens_limit"]), (5, 300000))
        self.assertAlmostEqual(body["spend_usd"], 0.003045, places=5)



class ChallengeBrief(unittest.TestCase):
    """Items named in the official problem statement (PDF, Problem Statement 05)."""

    def test_business_development_is_a_meeting_type(self):
        with mock.patch.object(server, "make_brief", side_effect=fake_brief):
            got = events(TestClient(server.app).get("/api/brief", params={**GOOD, "goal": "bizdev"}))
        self.assertEqual(got[-1][0], "brief")

    def test_the_form_offers_every_meeting_type_the_server_accepts(self):
        page = TestClient(server.app).get("/").text
        for goal in server.GOALS:
            self.assertIn(f'value="{goal}"', page, goal)


if __name__ == "__main__":
    unittest.main()
