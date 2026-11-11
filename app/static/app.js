// Vouch front end. Every piece of text from the web is inserted with
// textContent (never innerHTML), so an article can't inject code into the page.

const $ = (id) => document.getElementById(id);

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {  // nested lists of elements are fine
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const fmtDate = (iso) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const GOAL_LABEL = { investor: "Investor", sales: "Sales", partnership: "Partnership",
                     bizdev: "Business development", hiring: "Hiring", general: "General" };

// Default the meeting to tomorrow at 10:00, in the user's own time zone.
const tomorrow = new Date(Date.now() + 86400000);
const pad = (n) => String(n).padStart(2, "0");
$("meeting").value = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T10:00`;

// ---------- live progress ----------
const STAGES = {
  search: { running: "Searching the last 30 days of news",
            done: (d) => `Found ${plural(d.found, "article")}` +
                         (d.credits ? ` (${plural(d.credits, "search credit")} used)` : " (from cache, no credits used)") +
                         (d.failed && d.failed.length ? `; the ${d.failed.join(", ")} search failed` : "") },
  filter: { done: (d) => `Kept ${d.kept}, threw out ${d.rejected}` },
  entity: { running: "Checking every article is about the same one",
            done: (d) => d.skipped ? "Couldn't run the same-subject check; continuing without it"
                       : d.needs_choice ? `Found ${d.groups} different subjects with this name`
                       : d.set_aside ? `Kept ${d.kept} about ${d.label || "this subject"}, set aside ${d.set_aside} about others`
                       : `All ${d.kept} articles are about the same subject` },
  draft:  { running: (d) => `Writing the draft with ${d.model}`,
            done: (d) => `Draft written by ${d.served_by} in ${d.seconds}s` +
                         (d.fallback ? " (backup model took over)" : "") },
  verify: { done: (d) => `Checked every quote: ${d.verified} verified, ${d.removed} removed` },
  growth: { running: "Looking up yearly revenue and profit",
            done: (d) => d.method === "market" ? `${plural(d.years, "year")} of figures from market data (${d.symbol})`
                       : d.method === "news" ? `${plural(d.years, "year")} of figures from the news, each checked word for word`
                       : "No yearly figures that could be checked" },
};

// The five stages in the order the server runs them, and who does each one.
const STAGE_ORDER = [
  ["search", "Search", "Tavily"],
  ["filter", "Filter", "Code"],
  ["entity", "Same subject", "Model sorts, code decides"],
  ["draft",  "Draft", "Model, via Bifrost"],
  ["verify", "Verify", "Code"],
  ["growth", "Growth", "Market data or news, checked in code"],
];

// Every stage is listed from the start, waiting, so the run reads as a known sequence.
function resetStages() {
  $("progress").replaceChildren(...STAGE_ORDER.map(([key, step, who]) =>
    h("li", { "data-stage": key, class: "pending" },
      h("span", { class: "mark", "aria-hidden": "true" }),
      h("span", { class: "step", text: step }),
      h("span", { class: "who", text: who }),
      h("span", { class: "label", text: "Waiting" }))));
  updateMeter();
}

function updateMeter() {
  const done = $("progress").querySelectorAll("li.done").length;
  $("meter").setAttribute("aria-valuenow", done);
  $("meter").setAttribute("aria-valuemax", STAGE_ORDER.length);
  $("meter").style.setProperty("--done", done / STAGE_ORDER.length);
}

function showStep(stage, data) {
  const li = $("progress").querySelector(`[data-stage="${stage}"]`);
  const spec = STAGES[stage] && STAGES[stage][data.status];
  if (!li || !spec) return;
  li.className = data.status;
  li.querySelector(".label").textContent = typeof spec === "function" ? spec(data) : spec;
  updateMeter();
}

function showFailure(message) {
  $("progress").querySelectorAll("li.running").forEach((li) => {
    li.className = "stopped";
    li.querySelector(".label").textContent = "Stopped";
  });
  $("analysis-error").textContent = message;
  $("analysis-error").hidden = false;
  $("cancel").textContent = "Back to the question";
}

// ---------- big names: always one line, shrunk to fit ----------
// A company or person's name is set very large. Instead of breaking it inside a word
// ("Accent / ure"), keep it on one line and step the size down until it fits. Only if it
// still doesn't fit at the smallest size does it wrap, and then only between words.
const FIT_MIN_PX = 28;
function fitOneLine(el) {
  if (!el || !el.offsetParent) return;          // not on screen: nothing to measure
  el.classList.remove("fits-wrap");
  el.style.fontSize = "";                       // start again from the stylesheet's size
  let size = parseFloat(getComputedStyle(el).fontSize);
  while (el.scrollWidth > el.clientWidth + 1 && size > FIT_MIN_PX) {
    size = Math.max(FIT_MIN_PX, size * 0.92);
    el.style.fontSize = `${size}px`;
  }
  if (el.scrollWidth > el.clientWidth + 1) el.classList.add("fits-wrap");
}
const fitNames = () => ["result-title", "analysis-title"].forEach((id) => fitOneLine($(id)));
let fitTimer = null;
window.addEventListener("resize", () => { clearTimeout(fitTimer); fitTimer = setTimeout(fitNames, 120); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitNames);   // re-measure once fonts land

// ---------- screens: the question, the analysis, the brief ----------
let clock = null;

function showAnalysis(name, goal, meeting) {
  $("analysis-title").textContent = name;
  $("analysis-title").dataset.name = name;   // the glow layer copies the name (CSS attr, never parsed as HTML)
  $("analysis-context").textContent =
    `${GOAL_LABEL[goal] || "General"} meeting on ${fmtDate(meeting.slice(0, 10))} at ${meeting.slice(11, 16)}. ` +
    "Reading the last 30 days of news, then checking every quote in code.";
  $("analysis-error").hidden = true;
  $("cancel").textContent = "Cancel";
  resetStages();

  const started = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - started) / 1000);
    $("elapsed").textContent = `${Math.floor(s / 60)}:${pad(s % 60)}`;
  };
  tick();
  clearInterval(clock);
  clock = setInterval(tick, 1000);

  document.querySelector(".entry").hidden = true;
  $("result").hidden = true;
  $("analysis").hidden = false;
  window.scrollTo(0, 0);
  fitOneLine($("analysis-title"));
  $("analysis-title").focus({ preventScroll: true });
}

function showQuestion() {
  clearInterval(clock);
  $("analysis").hidden = true;
  document.querySelector(".entry").hidden = false;
}

// ---------- the brief ----------
function storyRow(s, i) {
  const quote = h("blockquote", { class: "quote" },
    h("mark", { text: `“${s.quote}”` }),
    h("cite", {}, "Found word for word in ",
      s.quote_url ? h("a", { href: s.quote_url, target: "_blank", rel: "noopener", text: s.quote_site }) : s.quote_site));

  const sources = h("details", { class: "sources" },
    h("summary", { text: `${plural(s.sources.length, "article")} behind this` }),
    h("ul", {}, s.sources.map((src) =>
      h("li", {}, src.url ? h("a", { href: src.url, target: "_blank", rel: "noopener", text: src.title }) : src.title,
        ` (${src.site}, ${fmtDate(src.date)})`))));

  return h("article", { class: "row", id: `story-${i + 1}` },
    h("div", { class: "story" },
      h("h4", {}, h("span", { class: "num", text: `${i + 1}.` }), s.headline),
      h("p", { class: "summary", text: s.summary }),
      quote, sources),
    // The proof margin. Each flag is a drawn icon (CSS, by class) plus its words, never colour alone.
    h("div", { class: "margin" },
      h("span", { class: "flag reported", text: `Reported ${fmtDate(s.date)}` }),
      s.older_event ? h("span", { class: "flag older", text: `Older event: ${s.older_event}` }) : null,
      s.outlets.length > 1
        ? h("span", { class: "flag outlets", text: `Reported by ${s.outlets.length} outlets` })
        : h("span", { class: "flag single", text: "Single source" }),
      h("span", { class: "flag check", text: "Quote verified" })));
}

// ---------- the numbers: drawn from this brief's own data only ----------
const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") el.textContent = v;
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) if (c) el.append(c);
  return el;
}

// Money in the reader's terms: rupees in crore as Indian reports write them ("₹2,67,021 cr"),
// everything else compact ("$215.9B").
function money(value, currency) {
  if (currency === "INR" && Math.abs(value) >= 1e7) {
    return `₹${Math.round(value / 1e7).toLocaleString("en-IN")} cr`;
  }
  const locale = currency === "INR" ? "en-IN" : "en-US";
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency: currency || "USD",
      notation: "compact", maximumFractionDigits: 2 }).format(value);
  } catch (e) {
    return `${new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 2 }).format(value)} ${currency || ""}`.trim();
  }
}
const pct = (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(1)}%`;
const fy = (year) => `FY${year}`;

