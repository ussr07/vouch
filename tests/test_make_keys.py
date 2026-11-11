"""scripts/make_keys.py: fills in Vouch's Bifrost keys once and never overwrites a key."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "make_keys", Path(__file__).resolve().parent.parent / "scripts" / "make_keys.py")
make_keys = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(make_keys)


class MakeKeys(unittest.TestCase):
    def setUp(self):
        self.env = Path(tempfile.mkdtemp()) / ".env"

    def test_empty_placeholders_are_filled_and_other_lines_kept(self):
        self.env.write_text("TAVILY_API_KEY=tvly-x\nVOUCH_VK=\nBIFROST_ADMIN_USERNAME=me\n", encoding="utf-8")
        added = make_keys.ensure_keys(self.env)
        self.assertEqual(added, ["VOUCH_VK", "VOUCH_DEMO_VK", "BIFROST_ADMIN_PASSWORD"])
        text = self.env.read_text(encoding="utf-8")
        self.assertIn("TAVILY_API_KEY=tvly-x", text)
        self.assertIn("BIFROST_ADMIN_USERNAME=me", text)       # an existing value is never replaced
        self.assertNotIn("VOUCH_VK=\n", text)                  # the empty placeholder is gone
        self.assertEqual(text.count("VOUCH_VK="), 1)
        self.assertTrue(make_keys.has_value(text, "VOUCH_VK"))

    def test_second_run_changes_nothing(self):
        make_keys.ensure_keys(self.env)
        before = self.env.read_text(encoding="utf-8")
        self.assertEqual(make_keys.ensure_keys(self.env), [])
        self.assertEqual(self.env.read_text(encoding="utf-8"), before)

    def test_virtual_keys_have_bifrost_prefix(self):
        make_keys.ensure_keys(self.env)
        text = self.env.read_text(encoding="utf-8")
        for name in ("VOUCH_VK", "VOUCH_DEMO_VK"):
            value = next(l.split("=", 1)[1] for l in text.splitlines() if l.startswith(name + "="))
            self.assertTrue(value.startswith("sk-bf-"))


if __name__ == "__main__":
    unittest.main()
