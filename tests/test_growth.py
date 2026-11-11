"""Growth over the years: every figure has a source, and nothing unproven gets through.

No network: Yahoo, Tavily and the model are replaced by fakes.
"""
import unittest
from datetime import datetime
from unittest import mock

from vouch import growth, pipeline
from vouch.growth import Figure, check_news_figures, clean_company, listing_matches, parse_amount
from vouch.llm import CallInfo

CALL = CallInfo("fake/model", False, 10, 5, 0.1)
ARTICLE = {"url": "https://www.example.com/results", "title": "Acme results",
           "content": "Acme reported revenue of Rs 2,55,324 crore for FY2025, up 6%. "
                      "In fiscal 2024, Acme's revenue was Rs 2,40,893 crore. "
                      "Net profit for FY2025 stood at Rs 48,553 crore."}


def fig(year, metric="revenue", amount="Rs 2,55,324 crore", quote=None, article_id=1, currency="INR"):
    return {"year": year, "metric": metric, "amount": amount, "currency": currency,
            "article_id": article_id,
            "quote": quote or "Acme reported revenue of Rs 2,55,324 crore for FY2025, up 6%."}


class Names(unittest.TestCase):
    def test_funds_are_never_the_company(self):
        self.assertFalse(listing_matches("Zerodha", "Zerodha Gold ETF"))
        self.assertFalse(listing_matches("Zerodha", "Zerodha Nifty Midcap 150 ETF"))

    def test_every_word_of_the_name_must_match(self):
        self.assertTrue(listing_matches("Tata Consultancy Services", "Tata Consultancy Services Limited"))
        self.assertTrue(listing_matches("Nvidia", "NVIDIA Corporation"))
        self.assertFalse(listing_matches("Infosys", "HCL Infosystems Limited"))

    def test_a_near_name_is_a_different_company(self):
        # "Mercury" the startup bank is not Mercury Systems, the aerospace company.
        self.assertFalse(listing_matches("Mercury", "Mercury Systems, Inc."))
        self.assertFalse(listing_matches("Reliance", "Reliance Industries Limited"))

    def test_a_name_typed_as_the_ticker_matches_its_listing(self):
        self.assertTrue(growth.symbol_matches("TCS", "TCS.NS", "Tata Consultancy Services Limited"))
        self.assertFalse(growth.symbol_matches("Mercury", "MRCY", "Mercury Systems, Inc."))
        self.assertFalse(growth.symbol_matches("GOLD", "GOLD.NS", "Some Gold ETF"))

    def test_labels_are_reduced_to_the_company_name(self):
        self.assertEqual(clean_company("Tata Consultancy Services (TCS)"), "Tata Consultancy Services")
        self.assertEqual(clean_company("Infosys, the Indian IT services company"), "Infosys")


class Amounts(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_amount("Rs 2,55,324 crore"), 255324 * 1e7)
        self.assertEqual(parse_amount("₹2.55 lakh crore"), 2.55 * 1e12)
        self.assertEqual(parse_amount("$60.9 billion in sales"), 60.9 * 1e9)
        self.assertEqual(parse_amount("1,234"), 1234)
        self.assertIsNone(parse_amount("no figure here"))


class NewsFiguresAreChecked(unittest.TestCase):
    def test_a_figure_found_word_for_word_is_kept_with_its_source(self):
        got = check_news_figures({"figures": [fig(2025)]}, [ARTICLE])
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0].year, got[0].value, got[0].source_name), (2025, 255324 * 1e7, "example.com"))
        self.assertIn("2,55,324", got[0].quote)

    def test_paraphrased_quote_is_dropped(self):
        got = check_news_figures({"figures": [fig(2025, quote="Acme made Rs 2,55,324 crore in FY2025 overall.")]}, [ARTICLE])
        self.assertEqual(got, [])

    def test_number_not_in_the_quote_is_dropped(self):
        got = check_news_figures({"figures": [fig(2025, amount="Rs 3,00,000 crore")]}, [ARTICLE])
        self.assertEqual(got, [])

    def test_quote_must_name_the_year(self):
        got = check_news_figures({"figures": [fig(2023)]}, [ARTICLE])   # the sentence says FY2025
        self.assertEqual(got, [])

    def test_one_figure_per_metric_and_year_and_one_currency(self):
        raw = {"figures": [
            fig(2025), fig(2025),                                        # duplicate year
            fig(2024, amount="Rs 2,40,893 crore", quote="In fiscal 2024, Acme's revenue was Rs 2,40,893 crore."),
            fig(2025, metric="profit", amount="Rs 48,553 crore",
                quote="Net profit for FY2025 stood at Rs 48,553 crore."),
            fig(2024, currency="USD", metric="profit", amount="Rs 2,40,893 crore",
                quote="In fiscal 2024, Acme's revenue was Rs 2,40,893 crore."),
        ]}
        got = check_news_figures(raw, [ARTICLE])
        self.assertEqual(sorted((f.metric, f.year) for f in got), [("profit", 2025), ("revenue", 2024), ("revenue", 2025)])
        self.assertEqual({f.currency for f in got}, {"INR"})

    def test_an_exact_figure_beats_an_approximate_one(self):
        rough_article = {"url": "https://a.example/x", "content": "Revenue fell from nearly Rs 2,41,000 crore in fiscal 2024 to less."}
        raw = {"figures": [
            fig(2024, amount="nearly Rs 2,41,000 crore", quote="Revenue fell from nearly Rs 2,41,000 crore in fiscal 2024 to less.", article_id=1),
            fig(2024, amount="Rs 2,40,893 crore", quote="In fiscal 2024, Acme's revenue was Rs 2,40,893 crore.", article_id=2),
        ]}
        got = check_news_figures(raw, [rough_article, ARTICLE])
        self.assertEqual([(f.year, f.value) for f in got], [(2024, 240893 * 1e7)])

    def test_bad_shapes_never_crash(self):
        for raw in (None, [], {"figures": "x"}, {"figures": [None, {"year": "soon"}, {"article_id": 9}]}):
            self.assertEqual(check_news_figures(raw, [ARTICLE]), [])