// One bar per year; every bar links to the page its figure came from.
function barChart(series, { height, label }) {
  const top = 34, bottom = 30, plot = height - top - bottom;
  const max = Math.max(...series.map((f) => Math.abs(f.value))) || 1;
  const slot = 100 / series.length;
  return svg("svg", { class: "bars", width: "100%", height, role: "img", "aria-label": label },
    svg("line", { class: "base", x1: "0%", x2: "100%", y1: top + plot, y2: top + plot }),
    series.map((f, i) => {
      const hgt = Math.max(2, (Math.abs(f.value) / max) * plot);
      const x = i * slot + slot * 0.2, w = slot * 0.6, cx = `${i * slot + slot / 2}%`;
      const y = f.value >= 0 ? top + plot - hgt : top + plot;
      const labelY = (f.value >= 0 ? y : top + plot);
      const said = `${fy(f.year)}: ${money(f.value, f.currency)}` +
                   (f.change != null ? `, ${pct(f.change)} on the year before` : "") +
                   `. Source: ${f.source_name}` + (f.quote ? ` “${f.quote}”` : "");
      const bar = svg("g", { class: `bar${i === series.length - 1 ? " bar-latest" : ""}${f.value < 0 ? " bar-negative" : ""}`,
                             style: `--i:${i}` },
        svg("title", { text: said }),
        svg("rect", { x: `${x}%`, y, width: `${w}%`, height: hgt, rx: 3 }),
        svg("text", { class: "val", x: cx, y: labelY - 20, "text-anchor": "middle", text: money(f.value, f.currency) }),
        f.change != null ? svg("text", { class: `chg${f.change < 0 ? " down" : ""}`, x: cx, y: labelY - 5,
                                         "text-anchor": "middle", text: pct(f.change) }) : null,
        svg("text", { class: "yr", x: cx, y: top + plot + 20, "text-anchor": "middle", text: fy(f.year) }));
      return f.source_url ? svg("a", { href: f.source_url, target: "_blank", rel: "noopener", "aria-label": said }, bar) : bar;
    }));
}

