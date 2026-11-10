# Vouch evaluation

Run on 10 Nov 2026 21:27, meeting date 2026-11-14. Expectations in `subjects.json` were written before running.

## Per subject

| Subject | Expected ambiguous | Asked which one | Found | Kept | Other-entity set aside | AI stories | Verified | Removed by checks | Older-event flags | Seconds | Tokens | Model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Infosys | no | no | 32 | 25 | 0 | 6 | 6 | 0 | 0 | 11.5 | 9534 | groq/openai/gpt-oss-120b |
| Zerodha | no | no | 32 | 19 | 4 | 5 | 4 | 1 | 0 | 58.5 | 8502 | groq/openai/gpt-oss-120b |
| Razorpay | no | no | 31 | 19 | 0 | 6 | 6 | 0 | 0 | 57.1 | 7973 | groq/openai/gpt-oss-120b |
| Swiggy | no | no | 31 | 23 | 0 | 4 | 3 | 1 | 0 | 62.9 | 7045 | gemini/gemini-3.5-flash-lite (fallback) |
| Nandan Nilekani | no | no | 22 | 17 | 0 | 5 | 4 | 1 | 1 | 33.3 | 6856 | groq/openai/gpt-oss-120b |
| Mercury | yes | yes | 26 | 16 | 0 | 0 | 0 | 0 | 0 | 2.6 | 1659 | - (fallback) |
| Apollo | yes | no | 32 | 26 | 5 | 6 | 5 | 1 | 0 | 18.0 | 7717 | gemini/gemini-3.5-flash-lite (fallback) |

## Summary

- Ambiguity handled as expected: **6 of 7** subjects.
- AI-drafted stories removed by the code checks: **4 of 32** (12%).
- Errors: 0.

## Tamper test

Every story that passed was corrupted one way at a time and re-checked.

| Corruption | Caught |
|---|---|
| quote figure changed | 11 of 11 |
| quote paraphrased | 28 of 28 |
| quote cites wrong article | 28 of 28 |
| invented figure in summary | 28 of 28 |
| invented quote | 28 of 28 |

Limits: a small set of well-covered subjects, one run each, judged by code rules. The checks prove quotes exist and figures appear in sources; they do not prove a summary's meaning is right.
