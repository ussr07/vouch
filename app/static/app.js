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
};

// The five stages in the order the server runs them, and who does each one.
const STAGE_ORDER = [
  ["search", "Search", "Tavily"],
  ["filter", "Filter", "Code"],
  ["entity", "Same subject", "Model sorts, code decides"],
  ["draft",  "Draft", "Model, via Bifrost"],
  ["verify", "Verify", "Code"],
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

// ---------- the numbers: drawn from this brief's own counts and stories ----------
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

// One whole split into its parts: a thin bar, with the figures in the legend under it.
// The bar is aria-hidden; the legend carries every number in words.
function splitBar(parts) {
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  if (!total) return [];   // nothing to split: the figure above says so
  let x = 0;
  const bar = total ? svg("svg", { class: "split", width: "100%", height: "10", "aria-hidden": "true" },
    parts.filter((p) => p.value > 0).map((p) => {
      const w = (p.value / total) * 100;
      const rect = svg("rect", { class: `seg seg-${p.kind}`, x: `${x}%`, y: 0, width: `${w}%`, height: 10, rx: 2 });
      x += w;
      return rect;
    })) : null;
  return [bar, h("ul", { class: "legend" }, parts.map((p) =>
    h("li", { class: `legend-item legend-${p.kind}` }, h("span", { class: "swatch", "aria-hidden": "true" }),
      h("strong", { text: String(p.value) }), ` ${p.name}`)))];
}

// When each story was reported, across the brief's own news window. One numbered mark per
// story, linking to it; filled for several outlets, hollow for a single source.
function timeline(b) {
  const day = (iso) => Date.parse(`${iso}T00:00:00Z`) / 86400000;
  const start = day(b.window.start), span = Math.max(1, day(b.window.end) - start);
  const pts = b.stories.map((st, i) => ({ n: i + 1, st, x: Math.min(1, Math.max(0, (day(st.date) - start) / span)) }));
  // Stories reported close together stack upward instead of overlapping.
  const lastX = [];
  for (const p of [...pts].sort((a, c) => a.x - c.x)) {
    let level = 0;
    while (lastX[level] !== undefined && p.x - lastX[level] < TIMELINE.minGap) level++;
    lastX[level] = p.x;
    p.level = level;
  }
  const { r, row, top } = TIMELINE;
  const base = top + r + (lastX.length - 1) * row;
  const axisY = base + r + TIMELINE.stemGap;

  return h("div", { class: "stat stat-wide" },
    h("h4", { class: "stat-title", id: "when-title", text: "When it was reported" }),
    h("div", { class: "timeline-wrap" },
      svg("svg", { class: "timeline", width: "100%", height: axisY + TIMELINE.tickBand, role: "group",
                   "aria-labelledby": "when-title" },
        svg("line", { class: "axis", x1: "0%", x2: "100%", y1: axisY, y2: axisY }),
        svg("text", { class: "tick", x: "0%", y: axisY + TIMELINE.tickOffset, "text-anchor": "start", text: fmtDate(b.window.start) }),
        svg("text", { class: "tick", x: "100%", y: axisY + TIMELINE.tickOffset, "text-anchor": "end", text: fmtDate(b.window.end) }),
        pts.map((p) => {
          const cx = `${p.x * 100}%`, cy = base - p.level * row;
          const multi = p.st.outlets.length > 1;
          const said = `Story ${p.n}, reported ${fmtDate(p.st.date)}, ` +
                       (multi ? `${p.st.outlets.length} outlets` : "single source") +
                       (p.st.older_event ? `, older event: ${p.st.older_event}` : "");
          return svg("a", { class: `pt ${multi ? "pt-multi" : "pt-single"}`, href: `#story-${p.n}`, "aria-label": said,
                            style: `--i:${p.n - 1}` },
            svg("title", { text: `${said}. ${p.st.headline}` }),
            svg("line", { class: "stem", x1: cx, x2: cx, y1: cy + r, y2: axisY }),
            svg("circle", { cx, cy, r }),
            svg("text", { x: cx, y: cy, dy: "0.35em", "text-anchor": "middle", text: String(p.n) }));
        }))),
    h("ul", { class: "legend" },
      h("li", { class: "legend-item legend-a" }, h("span", { class: "swatch dot", "aria-hidden": "true" }), "Several outlets"),
      h("li", { class: "legend-item legend-b" }, h("span", { class: "swatch ring", "aria-hidden": "true" }), "Single source")));
}
const TIMELINE = { r: 10, row: 24, top: 6, stemGap: 10, tickBand: 26, tickOffset: 19, minGap: 0.07 };

// The numbers panel visualises the counts line in the header; it doesn't restate them as
// headline figures. Each chart counts one unit only: articles with articles, stories with stories.
function statsPanel(b) {
  const { articles: a, stories: s } = VouchStats.briefNumbers(b);
  return h("section", { class: "stats", "aria-labelledby": "stats-title" },
    h("h3", { id: "stats-title", class: "sr-only", text: "This brief in numbers" }),
    h("div", { class: "stat" },
      h("h4", { class: "stat-title", text: "Articles" }),
      a.found
        ? splitBar([{ name: "kept", value: a.kept, kind: "a" }, { name: "filtered out", value: a.filteredOut, kind: "b" }])
        : h("p", { class: "stat-empty", text: "No articles found in this news window." })),
    h("div", { class: "stat" },
      h("h4", { class: "stat-title", text: "Stories" }),
      s.drafted
        ? [splitBar([{ name: "verified", value: s.verified, kind: "a" }, { name: "removed by checks", value: s.removed, kind: "b" }]),
           s.verified ? [h("h5", { class: "stat-sub", text: "Verified stories, by source" }),
                         splitBar([{ name: "several outlets", value: s.multi, kind: "a" },
                                   { name: "single source", value: s.single, kind: "b" }])] : null,
           s.older ? h("p", { class: "stat-note flag older",
                              text: `${s.older} ${s.older === 1 ? "is an older event" : "are older events"}` }) : null]
        : h("p", { class: "stat-empty", text: a.kept ? "The AI drafted no stories from the kept articles."
                                                     : "No stories: no article passed the filters." })),
    s.verified ? timeline(b) : null);
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
  const rows = (items, title) => items.length ? [
    h("h4", { text: title }),
    group(items).map((r) => h("div", { class: "row" },
      h("p", { class: "struck" },
        r.url ? h("a", { href: r.url, target: "_blank", rel: "noopener", text: r.title }) : (r.title || r.item),
        r.count > 1 ? h("span", { class: "times", text: ` ×${r.count}` }) : null),
      h("span", { class: "reason", text: r.reason }))),
  ] : [];
  return h("section", { class: "part ledger", "aria-labelledby": "ledger-title" },
    h("h3", { id: "ledger-title", text: `What we left out (${total})` }),
    h("p", { class: "ledger-intro", text: "Nothing is dropped silently. Each item below was removed by a rule in code, not by the AI." }),
    rows(l.articles, "Articles that didn't qualify"),
    rows(l.draft, "Lines the AI wrote that failed our checks"));
}

function renderChoices(b) {
  const r = $("result");
  $("print-slot").replaceChildren();   // a question, not a brief: nothing to print
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

function renderBrief(b) {
  if (b.choices && b.choices.length) return renderChoices(b);
  const r = $("result");
  r.replaceChildren();
  const c = b.counts;

  r.append(h("header", { class: "brief-head" },
    h("h2", { id: "result-title", text: b.subject.name }),
    b.subject.identified_as ? h("p", { class: "identified", text: `Identified as ${b.subject.identified_as}` }) : null,
    (b.warnings || []).map((w) => h("p", { class: "warning", role: "note", text: w })),
    h("p", { text: `${GOAL_LABEL[b.subject.goal] || "General"} meeting on ${fmtDate(b.subject.meeting)}` +
                   (b.subject.meeting_time ? ` at ${b.subject.meeting_time}` : "") + ". " +
                   `News from ${fmtDate(b.window.start)} to ${fmtDate(b.window.end)}.` }),
    h("p", { class: "funnel" },
      h("strong", { text: c.found }), " articles found, ",
      h("strong", { text: c.kept }), " kept, ",
      h("strong", { text: c.verified }), ` ${c.verified === 1 ? "story" : "stories"} verified.`),
    c.verified ? h("p", { class: "key", text:
      "How to read this: every quote below was found word for word in its article. " +
      "\u201cSingle source\u201d means only one outlet reported it, so weigh it with more care; " +
      "\u201cOlder event\u201d means the news is recent but the event isn't. " +
      "Claims that failed a check are listed under What we left out." }) : null));

  r.append(statsPanel(b));

  if (!b.stories.length) {
    r.append(h("section", { class: "part" },
      h("p", { class: "nothing", text: VouchStats.emptyMessage(b) })));
  } else {
    r.append(h("section", { class: "part", "aria-labelledby": "what-title" },
      h("h3", { id: "what-title", text: "What happened" }),
      b.stories.map(storyRow)));
    r.append(h("div", { class: "two-up" },
      b.talking_points.length ? h("section", { class: "part" }, h("h3", { text: "Worth raising" }), pointList(b.talking_points)) : null,
      b.open_questions.length ? h("section", { class: "part" }, h("h3", { text: "Questions to ask" }), pointList(b.open_questions)) : null));
  }

  const left = ledger(b.ledger);
  if (left) r.append(left);   // append(null) would print the word "null"

  // How the brief was made: which model wrote it through Bifrost, and the Tavily search behind it.
  // Kept on screen and in print; it's the record of the tools used.
  r.append(h("p", { class: "machine", text:
    (b.model
      ? `Written by ${b.model.served_by}${b.model.fallback ? " (backup model, primary was unavailable)" : ""} via the Bifrost gateway, ` +
        `${(b.model.prompt_tokens + b.model.completion_tokens + b.model.entity_check_tokens).toLocaleString()} tokens, ${b.seconds}s in total. `
      : "No model was called: no article passed the filters. ") +
    `Search by Tavily (${plural(c.credits || 0, "credit")}).` }));

  // Print sits in the page bar, beside New brief.
  const printBtn = h("button", { type: "button", class: "btn-quiet print-btn", text: "Print or save as PDF" });
  printBtn.addEventListener("click", () => window.print());
  $("print-slot").replaceChildren(printBtn);
  r.hidden = false;
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