function heroGrowth(b) {
  const g = b.growth;
  if (!g) return null;
  const s = VouchStats.growthSeries(g);
  const title = b.subject.kind === "person" && g.company
    ? `Growth of ${g.company}` + (g.person_role ? `, where ${b.subject.name} is ${g.person_role}` : `, ${b.subject.name}’s company`)
    : `Growth of ${g.company || b.subject.name}`;
  const how = g.method === "market"
    ? `Yearly reported figures from Yahoo Finance (${g.symbol}), in ${s ? s.currency : ""}. Each bar links to the source.`
    : g.method === "news"
      ? "From news reports of annual results. Each figure was found word for word in its article, and each bar links to it."
      : "";
  return h("section", { class: "hero-growth", "aria-labelledby": "growth-title" },
    h("div", { class: "panel-head" },
      h("h3", { id: "growth-title", text: title }),
      how ? h("p", { class: "panel-note", text: how }) : null),
    s ? [
      h("div", { class: "growth-summary" },
        h("p", {}, h("span", { class: "k", text: `Revenue, ${fy(s.latest.year)}` }),
          h("strong", { text: money(s.latest.value, s.currency) })),
        s.latest.change != null ? h("p", {}, h("span", { class: "k", text: "On the year before" }),
          h("strong", { class: s.latest.change < 0 ? "down" : "up", text: pct(s.latest.change) })) : null,
        s.revenue.length > 2 ? h("p", {}, h("span", { class: "k", text: `${fy(s.first.year)} to ${fy(s.latest.year)}` }),
          h("strong", { text: pct((s.latest.value - s.first.value) / Math.abs(s.first.value)) })) : null),
      h("h4", { class: "chart-title", text: "Revenue" }),
      barChart(s.revenue, { height: 200, label: `Revenue by fiscal year, ${s.currency}` }),
      s.profit.length >= 2 ? [h("h4", { class: "chart-title", text: "Net profit" }),
        barChart(s.profit, { height: 140, label: `Net profit by fiscal year, ${s.currency}` })] : null,
    ] : h("p", { class: "panel-empty", text: g.note || "No yearly figures could be found and checked." }));
}

