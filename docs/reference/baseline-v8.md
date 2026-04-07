# browser-pilot v8 Baseline (anchor numbers)

These are the **target numbers** that caliper's Phase 1 port must reproduce
(within ±1 sample on judge pass at N=2). They come from the final round of
8 weeks of iteration on browser-pilot's `tests/agent/run.py`, after the v8
stale-reference judge fix.

If your caliper port produces these numbers (within tolerance), the
abstractions work. If it doesn't, debug against the saved logs in
`browser-pilot/test-results/`.

> **Important:** these numbers were measured **without** cache tracking
> and **without** $ cost calculation. Phase 1's M1.6 will produce a v9
> baseline that adds those columns. The v8 numbers below are the
> "judge pass and tokens only" reference that v9 must match on the
> overlap columns.

---

## Configuration

| Field | Value |
|---|---|
| Model | `claude-sonnet-4-6` (primary) and `gpt-5.4` (validation) |
| Max turns | 12 |
| Epochs (runs per task) | 2 |
| Total samples (per model) | 12 tasks × 2 runs = 24 |
| Judge | v8 stale-ref tolerant (see `inherited.md`) |
| Judge temperature | 0 |
| Tools available | full bp CLI: open, click, type, press, keyboard, read, snapshot, eval, locate, screenshot, tabs, frame, cookies, upload, auth, net |
| System prompt | `browser-pilot/plugin/skills/browser-pilot/SKILL.md` |
| Date measured | 2026-04-07 |

---

## Top-line Sonnet results

```
Sonnet v8 (12 tasks × 2 runs = 24 samples)
─────────────────────────────────────────
Judge pass:       23/24  (96%)
Total tokens:     ~1,250,000  (across 24 runs)
Avg tokens/run:   ~52,000
$ cost:           NOT MEASURED in v8
Cache hit rate:   NOT MEASURED in v8
Lazy hits:        0
```

## Top-line gpt-5.4 results

```
gpt-5.4 v8 (12 tasks × 2 runs = 24 samples)
─────────────────────────────────────────
Judge pass:       17/24  (71%)
Total tokens:     ~470,000
Avg tokens/run:   ~20,000
$ cost:           NOT MEASURED
Cache hit rate:   NOT MEASURED
Lazy hits:        2  (gpt-5.4 ESPN--0 run 1, gpt-5.4 ArXiv--2 run 2)
```

---

## Per-bucket results

### Sonnet

| Bucket | Pass rate | Mean steps | Mean tokens | Notes |
|---|---|---|---|---|
| lookup | 6/6 (100%) | 7.5 | 45,616 | Stable across runs |
| search | 6/6 (100%) | 6.0 | 44,735 | Stable |
| **compare** | **5/6 (83%)** | 9.3 | 105,841 | Apple--3 run 2 hits 12-step limit with empty answer (the one v8 failure) |
| navigate | 6/6 (100%) | 4.7 | 28,418 | Stable |

### gpt-5.4

| Bucket | Pass rate | Mean steps | Mean tokens | Notes |
|---|---|---|---|---|
| lookup | 4/6 (67%) | 3.8 | 16,675 | Wolfram Alpha--0 run 2 was lazy (1 cmd, 0 obs) |
| search | 3/6 (50%) | 3.3 | 20,469 | Allrecipes--3, Coursera--0, Huggingface--3 each fail one run |
| compare | 6/6 (100%) | 5.3 | 30,986 | After v8 stale-ref fix, all pass |
| navigate | 4/6 (67%) | 2.3 | 11,084 | ArXiv--2 was lazy in run 2 |

