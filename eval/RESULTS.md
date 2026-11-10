# Vouch evaluation

Run on 10 Nov 2026 22:35, meeting date 2026-11-14. Expectations in `subjects.json` were written before running.

## Per subject

| Subject | Expected ambiguous | Asked which one | Found | Kept | Other-entity set aside | AI stories | Verified | Removed by checks | Older-event flags | Seconds | Tokens | Model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Infosys | no | no | 32 | 24 | 0 | 5 | 5 | 0 | 1 | 9.2 | 7476 | groq/openai/gpt-oss-120b |
| Zerodha | no | no | 32 | 19 | 0 | 5 | 5 | 0 | 0 | 31.3 | 7432 | groq/openai/gpt-oss-120b |
| Razorpay | no | no | 30 | 17 | 0 | 2 | 1 | 1 | 0 | 4.9 | 5868 | gemini/gemini-3.5-flash-lite (fallback) |
| Swiggy | no | no | 18 | 10 | 0 | 2 | 2 | 0 | 0 | 7.3 | 4223 | gemini/gemini-3.5-flash-lite (fallback) |
| Nandan Nilekani | no | no | 18 | 13 | 0 | 5 | 4 | 1 | 1 | 6.2 | 4790 | groq/openai/gpt-oss-120b |
| Mercury | yes | yes | 32 | 18 | 0 | 0 | 0 | 0 | 0 | 3.5 | 2226 | - |
| Apollo | yes | no | 32 | 26 | 7 | 6 | 5 | 1 | 0 | 14.8 | 9827 | groq/qwen/qwen3.8-27b (fallback) |

## Summary

- Ambiguity handled as expected: **6 of 7** subjects.
- AI-drafted stories removed by the code checks: **3 of 25** (12%).
- Errors: 0.

## Tamper test

Every story that passed was corrupted one way at a time and re-checked.

| Corruption | Caught |
|---|---|
| quote figure changed | 13 of 13 |
| quote paraphrased | 22 of 22 |
| quote cites wrong article | 22 of 22 |
| invented figure in summary | 22 of 22 |
| invented quote | 22 of 22 |

Limits: a small set of well-covered subjects, one run each, judged by code rules. The checks prove quotes exist and figures appear in sources; they do not prove a summary's meaning is right.