// The pipeline, made visible: the funnel, why things were left out, and how it was made.
function proofPanel(b) {
  const steps = VouchStats.funnelSteps(b);
  const reasons = VouchStats.reasonGroups(b);
  const maxReason = reasons.length ? reasons[0].count : 1;
  const base = { articles: steps[0].value || 1, stories: steps[4].value || 1 };
  const m = b.model, g = b.growth, c = b.counts;
  const stagesTimed = Object.entries(b.timings || {}).filter(([, sec]) => sec > 0);
  const totalTimed = stagesTimed.reduce((sum, [, sec]) => sum + sec, 0) || 1;
  const STAGE_NAME = { search: "Search", filter: "Filter", entity: "Same subject", draft: "Draft",
                       verify: "Verify", growth: "Growth" };

  const made = [
    ["Search", `Tavily, ${plural(c.credits || 0, "credit")}` + (c.cache_hits ? `, ${c.cache_hits} of 4 searches from cache` : "")],
    m && m.entity_check_by ? ["Same-subject check", `${m.entity_check_by}, ${m.entity_check_tokens.toLocaleString()} tokens`] : null,
    m ? ["Draft", `${m.served_by}${m.fallback ? " (backup model; the first choice was unavailable)" : ""}, ` +
                  `${(m.prompt_tokens + m.completion_tokens).toLocaleString()} tokens, ${m.seconds}s`] : null,
    ["Checks", "Plain code: quotes word for word, figures in the sources, quote backs the claim"],
    g ? ["Growth", g.method === "market" ? `Yahoo Finance market data (${g.symbol})`
                 : g.method === "news" ? `News, ${plural(g.credits, "credit")}, ${g.tokens.toLocaleString()} tokens, figures checked in code`
                 : "Nothing that could be checked"] : null,
    m ? ["Gateway", "Bifrost, with Vouch’s own virtual key and daily limits"] : null,
    ["Total time", `${b.seconds}s`],
  ].filter(Boolean);

  return h("section", { class: "panel proof", "aria-labelledby": "proof-title" },
    h("div", { class: "panel-head" },
      h("h3", { id: "proof-title", text: "How this brief was checked" }),
      h("p", { class: "panel-note", text: "Every stage, with the real counts from this run. Articles and stories are counted separately." })),
    h("ol", { class: "funnel-steps" }, steps.map((st) =>
      h("li", { class: `fstep fstep-${st.unit}`, style: `--p:${Math.min(1, st.value / base[st.unit])}` },
        h("span", { class: "step-value", text: String(st.value) }),
        h("span", { class: "step-label", text: st.label }),
        h("span", { class: "step-unit", text: st.unit }),
        h("span", { class: "step-bar", "aria-hidden": "true" }),
        h("span", { class: "step-who", text: st.who })))),
    h("div", { class: "proof-cols" },
      h("div", { class: "proof-col" },
        h("h4", { text: "Why things were left out" }),
        reasons.length
          ? h("ul", { class: "reasons" }, reasons.map((r) =>
              h("li", { style: `--p:${r.count / maxReason}` },
                h("span", { class: "reason-label", text: r.label }),
                h("span", { class: "reason-count", text: String(r.count) }),
                h("span", { class: "reason-bar", "aria-hidden": "true" }))))
          : h("p", { class: "panel-empty", text: "Nothing was left out." })),
      h("div", { class: "proof-col" },
        h("h4", { text: "How it was made" }),
        h("dl", { class: "made" }, made.map(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })])),
        stagesTimed.length ? [
          h("h4", { class: "time-title", text: "Time per stage" }),
          h("div", { class: "timebar", "aria-hidden": "true" }, stagesTimed.map(([k, sec], i) =>
            h("span", { class: `seg seg-${i % 6}`, style: `--w:${sec / totalTimed}`, title: `${STAGE_NAME[k] || k}: ${sec}s` }))),
          h("ul", { class: "timelegend" }, stagesTimed.map(([k, sec], i) =>
            h("li", {}, h("span", { class: `sw seg-${i % 6}`, "aria-hidden": "true" }), `${STAGE_NAME[k] || k} ${sec}s`))),
        ] : null)));
}

function pointList(points) {
  return h("ol", { class: "points" }, points.map((p) =>
    h("li", {}, p.text, h("span", { class: "ref" }, "(",
      p.stories.map((n, j) => [j ? ", " : "", h("a", { href: `#story-${n}`, text: `story ${n}` })]), ")"))));
}

function ledger(l) {
  const total = l.articles.length + l.draft.length;
  if (!total) return null;
  // Identical rejections (same title, same reason) are shown once with a count.
  const group = (items) => {
    const seen = new Map();
    for (const r of items) {
      const key = (r.title || r.item) + "|" + r.reason;
      if (seen.has(key)) seen.get(key).count += 1;
      else seen.set(key, { ...r, count: 1 });
    }
    return [...seen.values()];
  };
  const rows = (items, title) => items.length ? h("div", { class: "ledger-group" },
    h("h4", { text: title }),
    group(items).map((r) => h("div", { class: "row", "data-reason": VouchStats.reasonLabel(r.reason) },
      h("p", { class: "struck" },
        r.url ? h("a", { href: r.url, target: "_blank", rel: "noopener", text: r.title }) : (r.title || r.item),
        r.count > 1 ? h("span", { class: "times", text: ` ×${r.count}` }) : null),
      h("span", { class: "reason", text: r.reason })))) : null;
  const groups = VouchStats.reasonGroups({ ledger: l });
  return h("section", { class: "part ledger", "aria-labelledby": "ledger-title" },
    h("h3", { id: "ledger-title", text: `What we left out (${total})` }),
    h("p", { class: "ledger-intro", text: "Nothing is dropped silently. Each item below was removed by a rule in code, not by the AI." }),
    h("div", { class: "ledger-chips", role: "group", "aria-label": "Show only one reason" },
      h("button", { type: "button", class: "ledger-chip", "data-reason": "", "aria-pressed": "true" }, "All ", h("span", { text: String(total) })),
      groups.map((g) => h("button", { type: "button", class: "ledger-chip", "data-reason": g.label, "aria-pressed": "false" },
        `${g.label} `, h("span", { text: String(g.count) })))),
    rows(l.articles, "Articles that didn't qualify"),
    rows(l.draft, "Lines the AI wrote that failed our checks"));
}

