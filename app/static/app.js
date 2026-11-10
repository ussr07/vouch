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

// Default the meeting to tomorrow at 10:00, in the user's own time zone.
const tomorrow = new Date(Date.now() + 86400000);
const pad = (n) => String(n).padStart(2, "0");
$("meeting").value = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T10:00`;

// ---------- live progress ----------
const STAGES = {
  search: { running: "Searching the last 30 days of news",
            done: (d) => `Found ${plural(d.found, "article")}` +
                         (d.credits ? ` (${plural(d.credits, "search credit")} used)` : " (from cache, no credits used)") },
  filter: { done: (d) => `Kept ${d.kept}, threw out ${d.rejected}` },
  entity: { running: "Checking every article is about the same one",
            done: (d) => d.needs_choice ? `Found ${d.groups} different subjects with this name`
                       : d.set_aside ? `Kept ${d.kept} about ${d.label || "this subject"}, set aside ${d.set_aside} about others`
                       : `All ${d.kept} articles are about the same subject` },
  draft:  { running: (d) => `Writing the draft with ${d.model}`,
            done: (d) => `Draft written by ${d.served_by} in ${d.seconds}s` +
                         (d.fallback ? " (backup model took over)" : "") },
  verify: { done: (d) => `Checked every quote: ${d.verified} verified, ${d.removed} removed` },
};

function showStep(stage, data) {
  const list = $("progress");
  let li = list.querySelector(`[data-stage="${stage}"]`);
  if (!li) {
    li = h("li", { "data-stage": stage }, h("span", { class: "mark", "aria-hidden": "true" }), h("span"));
    list.append(li);
  }
  const spec = STAGES[stage][data.status];
  li.className = data.status;
  li.querySelector(".mark").textContent = data.status === "done" ? "✓" : "";
  li.lastChild.textContent = typeof spec === "function" ? spec(data) : spec;
}

function showFailure(message) {
  const list = $("progress");
  list.hidden = false;
  list.querySelectorAll("li.running").forEach((li) => li.remove());
  list.append(h("li", { class: "failed" }, h("span", { class: "mark", "aria-hidden": "true", text: "×" }),
                h("span", { text: message })));
}

// ---------- the brief ----------
function storyRow(s, i) {
  const quote = h("blockquote", { class: "quote" },
    h("mark", { text: `“${s.quote}”` }),
    h("cite", {}, "Found word for word in ", h("a", { href: s.quote_url, target: "_blank", rel: "noopener", text: s.quote_site })));

  const sources = h("details", { class: "sources" },
    h("summary", { text: `${plural(s.sources.length, "article")} behind this` }),
    h("ul", {}, s.sources.map((src) =>
      h("li", {}, h("a", { href: src.url, target: "_blank", rel: "noopener", text: src.title }),
        ` (${src.site}, ${fmtDate(src.date)})`))));

  return h("article", { class: "row", id: `story-${i + 1}` },
    h("div", { class: "story" },
      h("h4", {}, h("span", { class: "num", text: `${i + 1}.` }), s.headline),
      h("p", { class: "summary", text: s.summary }),
      quote, sources),
    h("div", { class: "margin" },
      h("span", { text: `Reported ${fmtDate(s.date)}` }),
      s.older_event ? h("span", { class: "older", text: `Older event: ${s.older_event}` }) : null,
      h("span", { text: plural(s.outlets.length, "outlet") }),
      h("span", { class: "check", text: "✓ Quote verified" })));
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
        r.url ? h("a", { href: r.url, target: "_blank", rel: "noopener", text: r.title }) : r.item,
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
  $("empty").hidden = true;
}

function renderBrief(b) {
  if (b.choices && b.choices.length) return renderChoices(b);
  const r = $("result");
  r.replaceChildren();
  const c = b.counts;

  r.append(h("header", { class: "brief-head" },
    h("h2", { id: "result-title", text: b.subject.name }),
    b.subject.identified_as ? h("p", { class: "identified", text: `Identified as ${b.subject.identified_as}` }) : null,
    h("p", { text: `${b.subject.goal[0].toUpperCase() + b.subject.goal.slice(1)} meeting on ${fmtDate(b.subject.meeting)}` +
                   (b.subject.meeting_time ? ` at ${b.subject.meeting_time}` : "") + ". " +
                   `News from ${fmtDate(b.window.start)} to ${fmtDate(b.window.end)}.` }),
    h("p", { class: "funnel" },
      h("strong", { text: c.found }), " articles found, ",
      h("strong", { text: c.kept }), " kept, ",
      h("strong", { text: c.verified }), ` ${c.verified === 1 ? "story" : "stories"} verified.`)));

  if (!b.stories.length) {
    r.append(h("section", { class: "part" },
      h("p", { class: "nothing", text: c.kept
        ? "No story survived the checks, so there's nothing we can vouch for. The ledger below shows why."
        : "No recent news about this subject passed the filters. Check the spelling, or try the full name." })));
  } else {
    r.append(h("section", { class: "part", "aria-labelledby": "what-title" },
      h("h3", { id: "what-title", text: "What happened" }),
      b.stories.map(storyRow)));
    r.append(h("div", { class: "two-up" },
      b.talking_points.length ? h("section", { class: "part" }, h("h3", { text: "Worth raising" }), pointList(b.talking_points)) : null,
      b.open_questions.length ? h("section", { class: "part" }, h("h3", { text: "Questions to ask" }), pointList(b.open_questions)) : null));
  }

  r.append(ledger(b.ledger));
  const printBtn = h("button", { type: "button", class: "print-btn", text: "Print or save as PDF" });
  printBtn.addEventListener("click", () => window.print());
  r.querySelector(".brief-head").append(printBtn);

  if (b.model) {
    r.append(h("p", { class: "machine", text:
      `Written by ${b.model.served_by}${b.model.fallback ? " (backup model, primary was unavailable)" : ""} via the Bifrost gateway, ` +
      `${(b.model.prompt_tokens + b.model.completion_tokens + b.model.entity_check_tokens).toLocaleString()} tokens, ${b.seconds}s in total. ` +
      `Search by Tavily (${plural(c.credits, "credit")}).` }));
  }
  r.hidden = false;
  $("empty").hidden = true;
  r.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
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
  $("progress").replaceChildren();
  $("progress").hidden = false;
  $("result").hidden = true;
  $("go").disabled = true;
  $("go").textContent = "Making brief";

  const qs = new URLSearchParams({ name, kind: $("kind").value, goal: $("goal").value, meeting,
                                  about: $("about").value.trim() });
  source = new EventSource(`/api/brief?${qs}`);
  const finish = () => { source.close(); source = null; $("go").disabled = false; $("go").textContent = "Make brief"; };

  source.addEventListener("step", (ev) => { const d = JSON.parse(ev.data); showStep(d.stage, d); });
  source.addEventListener("brief", (ev) => { finish(); renderBrief(JSON.parse(ev.data)); });
  source.addEventListener("failure", (ev) => { finish(); showFailure(JSON.parse(ev.data).message); });
  source.onerror = () => { if (source) { finish(); showFailure("Lost the connection to the Vouch server. Is it still running?"); } };
});

// A new name means the old "which one" hint no longer applies.
$("name").addEventListener("input", () => { $("form-error").textContent = ""; $("about").value = ""; });
