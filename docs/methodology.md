# Methodology

These are the 5 principles that come from 8 weeks of iterating on browser-pilot
(see [lessons-learned.md](lessons-learned.md) for the war stories). Each
principle is paired with the failure mode that taught it to us.

Caliper's job is to make these principles **the path of least resistance**.

---

## 1. Measurement comes before optimization

> If you don't trust your measurement, all your "improvements" are noise.

### The lesson

In browser-pilot v0 through v4 we celebrated "7/7 LLM judge pass" across
multiple iterations. In v5 we discovered that our judge prompt asked for
"CORRECT or INCORRECT" and our parser checked `"CORRECT" in response`, which
returns `True` for `"INCORRECT"` because of the substring trap. **38% of
all judge results across the previous 4 versions were silently flipped from
INCORRECT to PASS.**

The "improvement" we'd been celebrating wasn't real. We'd been optimizing
against a metric that lied to us.

### The principle

Before claiming any improvement, the measurement layer itself must be
verified. Caliper enforces this by:

- **Structured JSON judge output** (`{"verdict": "correct"}` not free text)
- **INCORRECT-first keyword fallback** for legacy parsers
- **Self-evaluation tests** that prove the judge gives correct verdicts on
  hand-labeled (answer, expected_verdict) pairs (see [self-evaluation.md](self-evaluation.md))
- **Anti-substring-bug regression tests** in `tests/unit/`

### How caliper bakes this in

The default JSON judge scorer ships with the parser already correct. Custom
scorers that bypass the default must add their own self-evaluation pairs or
they don't get the "trusted" tag in reports.

---

## 2. N≥2 is the floor, not a luxury

> Single-run results are noise. Period.

### The lesson

In v6 we ran the same 7 tasks twice with both Sonnet and GPT-5.4. The judge
verdicts disagreed across runs in **5 out of 14 (model, task) pairs** — 36%
inconsistency. With Sonnet we saw token spreads up to 43% on the same task.
With GPT-5.4 we saw token spreads up to **125%** (3K → 14K on the same
prompt).

Single-run results are noise. Any "improvement" smaller than the noise floor
is fiction.

### The principle

- The minimum supported N is 2.
- The recommended N is 3 (for high-variance models like reasoning models).
- A user who runs N=1 sees a warning that this result cannot be used for A/B
  decisions.
- Aggregate metrics report mean ± range, not just mean.
- Per-task variance is reported alongside per-bucket aggregates.

### How caliper bakes this in

The Inspect AI eval invocation defaults to `epochs=2`. Caliper's report layer
computes a CV (coefficient of variation) and refuses to print "improvement"
deltas that are within 2σ of the noise floor.

---

## 3. One change at a time, or you can't attribute anything

> If you change two things and the result improves, you don't know which one helped.

### The lesson

In v3 we changed both the snapshot text format **and** the default
`bp read --limit` value in the same commit. The result was a token reduction
that we attributed to "compact snapshot format". When we later tried to
explain why some tasks regressed, we couldn't tell if it was the format
change or the limit change. We had to run a separate A/B to disentangle them,
losing a day.

### The principle

- One change per benchmark run.
- The change must be a single named, version-tagged config (e.g., `v8` vs
  `v9_tighter_limit` vs `v9_compact_format`).
- A "change" can be a tool addition, a prompt edit, a config tweak, a model
  swap — but only one of those at a time.

### How caliper bakes this in

The roadmap (`docs/roadmap.md`) tracks each milestone as a single change.
A/B reports refuse to label a delta as "due to X" if the diff between configs
includes more than one named change.

---

## 4. Failure attribution before fix

> If you can't categorize why each failure happened, you'll fix the wrong thing.

### The lesson

In v6 we built a failure attribution table for the 24 v0-baseline runs. The
breakdown was:

| Tag | Count | % |
|---|---|---|
| OK | 8 | 33% |
| `TOOL_LIMIT` (snapshot blind to content) | 6 | **25%** |
| `LLM_BEHAVIOR` (answer extraction, repetition) | 5 | 21% |
| `TOOL_BUG` (timeout misreport, click failure) | 3 | 12% |
| `REF_STALE` | 1 | 4% |
| `SITE_ISSUE` | 1 | 4% |

