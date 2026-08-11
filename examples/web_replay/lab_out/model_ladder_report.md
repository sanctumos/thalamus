# Venice refine model ladder (mini lab)

Fragments: **14** from `raw_data_log.json` (ASR cleanup, stenographer prompt).
Gold / baseline: `llama-3.3-70b`.

## Summary

| Model | Pass% | Mean Q | Hard fails | Soft fails | Mean latency | $/1M in | $/1M out | Lab $ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llama-3.3-70b` | 100.0 | 0.969 | 0 | 0 | 1931 | 0.7 | 2.8 | 0.002512 |
| `mistral-small-3-2-24b-instruct` | 100.0 | 0.987 | 0 | 0 | 1242 | 0.09375 | 0.25 | 0.000292 |
| `deepseek-v4-flash` | 85.7 | 0.843 | 2 | 0 | 4537 | 0.138 | 0.275 | 0.000988 |
| `qwen3-5-9b` | 0.0 | 0.0 | 14 | 0 | 2639 | 0.1 | 0.15 | 0.000264 |
| `zai-org-glm-4.7-flash` | 7.1 | 0.071 | 13 | 0 | 4936 | 0.06 | 0.4 | 0.001817 |
| `llama-3.2-3b` | 100.0 | 0.97 | 0 | 0 | 8040 | 0.15 | 0.6 | 0.000534 |

**Cheapest viable:** `mistral-small-3-2-24b-instruct` (pass 100.0%, mean Q 0.987).

**Also viable (weaker, slower):** `llama-3.2-3b` (pass 100%, mean Q 0.97) — works, but ~6.5× slower than Mistral Small and ~1.8× higher blended $/1M than Mistral.

**Reliability cliff:** `deepseek-v4-flash` starts intermittent empty outputs (2/14 hard fails). Below that, `qwen3-5-9b` hit 429s/empties and `zai-org-glm-4.7-flash` returned empty content on nearly all turns (likely reasoning-model chrome) — not usable for this refine loop as wired.

**Recommendation for web replay default:** `mistral-small-3-2-24b-instruct` — matches gold quality on this sample at ~$0.09/$0.25 per 1M vs 70B’s $0.70/$2.80.

Raw JSON: `/root/projects/thalamus/examples/web_replay/lab_out/model_ladder_report.json`