**Observation**: gpt-5.4 is faster (3-5 steps vs Sonnet's 4-9) and cheaper
(~20K tokens vs ~52K), but trades that for higher variance and
occasional lazy behavior. Sonnet is the more reliable A/B partner.

---

## Per-task detail (Sonnet only, both runs)

For each task: `(steps, tokens, judge)` for run 1 and run 2. `Y` = judge pass, `N` = judge fail.

| Bucket | Task | Run 1 | Run 2 |
|---|---|---|---|
| lookup | Cambridge Dictionary--3 | 3 / 14K / Y | 3 / 14K / Y |
| lookup | Wolfram Alpha--0 | 9 / 55K / Y | 10 / 64K / Y |
| lookup | Wolfram Alpha--2 | 9 / 51K / Y | 12 / 84K / Y |
| search | Allrecipes--3 | 8 / 56K / Y | 8 / 62K / Y |
| search | Coursera--0 | 5 / 33K / Y | 9 / 86K / Y |
| search | Huggingface--3 | 3 / 16K / Y | 3 / 16K / Y |
| compare | Apple--0 | 11 / 125K / Y | 11 / 129K / Y |
| compare | Apple--3 | 12 / 131K / Y | 12 / 151K / **N** ← only failure |
| compare | Allrecipes--0 | 6 / 40K / Y | 8 / 66K / Y |
| navigate | GitHub--3 | 5 / 36K / Y | 7 / 46K / Y |
| navigate | BBC News--5 | 3 / 14K / Y | 3 / 14K / Y |
| navigate | ArXiv--2 | 5 / 27K / Y | 5 / 35K / Y |

**Observed variance** (Sonnet, max range across 2 runs):
- Token spread up to 43% on the same task (ArXiv--0 type pattern)
- Step spread up to 3 steps on a task
- Judge verdicts disagreed across runs in 2/12 = 17% of Sonnet tasks
  (GitHub--1 in earlier 7-task v6 baseline, Apple--3 here)

This is the **noise floor** caliper has to respect. Improvements smaller
than this are not real.

---

## Caveats

1. **Apple--3 Sonnet failure is the one persistent v8 failure**. It's
   not a stale-reference issue (the agent legitimately runs out of
   steps). Caliper's port should reproduce this — if your port shows
   12/12 on compare, you've probably loosened max_turns or fixed
   something inadvertently.

2. **Reference answers from WebVoyager are dated 2023/2024**. Several
   compare tasks (Apple--0, Apple--3) only pass because of the v8
   stale-ref tolerance rule in the judge prompt. Without that rule, the
   judge would mark M5 chip answers as INCORRECT against M2 reference.

3. **WebVoyager site state changes**. Allrecipes, ESPN, Cambridge
   Dictionary occasionally have intermittent failures (Cloudflare,
   reformat, etc). The numbers above were measured on 2026-04-07. If
   you re-run a year later, expect drift on time-sensitive tasks.

4. **gpt-5.4 has 2600% token spread on some tasks**. We saw
   Huggingface--3 run from 3K tokens to 79K tokens across runs in v6
   variance analysis. gpt-5.4 is **not** a reliable A/B partner —
   use Sonnet for iteration decisions, gpt-5.4 only for cross-model
   validation.

---

## What v9 (Phase 1 output) must add

The v9 baseline produced by caliper in M1.6 must include all v8 columns
PLUS the cost/cache columns that v8 lacked:

| New v9 column | Source |
|---|---|
| `$_per_run` | `cost_tracker` scorer × `pricing.py` table |
| `cache_read_tokens` | Inspect AI's `usage.cache_read_input_tokens` |
| `cache_creation_tokens` | Inspect AI's `usage.cache_creation_input_tokens` |
| `cache_hit_rate` | `cache_read / (cache_read + cache_creation + input)` |
| `$_per_pass` | `total_$ / judge_pass_count` |

Validation rule: v9 judge pass must be within ±1 of v8 (i.e., Sonnet
22-24 / 24, gpt-5.4 16-18 / 24). Token totals should be within ±10%.
$ and cache metrics are new and have no v8 reference.

---

## How to load this in your code

When you write Phase 1 tests, import the v8 numbers as constants:

```python
# caliper/tests/baseline_v8_anchors.py
SONNET_V8 = {
    "judge_pass": 23,
    "total": 24,
    "buckets": {
        "lookup":   {"pass": 6, "total": 6},
        "search":   {"pass": 6, "total": 6},
        "compare":  {"pass": 5, "total": 6},
        "navigate": {"pass": 6, "total": 6},
    },
    "tolerance": 1,  # within ±1 sample is "passing"
}
GPT54_V8 = {
    "judge_pass": 17,
    "total": 24,
    # ... per-bucket
}
```

Phase 1 tests assert `abs(caliper_result - v8_anchor) <= tolerance`.