This single table told us where to look. The biggest single class was
`TOOL_LIMIT` (snapshot couldn't see search results / article content) — which
directly motivated `bp read` as the v1 fix. **Without the table we would
have probably tried to optimize the snapshot format first**, which is what
the v2/v3 work did and which only addressed ~20% of the actual failures.

### The principle

Every failure must get a tag from a finite vocabulary:

- `TOOL_BUG` — the tool returned the wrong thing
- `TOOL_LIMIT` — the tool can't do what's needed (gap, not bug)
- `SKILL_GAP` — the LLM doesn't know how to use the tool correctly
- `LLM_LIMIT` — the model isn't capable enough
- `LLM_BEHAVIOR` — the model is capable but lazy / inconsistent / fabricating
- `SITE_ISSUE` — external service problem (Cloudflare, rate limit, real outage)
- `REF_STALE` — benchmark reference answer is outdated
- `NOISE` — single failure that doesn't reproduce on retry

### How caliper bakes this in

Failure tags are first-class metadata on every failed sample. The bucket
report aggregates failures by tag. Caliper's default judge scorer surfaces a
"reason" field that maps cleanly to one of the tags above.

---

## 5. Cost > tokens, $/success > $/run

> Token counts are a proxy. Dollars are reality.

### The lesson

We spent v2 and v3 optimizing token counts. Total tokens dropped from 578K
to 308K — a 47% reduction we celebrated.

What we didn't measure: **prompt cache hit rate**. With Anthropic prompt
caching, cached input tokens cost 10% of fresh input tokens. So a config
with cache hits at 80% has roughly the same true cost as a config with
cache hits at 0% but 60% fewer raw tokens.

We never knew our actual $ cost during v0–v8 because we were measuring the
wrong thing. Worse: SKILL.md edits (which we did frequently) **invalidate
the cache prefix**, causing temporary cost spikes that don't show up in
token counts.

### The principle

The optimization target is **dollars per successful task**, not tokens.

- Track `input_tokens`, `cache_creation_tokens`, `cache_read_tokens`,
  `output_tokens`, `reasoning_tokens` separately.
- Apply per-model pricing tables to compute $.
- Report cache hit rate as a first-class metric.
- The headline metric is `cost_usd / judge_pass_count`, not `tokens / run`.
- Flag changes that invalidate the cache prefix as cache regressions, even
  if token counts look flat.

### How caliper bakes this in

The cost wrapper sits at the boundary of every LLM call. Pricing tables ship
with caliper for major models (Anthropic, OpenAI, Google). The default
report includes `$/run`, `$/success`, and `cache_hit_rate` columns.
Reference numbers are pinned to the date of the pricing snapshot so old
reports remain interpretable.

> **Implementation note (M1.2, 2026-04-08)**: caliper currently
> observes **tokens + cache_hit_rate**, not dollars. The principle
> above is the long-term direction; the v0.1 implementation reduces
> cost-per-success to **tokens-per-success** because the iteration
> loop caliper supports is same-model (SKILL.md tweaks, solver
> tuning), where fewer tokens at a fixed model is strictly cheaper.
> Cross-model dollar comparison and a pricing table are deferred
> until a real consumer needs them — see
> [`lessons-learned.md`](lessons-learned.md) "M1.2: re-scoping cost
> wrapper to token observability" for the full reasoning, and
> [`roadmap.md`](roadmap.md) "Out of scope" for the current status.
>
> The principle ($/success > $/run) is preserved as the philosophy.
> The implementation (tokens, cache_hit_rate, uncached_input_tokens)
> is the engineering reality that serves it for v0.1.

---

## How these compose

These 5 principles aren't independent. They form a chain:

```
Trustworthy measurement (P1)
    └─ enables → Variance discipline (P2)
                     └─ enables → Single-variable iteration (P3)
                                      └─ enables → Failure attribution (P4)
                                                       └─ enables → Cost-aware optimization (P5)
```

Skipping any earlier principle breaks the ones that follow. You can't
attribute failures if you don't trust the metric. You can't iterate on a
single variable if you can't tell signal from noise. You can't optimize cost
if you can't reproduce the same task.

This is why caliper is opinionated: not because we want to constrain users,
but because the principles only work as a system.