def market(n):
    return [Figure(2020 + i, "revenue", 100.0 + i, "USD", "https://finance.yahoo.com/quote/ACME/financials/",
                   "Yahoo Finance (ACME)") for i in range(n)]


class Sources(unittest.TestCase):
    def test_listed_company_uses_market_data(self):
        with mock.patch.object(growth, "find_listing", return_value=("ACME", "Acme Inc")), \
             mock.patch.object(growth, "market_figures", return_value=market(4)), \
             mock.patch.object(growth, "news_figures") as news:
            g = growth.growth_for("Acme", "company", label="Acme, a maker of things")
        self.assertEqual((g.method, g.symbol, g.company, len(g.figures)), ("market", "ACME", "Acme", 4))
        news.assert_not_called()

    def test_unlisted_company_falls_back_to_checked_news(self):
        with mock.patch.object(growth, "find_listing", return_value=None), \
             mock.patch.object(growth, "news_figures", return_value=(market(3), 1, CALL)):
            g = growth.growth_for("Acme", "company")
        self.assertEqual((g.method, g.credits, len(g.calls)), ("news", 1, 1))

    def test_nothing_found_says_so(self):
        with mock.patch.object(growth, "find_listing", return_value=None), \
             mock.patch.object(growth, "news_figures", return_value=(market(1), 1, CALL)):
            g = growth.growth_for("Acme", "company")
        self.assertEqual((g.method, g.figures), ("none", []))
        self.assertIn("No yearly revenue", g.note)


class People(unittest.TestCase):
    def test_company_must_be_named_in_the_articles(self):
        with mock.patch.object(growth, "chat_json", return_value=({"company": "Globex", "role": "CEO"}, CALL)):
            company, _, _ = growth.company_for_person("Jane Doe", ["Jane Doe spoke at Acme's event."])
        self.assertEqual(company, "")

    def test_person_maps_to_their_company(self):
        with mock.patch.object(growth, "chat_json", return_value=({"company": "Acme", "role": "co-founder"}, CALL)), \
             mock.patch.object(growth, "find_listing", return_value=("ACME", "Acme Inc")), \
             mock.patch.object(growth, "market_figures", return_value=market(3)):
            g = growth.growth_for("Jane Doe", "person", texts=["Jane Doe, co-founder of Acme, said..."])
        self.assertEqual((g.company, g.person_role, g.method), ("Acme", "co-founder", "market"))


class PipelineKeepsGoing(unittest.TestCase):
    def test_a_failed_lookup_still_delivers_the_brief(self):
        from tests.test_pipeline import fake_draft, fake_resolve, fake_run
        with mock.patch.object(pipeline, "GROWTH_ON", True), \
             mock.patch.object(pipeline, "search", return_value=fake_run(5)), \
             mock.patch.object(pipeline, "resolve", side_effect=fake_resolve), \
             mock.patch.object(pipeline, "draft", side_effect=fake_draft), \
             mock.patch.object(pipeline, "growth_for", side_effect=RuntimeError("down")):
            b = pipeline.make_brief("Acme", "company", datetime(2026, 11, 1))
        self.assertEqual(b.growth.method, "none")
        self.assertIn("Couldn't look up", b.growth.note)
        self.assertIn("growth", b.timings)


if __name__ == "__main__":
    unittest.main()