function renderChoices(b) {
  const r = $("result");
  r.replaceChildren(h("section", { class: "choose", "aria-labelledby": "result-title" },
    h("h3", { id: "result-title", text: `Which ${b.subject.name} do you mean?` }),
    h("p", { text: `The news mentions ${b.choices.length} different subjects with this name. ` +
                   "Pick one and Vouch will search again for that one only." }),
    h("ul", {}, b.choices.map((c) => h("li", {},
      h("button", { type: "button", "data-label": c.label },
        c.label, h("span", { text: plural(c.count, "article") })))))));
  r.querySelectorAll("button[data-label]").forEach((btn) => btn.addEventListener("click", () => {
    $("about").value = btn.dataset.label;
    $("ask").requestSubmit();
  }));
  r.hidden = false;
  window.scrollTo(0, 0);
}

// ---------- the brief as a one-screen workspace ----------
// A sidebar of sections; the open one fills the screen. Nothing on the page scrolls on a
// laptop or desktop: a long list scrolls inside its own panel. Print still gives every section.
const VIEWS = [
  ["overview", "Overview"],
  ["stories", "Stories"],
  ["meeting", "Your meeting"],
  ["leftout", "Left out"],
  ["proof", "The proof"],
];

// A tiny bar sparkline from real figures (the growth series), for the KPI strip.
function spark(series) {
  if (!series || series.length < 2) return null;
  const max = Math.max(...series.map((f) => Math.abs(f.value))) || 1;
  const slot = 100 / series.length;
  return svg("svg", { class: "spark", width: "100%", height: 26, "aria-hidden": "true" },
    series.map((f, i) => {
      const hgt = Math.max(2, (Math.abs(f.value) / max) * 24);
      return svg("rect", { class: i === series.length - 1 ? "spark-latest" : "", x: `${i * slot + slot * 0.18}%`,
                           y: 26 - hgt, width: `${slot * 0.64}%`, height: hgt, rx: 1.5 });
    }));
}

function kpiStrip(b) {
  const s = VouchStats.growthSeries(b.growth);
  const { articles, stories } = VouchStats.briefNumbers(b);
  const leftOut = b.ledger.articles.length + b.ledger.draft.length;
  const profitNow = s && s.profit.find((p) => p.year === s.latest.year);
  const meter = (p, tone) => h("span", { class: `kpi-meter kpi-${tone}`, style: `--p:${Math.max(0, Math.min(1, p))}`, "aria-hidden": "true" });
  const tile = (label, value, note, viz, tone = "") =>
    h("div", { class: `kpi ${tone}` }, h("p", { class: "kpi-label", text: label }),
      h("p", { class: "kpi-value", text: value }), note ? h("p", { class: "kpi-note", text: note }) : null, viz);
  return h("section", { class: "ws-kpis", "aria-label": "Key figures" },
    tile(s ? `Revenue, ${fy(s.latest.year)}` : "Revenue", s ? money(s.latest.value, s.currency) : "Not found",
         s && s.latest.change != null ? `${pct(s.latest.change)} on ${fy(s.latest.year - 1)}` : "No yearly figure could be checked",
         s ? spark(s.revenue) : null),
    tile(profitNow ? `Net profit, ${fy(profitNow.year)}` : "Net profit", profitNow ? money(profitNow.value, profitNow.currency) : "Not found",
         profitNow ? `${(profitNow.value / s.latest.value * 100).toFixed(1)}% of revenue` : "", s ? spark(s.profit) : null, "kpi-sand"),
    tile("Stories verified", stories.drafted ? `${stories.verified} of ${stories.drafted}` : "0",
         "drafted stories passed every check", meter(stories.drafted ? stories.verified / stories.drafted : 0, "sand"), "kpi-brand"),
    tile("Articles read", String((b.counts && b.counts.shown_to_model) || 0), `of ${articles.found} found, ${articles.kept} kept`,
         meter(articles.found ? ((b.counts && b.counts.shown_to_model) || 0) / articles.found : 0, "brand")),
    tile("Left out", String(leftOut), "each with its reason", meter(articles.found ? b.ledger.articles.length / articles.found : 0, "deep")),
    tile("Made in", `${b.seconds}s`, `${plural(Object.keys(b.timings || {}).length || 5, "stage")}, checked in code`, null));
}

