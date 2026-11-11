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

  root.VouchStats = { POINT_REASON, briefNumbers, emptyMessage };
})(typeof window !== "undefined" ? window : globalThis);
