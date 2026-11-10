# Vouch evaluation

Run on 10 Nov 2026 21:37, meeting date 2026-11-14. Expectations in `subjects.json` were written before running.

## Per subject

| Subject | Expected ambiguous | Asked which one | Found | Kept | Other-entity set aside | AI stories | Verified | Removed by checks | Older-event flags | Seconds | Tokens | Model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Infosys | no | no | 32 | 25 | 0 | 6 | 6 | 0 | 0 | 6.1 | 7650 | groq/openai/gpt-oss-120b |
| Zerodha | no | no | 32 | 19 | 0 | 6 | 6 | 0 | 0 | 9.7 | 9587 | groq/qwen/qwen3.8-27b (fallback) |
| Razorpay | no | no | 31 | 19 | 0 | 2 | 2 | 0 | 0 | 5.8 | 6643 | gemini/gemini-3.5-flash-lite (fallback) |
| Swiggy | no | no | 31 | 23 | 0 | 5 | 4 | 1 | 0 | 11.4 | 7433 | groq/openai/gpt-oss-120b |
| Nandan Nilekani | no | no | 22 | 17 | 0 | 2 | 2 | 0 | 0 | 3.4 | 4713 | gemini/gemini-3.5-flash-lite (fallback) |
| Mercury | yes | yes | 26 | 16 | 0 | 0 | 0 | 0 | 0 | 2.0 | 1687 | - (fallback) |
| Apollo | yes | no | 32 | 26 | 5 | 6 | 6 | 0 | 1 | 38.2 | 7931 | groq/openai/gpt-oss-120b (fallback) |

## Summary

- Ambiguity handled as expected: **6 of 7** subjects.
- AI-drafted stories removed by the code checks: **1 of 27** (4%).
- Errors: 0.

## Tamper test

Every story that passed was corrupted one way at a time and re-checked.

| Corruption | Caught |
|---|---|
| quote figure changed | 12 of 12 |
| quote paraphrased | 26 of 26 |
| quote cites wrong article | 26 of 26 |
| invented figure in summary | 26 of 26 |
| invented quote | 26 of 26 |

Limits: a small set of well-covered subjects, one run each, judged by code rules. The checks prove quotes exist and figures appear in sources; they do not prove a summary's meaning is right.