function storyList(b) {
  return h("ol", { class: "story-list", "aria-label": "Stories" }, b.stories.map((s, i) =>
    h("li", {},
      h("button", { type: "button", class: "story-pick", "data-story": String(i + 1), "aria-controls": `story-${i + 1}` },
        h("span", { class: "pick-num", text: String(i + 1) }),
        h("span", { class: "pick-text" },
          h("span", { class: "pick-head", text: s.headline }),
          h("span", { class: "pick-meta", text: [fmtDate(s.date),
            s.outlets.length > 1 ? `${s.outlets.length} outlets` : "Single source",
            s.older_event ? `Older event: ${s.older_event}` : null].filter(Boolean).join(", ") }))))));
}

function workspace(b, views) {
  const c = b.counts, m = b.model, g = b.growth;
  const { stories } = VouchStats.briefNumbers(b);
  const points = b.talking_points.length + b.open_questions.length;
  const leftOut = b.ledger.articles.length + b.ledger.draft.length;
  const badge = { stories: stories.verified, meeting: points, leftout: leftOut };
  const sources = [
    ["Tavily", `${plural((c.credits || 0) + ((g && g.credits) || 0), "credit")}`],
    ["Model", m ? m.served_by.split("/").pop() : "Not called"],
    ["Gateway", m ? "Bifrost" : "Not used"],
    ["Market data", g && g.method === "market" ? g.symbol : g && g.method === "news" ? "From news" : "None"],
  ];
  return h("div", { class: "ws" },
    h("aside", { class: "ws-side" },
      h("a", { class: "brand ws-brand", href: "/", "aria-label": "Vouch: start a new brief" },
        h("img", { class: "brand-logo", src: "/static/logo.webp", alt: "", width: "736", height: "1038" }),
        h("span", { class: "ws-brand-name", text: "Vouch" })),
      h("nav", { class: "ws-nav", "aria-label": "Brief sections" }, VIEWS.map(([key, label]) =>
        h("button", { type: "button", class: "ws-tab", "data-view": key },
          h("span", { class: "ws-tab-dot", "aria-hidden": "true" }),
          h("span", { class: "ws-tab-label", text: label }),
          badge[key] != null ? h("span", { class: "ws-tab-badge", text: String(badge[key]) }) : null))),
      h("div", { class: "ws-sources", "aria-label": "Tools behind this brief" },
        h("p", { class: "ws-sources-title", text: "Behind this brief" }),
        sources.map(([k, v]) => h("p", { class: "src" },
          h("span", { class: "src-dot", "aria-hidden": "true" }), h("span", { class: "src-name", text: k }),
          h("span", { class: "src-val", text: v }))))),
    h("div", { class: "ws-main" },
      h("p", { class: "ws-status" },
        h("span", { class: "ws-live", "aria-hidden": "true" }),
        h("span", { text: `${GOAL_LABEL[b.subject.goal] || "General"} meeting, ${fmtDate(b.subject.meeting)}` +
                          (b.subject.meeting_time ? ` at ${b.subject.meeting_time}` : "") }),
        h("span", { text: `News ${fmtDate(b.window.start)} to ${fmtDate(b.window.end)}` }),
        h("span", { text: `${c.found} found, ${c.kept} kept, ${c.verified} verified` })),
      kpiStrip(b),
      h("div", { class: "ws-views" }, views)));
}

