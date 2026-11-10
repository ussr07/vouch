# Vouch evaluation

Run on 10 Nov 2026 21:29, meeting date 2026-11-14. Expectations in `subjects.json` were written before running.

## Per subject

| Subject | Expected ambiguous | Asked which one | Found | Kept | Other-entity set aside | AI stories | Verified | Removed by checks | Older-event flags | Seconds | Tokens | Model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Infosys | no | no | 32 | 25 | 0 | 3 | 3 | 0 | 0 | 14.2 | 7158 | gemini/gemini-3.5-flash-lite (fallback) |
| Zerodha | no | no | 32 | 19 | 4 | 6 | 5 | 1 | 0 | 4.4 | 6758 | groq/openai/gpt-oss-120b |
| Razorpay | no | no | 31 | 19 | 0 | 2 | 2 | 0 | 0 | 13.1 | 6632 | gemini/gemini-3.5-flash-lite (fallback) |
| Swiggy | no | no | 31 | 23 | 0 | 3 | 3 | 0 | 0 | 3.6 | 6742 | gemini/gemini-3.5-flash-lite (fallback) |
| Nandan Nilekani | no | no | 22 | 17 | 0 | 2 | 2 | 0 | 0 | 5.4 | 4600 | gemini/gemini-3.5-flash-lite (fallback) |
| Mercury | yes | yes | 26 | 16 | 0 | 0 | 0 | 0 | 0 | 3.3 | 2270 | - (fallback) |
| Apollo | yes | no | 32 | 26 | 9 | 4 | 4 | 0 | 0 | 12.7 | 6832 | gemini/gemini-3.5-flash-lite (fallback) |

## Summary

- Ambiguity handled as expected: **6 of 7** subjects.
- AI-drafted stories removed by the code checks: **1 of 20** (5%).
- Errors: 0.

## Tamper test

Every story that passed was corrupted one way at a time and re-checked.

| Corruption | Caught |
|---|---|
| quote figure changed | 8 of 8 |
| quote paraphrased | 19 of 19 |
| quote cites wrong article | 19 of 19 |
| invented figure in summary | 19 of 19 |
| invented quote | 19 of 19 |

Limits: a small set of well-covered subjects, one run each, judged by code rules. The checks prove quotes exist and figures appear in sources; they do not prove a summary's meaning is right.
