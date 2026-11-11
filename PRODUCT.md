# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary audience: hackathon judges (Geek Room Global AI Hackathon 2026, Tavily Research Agent track) watching Vouch run live in a demo. The product's stated job is meeting prep: a person about to meet a company or person (investor, sales, partnership, business development, hiring, general) wants a one-page brief they can trust.

## Product Purpose
Give Vouch a company or person and a meeting date. It reads the news from the 30 days before the meeting, writes a one-page brief (what happened, what to raise, what to ask) and checks the brief in code. A story only stays if its quote is found word for word in a real article. Success: a judge sees, live, that every line on the brief is proven and that everything rejected is shown with its reason.

## Positioning
AI writes the draft, plain code checks the facts, and the reader sees everything that got rejected. Checking is a string match in Python, not another model's opinion. When a name is ambiguous, Vouch asks which one instead of guessing.

## Operating Context
A live demo on a laptop: the presenter types a name, the pipeline runs for roughly 10 to 40 seconds, then the brief appears and can be printed as one page. The pipeline streams real stages from the server (Server-Sent Events): search (Tavily), filter (code), same-subject check (model sorts, code decides), draft (model via Bifrost), verify (code).

## Capabilities and Constraints
- Plain HTML/CSS/JS served by FastAPI from `app/static`; no framework, no build step, no animation library.
- Web text goes on the page only via `textContent`, never `innerHTML`.
- Fonts may load from Google Fonts; no other new dependencies without asking.
- The brief, the rejection ledger and the print layout are a separate future design task (the results page).
- Saved briefs have an API (`/api/briefs`, `/api/briefs/{id}`) but no UI yet.

## Brand Commitments
- Name: Vouch. Tagline: "Meeting briefs where every line is proven."
- Approved entry direction "Proof Lock": dark monochrome instrument with restrained CRT atmosphere, Spectral wordmark that locks from raw mono letters, warm-white phosphor as the one accent.
- Voice: plain, specific, sentence case; errors say what went wrong and how to fix it.

## Evidence on Hand
- Measured results in README: 424 of 424 corrupted stories caught across 4 runs; 9 of 104 AI-written stories removed.
- Real per-run numbers streamed by the server (articles found, kept, rejected, verified, removed, model used, seconds).
- No testimonials, customers or press exist; none may be invented.

## Product Principles
1. Show the proof, not a claim of proof: real counts from the real run.
2. Nothing is dropped silently.
3. Ask instead of guessing.
4. The model writes; code decides.