function showView(key, { focus = false, remember = true } = {}) {
  const ws = document.querySelector(".ws");
  if (!ws || !VIEWS.some(([k]) => k === key)) return;
  ws.querySelectorAll(".ws-view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === key));
  ws.querySelectorAll(".ws-tab").forEach((t) => {
    if (t.dataset.view === key) t.setAttribute("aria-current", "page");
    else t.removeAttribute("aria-current");
  });
  if (remember) history.replaceState(null, "", `#${key}`);
  if (key === "overview") fitOneLine($("result-title"));
  if (focus) {
    const title = ws.querySelector(`.ws-view[data-view="${key}"] h2, .ws-view[data-view="${key}"] h3`);
    if (title) { title.setAttribute("tabindex", "-1"); title.focus({ preventScroll: true }); }
  }
}

function selectStory(n) {
  const ws = document.querySelector(".ws");
  if (!ws) return;
  ws.querySelectorAll(".story-pick").forEach((p) => p.setAttribute("aria-pressed", String(p.dataset.story === String(n))));
  ws.querySelectorAll(".story-detail .row").forEach((row) => row.classList.toggle("is-active", row.id === `story-${n}`));
  const detail = ws.querySelector(".story-detail");
  if (detail) detail.scrollTop = 0;
}

// Follow a "#story-3" link or a "#stories" address into the workspace.
function openFromHash(hash) {
  const story = /^#story-(\d+)$/.exec(hash || "");
  if (story) { showView("stories", { remember: false }); selectStory(Number(story[1])); history.replaceState(null, "", hash); return true; }
  const view = (hash || "").slice(1);
  if (VIEWS.some(([k]) => k === view)) { showView(view, { remember: false }); return true; }
  return false;
}

// A section address typed or pasted while the brief is open (#meeting, #story-2) opens it too.
window.addEventListener("hashchange", () => { if (document.querySelector(".ws")) openFromHash(location.hash); });

function wireWorkspace() {
  const ws = document.querySelector(".ws");
  ws.querySelectorAll(".ws-tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view, { focus: true })));
  ws.querySelectorAll(".story-pick").forEach((p) => p.addEventListener("click", () => selectStory(p.dataset.story)));
  ws.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#story-"]');
    if (a) { e.preventDefault(); openFromHash(a.getAttribute("href")); }
  });
  // "What we left out": filter by reason.
  ws.querySelectorAll(".ledger-chip").forEach((chip) => chip.addEventListener("click", () => {
    const want = chip.dataset.reason;
    ws.querySelectorAll(".ledger-chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    ws.querySelectorAll(".ledger-group").forEach((group) => {
      let shown = 0;
      group.querySelectorAll(".row").forEach((row) => {
        const on = !want || row.dataset.reason === want;
        row.hidden = !on;
        shown += on ? 1 : 0;
      });
      group.hidden = shown === 0;
    });
  }));
  selectStory(1);
  if (!openFromHash(location.hash)) showView("overview", { remember: false });
}

function renderBrief(b) {
  if (b.choices && b.choices.length) return renderChoices(b);
  const r = $("result");
  r.replaceChildren();
  const c = b.counts;
  const meetingLine = `${GOAL_LABEL[b.subject.goal] || "General"} meeting on ${fmtDate(b.subject.meeting)}` +
                      (b.subject.meeting_time ? ` at ${b.subject.meeting_time}` : "") + ". " +
                      `News from ${fmtDate(b.window.start)} to ${fmtDate(b.window.end)}.`;

  const overview = h("section", { class: "ws-view view-overview", "data-view": "overview", "aria-labelledby": "result-title" },
    h("header", { class: "brief-head hero" },
      h("div", { class: "hero-main" },
        h("h2", { id: "result-title", text: b.subject.name }),
        b.subject.identified_as ? h("p", { class: "identified", text: `Identified as ${b.subject.identified_as}` }) : null,
        (b.warnings || []).map((w) => h("p", { class: "warning", role: "note", text: w })),
        h("p", { class: "meeting-line", text: meetingLine }),
        h("p", { class: "funnel" },
          h("strong", { text: c.found }), " articles found, ",
          h("strong", { text: c.kept }), " kept, ",
          h("strong", { text: c.verified }), ` ${c.verified === 1 ? "story" : "stories"} verified.`),
        c.verified ? h("p", { class: "key", text:
          "How to read this: every quote was found word for word in its article. " +
          "“Single source” means only one outlet reported it, so weigh it with more care; " +
          "“Older event” means the news is recent but the event isn't. " +
          "Claims that failed a check are listed under Left out." }) : null),
      heroGrowth(b)));

  const storiesView = h("section", { class: "ws-view view-stories", "data-view": "stories", "aria-labelledby": "what-title" },
    h("h3", { id: "what-title", class: "view-title", text: "What happened" }),
    b.stories.length
      ? h("div", { class: "stories-split" }, storyList(b), h("div", { class: "story-detail" }, b.stories.map(storyRow)))
      : h("p", { class: "nothing", text: VouchStats.emptyMessage(b) }));

  const meetingView = h("section", { class: "ws-view view-meeting", "data-view": "meeting", "aria-labelledby": "meeting-title" },
    h("h3", { id: "meeting-title", class: "view-title", text: "Your meeting" }),
    b.talking_points.length || b.open_questions.length
      ? h("div", { class: "two-up" },
          b.talking_points.length ? h("section", { class: "part" }, h("h3", { text: "Worth raising" }), pointList(b.talking_points)) : null,
          b.open_questions.length ? h("section", { class: "part" }, h("h3", { text: "Questions to ask" }), pointList(b.open_questions)) : null)
      : h("p", { class: "nothing", text: "No talking points or questions: nothing in the news passed every check." }));

  const left = ledger(b.ledger);
  const leftView = h("section", { class: "ws-view view-leftout", "data-view": "leftout", "aria-labelledby": left ? "ledger-title" : "leftout-title" },
    left || [h("h3", { id: "leftout-title", class: "view-title", text: "What we left out" }),
             h("p", { class: "nothing", text: "Nothing was left out." })]);

  const proofView = h("section", { class: "ws-view view-proof", "data-view": "proof", "aria-labelledby": "proof-title" },
    proofPanel(b),
    // How the brief was made: which model wrote it through Bifrost, and the Tavily search behind it.
    // Kept on screen and in print; it's the record of the tools used.
    h("p", { class: "machine", text:
      (b.model
        ? `Written by ${b.model.served_by}${b.model.fallback ? " (backup model, primary was unavailable)" : ""} via the Bifrost gateway, ` +
          `${(b.model.prompt_tokens + b.model.completion_tokens + b.model.entity_check_tokens + ((b.growth && b.growth.tokens) || 0)).toLocaleString()} tokens, ${b.seconds}s in total. `
        : "No model was called: no article passed the filters. ") +
      `Search by Tavily (${plural((c.credits || 0) + ((b.growth && b.growth.credits) || 0), "credit")}).` +
      (b.growth && b.growth.method === "market" ? ` Market data from Yahoo Finance.` : "") }));

  r.append(workspace(b, [overview, storiesView, meetingView, leftView, proofView]));
  r.hidden = false;
  wireWorkspace();
  fitOneLine($("result-title"));
  document.title = `${b.subject.name}: Vouch brief`;
  window.scrollTo(0, 0);
}

