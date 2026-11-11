// The numbers a brief shows about itself, worked out from the brief's own data only.
// No DOM here, so tests can run it under Node (tests/test_frontend_stats.py).
//
// Units are kept apart on purpose: articles are counted with articles, stories with stories.
(function (root) {
  // vouch/verify.py gives every removed talking point or question this exact reason; every
  // other removal in ledger.draft is a story. A test checks this string still matches.
  const POINT_REASON = "not linked to any verified story";

  function briefNumbers(b) {
    const counts = b.counts || {};
    const stories = b.stories || [];
    const draftRemovals = (b.ledger && b.ledger.draft) || [];
    const found = counts.found || 0;
    const kept = counts.kept || 0;
    const verified = stories.length;
    const removed = draftRemovals.filter((r) => r.reason !== POINT_REASON).length;
    const multi = stories.filter((s) => (s.outlets || []).length > 1).length;
    return {
      articles: { found, kept, filteredOut: Math.max(0, found - kept) },
      stories: {
        drafted: verified + removed, verified, removed,
        multi, single: verified - multi,
        older: stories.filter((s) => s.older_event).length,
      },
    };
  }

  // What the page says when no story could be vouched for. Never empty, never "null".
  function emptyMessage(b) {
    return (b.counts && b.counts.kept)
      ? "No story survived the checks, so there's nothing we can vouch for. The ledger below shows why."
      : "No recent news about this subject passed the filters. Check the spelling, or try the full name.";
  }

  // Every rejection reason the server writes, grouped under a short label.
  // Anything not listed here keeps its own wording, so nothing is hidden.
  const REASONS = [
    [/only mentioned in passing/i, "Only mentioned in passing"],
    [/^not a news article/i, "Not a news article"],
    [/^duplicate/i, "Duplicate of a page already kept"],
    [/no publish date/i, "No publish date"],
    [/outside the window/i, "Outside the 30-day window"],
    [/^never mentions/i, "Never names the subject"],
    [/not a normal web address/i, "Unsafe link"],
    [/^about a different/i, "About a different subject"],
    [/^not read/i, "Not read: past the reading limit"],
    [/quote not found/i, "Quote not found word for word"],
    [/^figure\(s\)/i, "A figure isn't in the sources"],
    [/cites no real article|doesn't exist/i, "Cites no real article"],
    [/doesn't back up/i, "Quote doesn't back up the claim"],
    [new RegExp(POINT_REASON, "i"), "Point not linked to a verified story"],
  ];
  const reasonLabel = (reason) => {
    const hit = REASONS.find(([re]) => re.test(reason || ""));
    return hit ? hit[1] : (reason || "No reason given");
  };

  // Rejections counted by reason, largest first.
  function reasonGroups(b) {
    const ledger = b.ledger || {};
    const counts = new Map();
    for (const r of [...(ledger.articles || []), ...(ledger.draft || [])]) {
      const label = reasonLabel(r.reason);
      counts.set(label, (counts.get(label) || 0) + 1);
    }
    return [...counts].map(([label, count]) => ({ label, count })).sort((a, z) => z.count - a.count);
  }

  // The pipeline as a funnel. Articles are counted with articles and stories with
  // stories; `unit` says which, so the page never compares one with the other.
  function funnelSteps(b) {
    const counts = b.counts || {};
    const articles = (b.ledger && b.ledger.articles) || [];
    const setAside = articles.filter((r) => /^about a different/i.test(r.reason || "")).length;
    const notRead = articles.filter((r) => /^not read/i.test(r.reason || "")).length;
    const filteredOut = articles.length - setAside - notRead;
    const found = counts.found || 0;
    const passed = Math.max(0, found - filteredOut);
    const { stories } = briefNumbers(b);
    return [
      { key: "found", label: "Found", value: found, unit: "articles", who: `Tavily, ${counts.searches || 4} news searches` },
      { key: "filtered", label: "Passed the filters", value: passed, unit: "articles", who: "Code rules" },
      { key: "subject", label: "About this subject", value: Math.max(0, passed - setAside), unit: "articles", who: "Model sorts, code decides" },
      { key: "read", label: "Read by the AI", value: counts.shown_to_model || 0, unit: "articles", who: "The newest articles" },
      { key: "drafted", label: "Stories drafted", value: stories.drafted, unit: "stories", who: "Model, via Bifrost" },
      { key: "verified", label: "Verified", value: stories.verified, unit: "stories", who: "Code checks every quote" },
    ];
  }

  // Yearly figures as chart series. Change is year on year, from the brief's own figures.
  function growthSeries(g) {
    if (!g || !Array.isArray(g.figures) || !g.figures.length) return null;
    const pick = (metric) => g.figures.filter((f) => f.metric === metric)
      .sort((a, z) => a.year - z.year)
      .map((f, i, all) => ({ ...f, change: i && all[i - 1].value ? (f.value - all[i - 1].value) / Math.abs(all[i - 1].value) : null }));
    const revenue = pick("revenue"), profit = pick("profit");
    if (revenue.length < 2) return null;
    return { currency: revenue[revenue.length - 1].currency, revenue, profit,
             first: revenue[0], latest: revenue[revenue.length - 1] };
  }

  // "Numbers to have ready" for the meeting: picked by code from figures that were already
  // checked (market data or word-for-word news) and from the verified stories. No AI writes these.
  function numbersToHave(b) {
    const out = [];
    const s = growthSeries(b.growth);
    if (s) {
      out.push({ kind: "revenue", year: s.latest.year, value: s.latest.value, currency: s.currency,
                 change: s.latest.change, source_url: s.latest.source_url, source_name: s.latest.source_name });
      if (s.revenue.length > 2) {
        out.push({ kind: "span", from: s.first.year, to: s.latest.year,
                   change: (s.latest.value - s.first.value) / Math.abs(s.first.value),
                   source_url: s.latest.source_url, source_name: s.latest.source_name });
      }
      const profit = s.profit.find((p) => p.year === s.latest.year);
      if (profit) {
        out.push({ kind: "profit", year: profit.year, value: profit.value, currency: profit.currency,
                   margin: profit.value / s.latest.value, source_url: profit.source_url, source_name: profit.source_name });
      }
    }
    const stories = (b.stories || []).map((st, i) => ({ ...st, n: i + 1 }));
    if (stories.length) {
      const top = stories.reduce((a, z) => ((z.outlets || []).length > (a.outlets || []).length ? z : a));
      if ((top.outlets || []).length > 1) {
        out.push({ kind: "coverage", story: top.n, headline: top.headline, outlets: top.outlets.length });
      }
      const newest = stories.reduce((a, z) => (z.date > a.date ? z : a));
      out.push({ kind: "latest", story: newest.n, headline: newest.headline, date: newest.date });
    }
    const n = briefNumbers(b);
    if (n.stories.drafted) out.push({ kind: "checked", verified: n.stories.verified, drafted: n.stories.drafted });
    return out;
  }

  root.VouchStats = { POINT_REASON, briefNumbers, emptyMessage, reasonGroups, reasonLabel, funnelSteps, growthSeries,
                      numbersToHave };
})(typeof window !== "undefined" ? window : globalThis);
