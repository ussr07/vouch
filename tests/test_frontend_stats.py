"""The brief page's numbers: units kept apart, zero handled, nothing invented.

The number logic lives in app/static/stats.js (no DOM), so it runs here under Node.
These tests are skipped when Node isn't installed.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS_JS = ROOT / "app" / "static" / "stats.js"
APP_JS = ROOT / "app" / "static" / "app.js"
VERIFY_PY = ROOT / "vouch" / "verify.py"

# Loads stats.js in a sandbox and answers for the brief given on stdin.
HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), ctx);
const brief = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify({
  numbers: ctx.VouchStats.briefNumbers(brief),
  empty: ctx.VouchStats.emptyMessage(brief),
  pointReason: ctx.VouchStats.POINT_REASON,
}));
"""


def run_stats(brief: dict) -> dict:
    out = subprocess.run(["node", "-e", HARNESS, str(STATS_JS)], input=json.dumps(brief),
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


def story(outlets=1, older=None):
    return {"headline": "h", "outlets": [f"site{i}.com" for i in range(outlets)], "older_event": older}


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class Numbers(unittest.TestCase):
    def test_zero_brief_has_honest_numbers_and_a_message(self):
        brief = {"counts": {"found": 0, "kept": 0, "verified": 0}, "stories": [],
                 "ledger": {"articles": [], "draft": []}}
        got = run_stats(brief)
        self.assertEqual(got["numbers"]["articles"], {"found": 0, "kept": 0, "filteredOut": 0})
        self.assertEqual(got["numbers"]["stories"],
                         {"drafted": 0, "verified": 0, "removed": 0, "multi": 0, "single": 0, "older": 0})
        self.assertTrue(got["empty"].startswith("No recent news"))
        self.assertNotIn("null", got["empty"])

    def test_zero_stories_from_kept_articles_says_why(self):
        brief = {"counts": {"found": 9, "kept": 4, "verified": 0}, "stories": [],
                 "ledger": {"articles": [], "draft": [{"item": "x", "reason": "cites no real article"}]}}
        got = run_stats(brief)
        self.assertTrue(got["empty"].startswith("No story survived the checks"))
        self.assertEqual(got["numbers"]["stories"]["drafted"], 1)
        self.assertEqual(got["numbers"]["stories"]["removed"], 1)

    def test_articles_and_stories_are_counted_separately(self):
        brief = {
            "counts": {"found": 32, "kept": 24, "verified": 3},
            "stories": [story(7), story(1, older="2012"), story(3)],
            "ledger": {"articles": [{"title": "t", "reason": "not a news article"}] * 8, "draft": [
                {"item": "a story", "reason": "quote not found word for word in the cited article"},
                {"item": "another", "reason": "cites no real article"},
                {"item": "a talking point", "reason": "not linked to any verified story"},
            ]},
        }
        n = run_stats(brief)["numbers"]
        # Articles: only article counts, straight from the brief.
        self.assertEqual(n["articles"], {"found": 32, "kept": 24, "filteredOut": 8})
        # Stories: only story counts. The removed talking point is not a story.
        self.assertEqual(n["stories"]["verified"], 3)
        self.assertEqual(n["stories"]["removed"], 2)
        self.assertEqual(n["stories"]["drafted"], 5)
        self.assertEqual(n["stories"]["multi"] + n["stories"]["single"], n["stories"]["verified"])
        self.assertEqual((n["stories"]["multi"], n["stories"]["single"], n["stories"]["older"]), (2, 1, 1))

    def test_point_reason_matches_the_verifier(self):
        """Stories drafted = verified + removals that aren't talking points; that split relies
        on the verifier's exact wording for a removed talking point."""
        reason = run_stats({"counts": {}, "stories": [], "ledger": {"draft": []}})["pointReason"]
        self.assertIn(f'"{reason}"', VERIFY_PY.read_text(encoding="utf-8"))


class PageSource(unittest.TestCase):
    """Guards on app.js for behaviour that needs a browser to see."""

    def test_ledger_is_never_appended_unguarded(self):
        # Element.append(null) prints the word "null" on a brief with nothing left out.
        self.assertIsNone(re.search(r"append\(\s*ledger\(", APP_JS.read_text(encoding="utf-8")))

    def test_tool_record_line_is_still_rendered(self):
        src = APP_JS.read_text(encoding="utf-8")
        self.assertIn("via the Bifrost gateway", src)
        self.assertIn("Search by Tavily", src)


if __name__ == "__main__":
    unittest.main()
