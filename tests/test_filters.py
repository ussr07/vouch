"""Tests for the filter rules. No internet or API credits needed.

Run from the project folder:  python -m unittest -v
"""
import unittest
from datetime import date

from vouch.filters import filter_run, mentions, normalise_url, parse_date
from vouch.research import SearchRun, Source


def src(url, title="", snippet="", published="Fri, 23 Oct 2026 10:00:00 GMT", score=0.5):
    return Source(url=url, title=title, snippet=snippet,
                  published_date=published, angle="news", score=score)


def run_with(*sources):
    return SearchRun(name="Infosys", kind="company",
                     window_start=date(2026, 10, 11), window_end=date(2026, 11, 10),
                     sources=list(sources))


class ParseDate(unittest.TestCase):
    def test_news_format(self):
        self.assertEqual(parse_date("Fri, 23 Oct 2026 10:15:00 GMT"), date(2026, 10, 23))

    def test_iso_format(self):
        self.assertEqual(parse_date("2026-10-23T10:15:00Z"), date(2026, 10, 23))

    def test_missing_or_garbage(self):
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date("last Tuesday"))


class Mentions(unittest.TestCase):
    def test_whole_word_only(self):
        self.assertTrue(mentions("Meta", "Meta launches a new headset"))
        self.assertFalse(mentions("Meta", "metadata standards for archives"))

    def test_case_insensitive(self):
        self.assertTrue(mentions("Infosys", "INFOSYS posts Q2 results"))


class NameSpellings(unittest.TestCase):
    def test_spacing_and_dots_between_words_dont_matter(self):
        for headline in ("JPMorgan raises its forecast", "J.P. Morgan raises its forecast",
                         "JP Morgan raises its forecast", "JP-Morgan raises its forecast"):
            self.assertTrue(mentions("JP Morgan", headline), headline)

    def test_initials_may_carry_dots(self):
        self.assertTrue(mentions("TCS", "T.C.S. wins a deal"))
        self.assertTrue(mentions("TCS", "TCS wins a deal"))

    def test_still_whole_words_only(self):
        self.assertFalse(mentions("JP Morgan", "JP Morganite gemstones"))
        self.assertFalse(mentions("Meta", "metadata standards"))
        self.assertFalse(mentions("TCS", "ATCS reports"))
        self.assertFalse(mentions("", "anything"))


class NormaliseUrl(unittest.TestCase):
    def test_same_page_variants(self):
        a = normalise_url("https://www.example.com/story/")
        b = normalise_url("http://m.example.com/story")
        self.assertEqual(a, b)


class FilterRun(unittest.TestCase):
    def reasons(self, result):
        return [r.reason for r in result.rejected]

    def test_keeps_a_good_article(self):
        result = filter_run(run_with(src("https://a.com/1", title="Infosys wins deal")))
        self.assertEqual(len(result.kept), 1)
        self.assertEqual(result.rejected, [])

    def test_rejects_tavily_profile_page(self):
        result = filter_run(run_with(src("https://tavily.com/knowledge/company/x",
                                         title="Infosys", published=None)))
        self.assertIn("not a news article", self.reasons(result)[0])

    def test_rejects_duplicate_keeps_higher_score(self):
        result = filter_run(run_with(
            src("https://a.com/1", title="Infosys deal", score=0.4),
            src("https://www.a.com/1/", title="Infosys deal", score=0.9),
        ))
        self.assertEqual(len(result.kept), 1)
        self.assertEqual(result.kept[0].source.score, 0.9)
        self.assertIn("duplicate", self.reasons(result)[0])

    def test_rejects_missing_date(self):
        result = filter_run(run_with(src("https://a.com/1", title="Infosys", published=None)))
        self.assertIn("no publish date", self.reasons(result)[0])

    def test_rejects_outside_window(self):
        result = filter_run(run_with(src("https://a.com/1", title="Infosys",
                                         published="Mon, 01 Sep 2026 10:00:00 GMT")))
        self.assertIn("outside the window", self.reasons(result)[0])

    def test_rejects_wrong_subject(self):
        result = filter_run(run_with(src("https://a.com/1", title="Toptal AI launches")))
        self.assertIn("never mentions 'Infosys'", self.reasons(result)[0])

    def test_rejects_passing_mention(self):
        result = filter_run(run_with(src("https://a.com/1", title="Toptal AI launches",
                                         snippet="Also today: Infosys launches 200 agents")))
        self.assertIn("only mentioned in passing", self.reasons(result)[0])

    def person_run(self, *sources):
        r = run_with(*sources)
        r.name, r.kind = "Nandan Nilekani", "person"
        return r

    def test_person_surname_headline_kept_when_text_has_full_name(self):
        result = filter_run(self.person_run(src("https://a.com/1", title="Nilekani calls for exam reform",
                                                snippet="Nandan Nilekani said on Monday...")))
        self.assertEqual(len(result.kept), 1)

    def test_person_surname_only_everywhere_rejected(self):
        result = filter_run(self.person_run(src("https://a.com/1", title="Nilekani calls for exam reform",
                                                snippet="A Nilekani in Pune said...")))
        self.assertEqual(result.kept, [])

    def test_company_needs_full_name_in_headline(self):
        r = run_with(src("https://a.com/1", title="Infy wins deal", snippet="Infosys won a deal"))
        self.assertEqual(filter_run(r).kept, [])

    def test_rejects_unsafe_links(self):
        for bad in ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://a.com/x", "//a.com/x", ""]:
            result = filter_run(run_with(src(bad, title="Infosys wins deal")))
            self.assertEqual(result.kept, [], bad)
            self.assertIn("not a normal web address", result.rejected[0].reason)

    def test_safe_link_check(self):
        from vouch.filters import is_web_link
        self.assertTrue(is_web_link("https://economictimes.com/a"))
        self.assertTrue(is_web_link("HTTP://a.com"))
        self.assertFalse(is_web_link("JavaScript:alert(1)"))



class UrlDedupe(unittest.TestCase):
    def test_different_ids_are_different_pages(self):
        self.assertNotEqual(normalise_url("https://a.com/news.php?id=1"), normalise_url("https://a.com/news.php?id=2"))

    def test_tracking_tags_ignored(self):
        self.assertEqual(normalise_url("https://www.a.com/story/?utm_source=x&utm_medium=y"),
                         normalise_url("http://a.com/story"))

    def test_parameter_order_ignored(self):
        self.assertEqual(normalise_url("https://a.com/p?b=2&a=1"), normalise_url("https://a.com/p?a=1&b=2"))


if __name__ == "__main__":
    unittest.main()
