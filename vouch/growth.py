"""Company growth over the years: yearly revenue and profit, every figure with its source.

Two sources, tried in order:
1. Market data. If the company is listed, Yahoo Finance's yearly reported figures
   (company search, then yearly fundamentals). Exact, but listed companies only.
2. News. Otherwise one Tavily search for annual results. The model reads out each
   (year, figure) with the sentence it came from, and code keeps a figure only if that
   sentence is found word for word in the article and contains the figure's number.

For a person, the company is the one the verified articles tie them to; the model names
it and code checks the name appears in those articles.
"""
import os
import re
import time
from dataclasses import dataclass, field

import httpx
from tavily import TavilyClient

from vouch import cache
from vouch.llm import CallInfo, ENTITY_MODEL, chat_json
from vouch.verify import normalise, numbers_in, quote_found

YAHOO_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
YAHOO_SERIES = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
YAHOO_PAGE = "https://finance.yahoo.com/quote/{symbol}/financials/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; vouch)"}
TIMEOUT = 15
YEARS_BACK = 12          # market data rarely goes back further than this anyway
MIN_YEARS = 2            # one year is a number, not growth
METRICS = ("revenue", "profit")

# Listings whose names say they are funds, not the company itself
# ("Zerodha Gold ETF" is a fund run by Zerodha, not Zerodha).
_FUND_WORDS = re.compile(r"\b(etf|fund|funds|index|trust|futures?|bees|reit|ucits|notes?)\b", re.I)
# Words that don't identify a company when comparing names.
_NAME_FILLER = {"limited", "ltd", "inc", "incorporated", "corporation", "corp", "plc", "co",
                "company", "the", "group", "holdings", "sa", "ag", "nv", "llc", "pvt", "private"}