// ---------- submit ----------
let source = null;

$("ask").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("name").value.trim();
  const meeting = $("meeting").value;
  $("form-error").textContent = "";
  if (!name) { $("form-error").textContent = "Enter a company or person to brief on."; $("name").focus(); return; }
  if (!meeting) { $("form-error").textContent = "Pick the meeting date and time."; $("meeting").focus(); return; }

  if (source) source.close();
  showAnalysis(name, $("goal").value, meeting);

  const qs = new URLSearchParams({ name, kind: $("kind").value, goal: $("goal").value, meeting,
                                  about: $("about").value.trim() });
  source = new EventSource(`/api/brief?${qs}`);

  source.addEventListener("step", (ev) => { const d = JSON.parse(ev.data); showStep(d.stage, d); });
  // A finished brief opens as its own page (/brief/<id>), with no search screen to scroll back to.
  // A which-one question has no id: it is still part of asking, so it shows here, on its own.
  source.addEventListener("brief", (ev) => {
    const b = JSON.parse(ev.data);
    stopStream();
    if (b.id) { location.assign(`/brief/${encodeURIComponent(b.id)}`); return; }
    $("analysis").hidden = true;
    renderBrief(b);
  });
  source.addEventListener("failure", (ev) => { stopStream(); showFailure(JSON.parse(ev.data).message); });
  source.onerror = () => { if (source) { stopStream(); showFailure("Lost the connection to the Vouch server. Is it still running?"); } };
});

function stopStream() {
  if (source) source.close();
  source = null;
  clearInterval(clock);
}

// Cancel during a run, or go back after a failure: either way, return to the question.
$("cancel").addEventListener("click", () => {
  stopStream();
  showQuestion();
  $("name").focus();
});

// ---------- the brief page: /brief/<id> loads a saved brief and shows only that ----------
function showMissing(text) {
  const r = $("result");
  r.replaceChildren(h("h2", { id: "result-title", class: "missing-title", text: "Brief not found" }),
                    h("p", { class: "nothing", text }));
  r.hidden = false;
}

async function loadSavedBrief() {
  const id = decodeURIComponent(location.pathname.slice("/brief/".length)).replace(/\/$/, "");
  if (!/^[0-9a-f]{12}$/.test(id)) { showMissing("That link doesn't point to a brief. Make a new one from the start page."); return; }
  try {
    const res = await fetch(`/api/briefs/${id}`);
    if (res.status === 404) { showMissing("No saved brief has that link. It may have been made on another computer. Make a new one from the start page."); return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderBrief(await res.json());
  } catch (e) {
    showMissing("Couldn't load this brief from the Vouch server. Check that it's still running, then reload the page.");
  }
}

if (document.documentElement.classList.contains("route-brief")) loadSavedBrief();

// Back from a brief page can restore this page from the browser's memory, still showing the
// finished analysis. Return it to the question instead.
window.addEventListener("pageshow", (e) => {
  if (e.persisted && !document.documentElement.classList.contains("route-brief")) {
    stopStream();
    showQuestion();
  }
});

// A new name means the old "which one" hint no longer applies.
$("name").addEventListener("input", () => { $("form-error").textContent = ""; $("about").value = ""; });