_UNITS = {"thousand": 1e3, "k": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5,
          "million": 1e6, "mn": 1e6, "m": 1e6, "crore": 1e7, "crores": 1e7, "cr": 1e7,
          "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12, "tn": 1e12, "t": 1e12}


@dataclass
class Figure:
    year: int              # the fiscal year, by the year it ends
    metric: str            # "revenue" or "profit"
    value: float           # in whole currency units
    currency: str          # ISO code, e.g. "INR"
    source_url: str
    source_name: str       # "Yahoo Finance (TCS.NS)" or the news site
    quote: str = ""        # news only: the sentence the figure was found in


@dataclass
class Growth:
    company: str                       # whose figures these are
    method: str = "none"               # "market", "news" or "none"
    figures: list[Figure] = field(default_factory=list)
    symbol: str = ""                   # market data only, e.g. "TCS.NS"
    note: str = ""                     # why nothing was found, or which company a person maps to
    person_role: str = ""              # for a person: their role at the company
    credits: int = 0                   # Tavily credits spent here
    calls: list[CallInfo] = field(default_factory=list)
    seconds: float = 0.0


# ---------- names ----------
def clean_company(label: str) -> str:
    """'Infosys, the Indian IT services company' -> 'Infosys';
    'Tata Consultancy Services (TCS)' -> 'Tata Consultancy Services'."""
    label = re.sub(r"\(.*?\)", " ", label or "")
    label = re.split(r",| - | – | — ", label)[0]
    return " ".join(label.split())


def _name_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", normalise(text)) if w not in _NAME_FILLER}


def listing_matches(company: str, listed_name: str) -> bool:
    """A listing is this company only if it isn't a fund and its name is the company's
    name exactly, apart from words like "Limited" or "Inc". "Mercury Systems" is not
    "Mercury" (the startup bank): a near match would chart the wrong company."""
    if not listed_name or _FUND_WORDS.search(listed_name):
        return False
    wanted = _name_words(company)
    return bool(wanted) and wanted == _name_words(listed_name)


# ---------- market data ----------
def _get_json(url: str, params: dict) -> dict:
    key = {"yahoo": url, **params}
    cached = cache.get(key)
    if cached is not None:
        return cached
    r = httpx.get(url, params=params, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    cache.put(key, data)
    return data


def find_listing(company: str) -> tuple[str, str] | None:
    """(symbol, listed name) of the company's own shares, or None if it isn't listed."""
    data = _get_json(YAHOO_SEARCH, {"q": company, "quotesCount": 6, "newsCount": 0})
    for q in data.get("quotes") or []:
        name = q.get("longname") or q.get("shortname") or ""
        if q.get("quoteType") == "EQUITY" and (listing_matches(company, name)
                                               or symbol_matches(company, q.get("symbol", ""), name)):
            return q["symbol"], name
    return None


def symbol_matches(company: str, symbol: str, listed_name: str) -> bool:
    """'TCS' is Tata Consultancy Services because its shares trade as TCS.NS: a name
    typed as the ticker itself. Funds are still never the company."""
    root = symbol.split(".")[0].lower()
    return (bool(root) and not _FUND_WORDS.search(listed_name or "")
            and re.sub(r"[^a-z0-9]", "", normalise(company)) == root)


def market_figures(symbol: str) -> list[Figure]:
    now = int(time.time())
    data = _get_json(YAHOO_SERIES.format(symbol=symbol), {
        "type": "annualTotalRevenue,annualNetIncome",
        "period1": now - YEARS_BACK * 366 * 86400, "period2": now})
    page = YAHOO_PAGE.format(symbol=symbol)
    out = []
    for result in (data.get("timeseries") or {}).get("result") or []:
        kind = (result.get("meta") or {}).get("type", [""])[0]
        metric = {"annualTotalRevenue": "revenue", "annualNetIncome": "profit"}.get(kind)
        for point in result.get(kind) or []:
            if not metric or not point:
                continue
            raw = (point.get("reportedValue") or {}).get("raw")
            if not isinstance(raw, (int, float)):
                continue
            out.append(Figure(year=int(point["asOfDate"][:4]), metric=metric, value=float(raw),
                              currency=point.get("currencyCode") or "", source_url=page,
                              source_name=f"Yahoo Finance ({symbol})"))
    return out


# ---------- news ----------
def parse_amount(text: str) -> float | None:
    """'Rs 2,55,324 crore' -> 2.55324e12; '$60.9 billion' -> 6.09e10; '1,234' -> 1234."""
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([a-zA-Z]+)?\.?\s*([a-zA-Z]+)?", text or "")
    if not m:
        return None
    number = float(m.group(1).replace(",", ""))
    scale = 1.0
    for word in (m.group(2), m.group(3)):          # "lakh crore" = 1e5 * 1e7
        factor = _UNITS.get((word or "").lower())
        if factor is None:
            break
        scale *= factor
    return number * scale


def _year_in(year: int, text: str) -> bool:
    """The quote must name the year: '2025', 'FY25', 'FY2025', 'fiscal 2025'."""
    t = normalise(text)
    return str(year) in t or f"fy{year % 100:02d}" in t.replace(" ", "").replace("'", "")


GROWTH_SYSTEM = """You read news articles and pull out a company's yearly financial results.
Only report a figure that is written in the article. Copy the exact sentence it appears in.
Reply with JSON only."""

GROWTH_SHAPE = """{"figures": [{"year": 2025, "metric": "revenue", "amount": "Rs 2,55,324 crore",
  "currency": "INR", "article_id": 1, "quote": "the exact sentence from the article"}]}
"metric" is "revenue" (total revenue / turnover / sales) or "profit" (net profit / net income).
"year" is the fiscal year, by the calendar year it ends in. Full-year figures only: no quarters.
Report every year you find, across all the articles. A sentence that compares two years
("rose to X in FY25 from Y in FY24") gives two figures, one per year, both with that sentence.
Leave out anything you can't copy word for word. An empty list is a fine answer."""


def news_figures(company: str) -> tuple[list[Figure], int, CallInfo | None]:
    """(verified figures, credits spent, model call)."""
    params = {"query": f"{company} annual revenue net profit full year results",
              "topic": "general", "search_depth": "basic", "max_results": 8}
    response, credits = cache.get(params), 0
    if response is None:
        response = TavilyClient(api_key=os.environ["TAVILY_API_KEY"]).search(**params)
        cache.put(params, response)
        credits = 1
    articles = [r for r in response.get("results") or [] if r.get("content")]
    if not articles:
        return [], credits, None

    numbered = "\n\n".join(f"[{i}] {a.get('title', '')}\n{' '.join(a['content'].split())[:1500]}"
                           for i, a in enumerate(articles, 1))
    raw, call = chat_json(GROWTH_SYSTEM,
                          f"Company: {company}\n\nReply in this JSON shape:\n{GROWTH_SHAPE}\n\nARTICLES:\n{numbered}",
                          max_tokens=2500, model=ENTITY_MODEL)
    return check_news_figures(raw, articles), credits, call


_ROUGH = re.compile(r"\b(nearly|about|around|over|almost|approximately|roughly|close to|more than|less than|upwards of)\b|~", re.I)


def check_news_figures(raw: dict, articles: list[dict]) -> list[Figure]:
    """Keep a figure only if its sentence is in the article, word for word, and that
    sentence contains the figure's number and names its year. One figure per metric
    and year (the first that passes)."""
    kept: dict[tuple[str, int], Figure] = {}
    rough: dict[tuple[str, int], Figure] = {}       # "nearly Rs 10,000 crore": used only if nothing exact
    items = raw.get("figures") if isinstance(raw, dict) else None
    for f in items if isinstance(items, list) else []:
        if not isinstance(f, dict):
            continue
        metric, quote, amount = f.get("metric"), str(f.get("quote") or ""), str(f.get("amount") or "")
        try:
            year, idx = int(f.get("year")), int(f.get("article_id"))
        except (TypeError, ValueError):
            continue
        if metric not in METRICS or not (2000 <= year <= time.gmtime().tm_year + 1):
            continue
        if not (1 <= idx <= len(articles)) or (metric, year) in kept:
            continue
        article = articles[idx - 1]
        value = parse_amount(amount)
        digits = re.search(r"\d[\d,]*(?:\.\d+)?", amount)
        if value is None or not digits:
            continue
        if not quote_found(quote, article.get("content", "")):
            continue                                   # not word for word: dropped
        if digits.group(0).replace(",", "") not in numbers_in(quote) or not _year_in(year, quote):
            continue                                   # the sentence doesn't hold this figure
        url = str(article.get("url") or "")
        site = url.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")
        figure = Figure(year, metric, value, str(f.get("currency") or "").upper()[:3], url, site, quote)
        if _ROUGH.search(amount):
            rough.setdefault((metric, year), figure)
        else:
            kept[(metric, year)] = figure
    for key, figure in rough.items():                # an exact figure always wins
        kept.setdefault(key, figure)
    # Figures in different currencies can't share an axis: keep the most common one.
    figures = list(kept.values())
    if figures:
        main = max({x.currency for x in figures}, key=lambda c: sum(x.currency == c for x in figures))
        figures = [x for x in figures if x.currency == main]
    return figures


# ---------- people ----------
PERSON_SYSTEM = """You read news articles about a person and name the company they are most
associated with in these articles. Reply with JSON only."""


def company_for_person(name: str, texts: list[str]) -> tuple[str, str, CallInfo | None]:
    """(company, role, call). The company must be named in the articles themselves."""
    if not texts:
        return "", "", None
    numbered = "\n\n".join(f"[{i}] {' '.join(t.split())[:600]}" for i, t in enumerate(texts[:12], 1))
    raw, call = chat_json(PERSON_SYSTEM,
                          f'Person: "{name}"\nReply as {{"company": "...", "role": "..."}}, '
                          'or {"company": null} if no company is clear.\n\nARTICLES:\n' + numbered,
                          max_tokens=400, model=ENTITY_MODEL)
    company = clean_company(str((raw or {}).get("company") or ""))
    role = " ".join(str((raw or {}).get("role") or "").split())[:60]
    everything = normalise(" ".join(texts))
    if not company or normalise(company) not in everything:
        return "", "", call                            # not named in the articles: no guess
    return company, role, call


# ---------- the step ----------
def growth_for(name: str, kind: str, label: str = "", texts: list[str] | None = None) -> Growth:
    start = time.time()
    g = Growth(company=clean_company(label) or name)
    if kind == "person":
        company, role, call = company_for_person(name, texts or [])
        if call:
            g.calls.append(call)
        if not company:
            g.company, g.note = "", f"The articles don't tie {name} to one company, so there is no company growth to show."
            g.seconds = round(time.time() - start, 1)
            return g
        g.company, g.person_role = company, role

    listing = find_listing(g.company)
    if listing:
        g.symbol = listing[0]
        figures = market_figures(g.symbol)
        if sum(f.metric == "revenue" for f in figures) >= MIN_YEARS:
            g.method, g.figures = "market", sorted(figures, key=lambda f: (f.metric, f.year))
            g.seconds = round(time.time() - start, 1)
            return g

    figures, g.credits, call = news_figures(g.company)
    if call:
        g.calls.append(call)
    if sum(f.metric == "revenue" for f in figures) >= MIN_YEARS:
        g.method, g.figures = "news", sorted(figures, key=lambda f: (f.metric, f.year))
    else:
        g.note = (f"No yearly revenue for {g.company} in market data or the news "
                  "that could be checked word for word.")
    g.seconds = round(time.time() - start, 1)
    return g
