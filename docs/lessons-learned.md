# Lessons Learned: 8 Rounds of browser-pilot Iteration

This is the war story that motivated caliper. 8 rounds of iteration on
[browser-pilot](https://github.com/relixiaobo/browser-pilot)'s agent benchmark
runner produced the methodology in [methodology.md](methodology.md). Each
round taught us something we wish we'd known at the start.

These aren't theoretical lessons. Each one is paired with the round in which
we learned it the hard way, and the actual delta it produced when we
finally fixed the underlying issue.

## TL;DR

| Round | Change | What we *thought* we learned | What we *actually* learned |
|---|---|---|---|
| v0 | Initial baseline | "We need to optimize the agent loop" | The judge had a substring bug we wouldn't find for 4 versions |
| v1 | `bp read` + nav timeout fix | "New tools fix things" | The biggest win is when the LLM literally can't see the content it needs |
| v2 | Drop `backendNodeId` from snapshot | "Token compression matters" | LLMs don't need fields they can't use; cutting noise helps everything downstream |
| v3 | Compact text snapshot + ANSWER fix | "Format matters" | Snapshots get repeated in every turn; per-snapshot savings amortize across the conversation |
| v5 | Structured judge + lazy detection | "We have a 7/7 pass rate!" | **38% of our previous judge results were wrong; the substring bug had inflated everything** |
| v6 | temperature=0 judge + variance run | "Sonnet is more consistent than GPT" | Same task gives different verdicts 36% of the time at N=2; single-shot results are noise |
| v7 | 12-task bucketed baseline | "We need more tasks" | Bucketing reveals model strengths/weaknesses; the `compare` bucket is hardest for everyone |
| v8 | Stale-ref tolerant judge | "GPT-5.4 fabricates" | **Reference answers from 2023 cause false negatives even when the agent is correct against today's website** |

## Round 0: The baseline that lied

We built a simple agent loop in `tests/agent/run.py`:

- LLM gets a task description
- LLM outputs `bp xxx` commands as text
- Runner extracts commands with regex, executes via subprocess
- Results fed back to LLM
- After agent says ANSWER, score with an LLM judge

We ran 24 tasks (4 custom + 20 WebVoyager) with Claude Sonnet. The judge
reported 7/7 passing on every batch.

**This was a lie.** The judge prompt asked the LLM to respond with "CORRECT
or INCORRECT", and we parsed:

```python
llm_pass = "CORRECT" in judge_response.upper()
```

`"CORRECT" in "INCORRECT"` is `True`. **Every INCORRECT verdict was silently
flipped to PASS.** We wouldn't discover this for 4 more rounds.

The lesson: **measurement bugs are silent and self-confirming**. When your
metric is broken in a way that makes things look good, you'll happily
"improve" against it for as long as nobody questions it.

## Round 1: The first real fix

Failure attribution on the v0 results showed the biggest single class was
"snapshot blind to content" — 25% of tasks. Search results, article bodies,
list cards weren't in the accessibility tree, so the agent could see
buttons but not the text it needed to extract.

Fix: a new `bp read` command that returns cleaned page text. Plus a
navigation timeout fix because Cambridge Dictionary was reporting load
failures even on successful loads.

Result: pass rate went from "looked like 7/7 but was really 2/7" up to
"looked like 7/7 but was really 5/7". **Real improvement, but the metric
was still hiding it.**

## Round 2: The token-shaped iceberg

We measured the snapshot output and noticed each element JSON included a
`backendNodeId` field. The LLM never used it (it's an internal handle).
Removing it cut snapshot size by 47%.

Costs dropped on paper. Pass rate stayed flat (correct behavior — the field
was noise).

The lesson here was subtle: **the LLM can't tell you what fields it
ignores**. You have to guess and measure. Anything in the prompt that the
LLM wouldn't use if it had a choice is just paying tax on every turn.

## Round 3: Snapshots compound across turns

Agent loops have a quadratic-ish token growth: each turn includes all prior
turns. By turn 12, the conversation contains 12 snapshots. So
**per-snapshot optimizations multiply across all subsequent turns**.

We rewrote the snapshot to a compact bracketed text format:

```
[1] link "Skip to main"
[2] textbox "Search" "quantum"
[3] button "Submit"
```

instead of JSON. Per-snapshot savings: 38%. But because each snapshot
appears in many turns, total token reduction was 24%.

We also fixed an ANSWER extraction bug: when the agent wrote `ANSWER:` on
one line and the actual answer on the next line, the runner only captured
the empty first line. Sonnet was getting "lazy_failure" labels for tasks
it had clearly completed.

These two changes together cut total tokens from 501K → 308K (-19%) and
"fixed" Sonnet's apparent regression on multi-line answers.

Lesson: **everything that touches LLM context has multiplicative cost
implications**. And **the runner is part of the eval surface** — its bugs
look like agent bugs.

## Round 4: The dark round (no real changes)

Skipped — we made some experimental changes that didn't pan out. Notable
mainly because we were still optimizing against the broken judge metric
without knowing it.

## Round 5: The bug that broke our hearts

We added two things that revealed the truth:

**Structured JSON judge output**: instead of asking for "CORRECT or
INCORRECT", ask for `{"verdict": "correct"}` or
`{"verdict": "incorrect"}`. Parse with JSON. Fall back to keyword matching
with INCORRECT-first priority.

**Lazy detection**: track whether the agent ever called any observation
command (read/snapshot/eval/screenshot/locate/cookies/tabs). If the agent
gave an ANSWER without ever observing the page, it was making things up.

Running these on the same 24 tasks, we re-scored the saved logs from v0-v4
with the corrected parser.

```
                         old score    actual score
Sonnet v0 judge pass     7/7          2/7    ← all the celebration was fake
Sonnet v1                7/7          5/7
Sonnet v2                7/7          6/7
Sonnet v3                7/7          5/7
Sonnet v5                7/7          6/7    ← actually correct
```

**38% of our previous judge results had been wrong.** The "improvement"
arc we'd been celebrating was real in some places (v0 → v3 was actually
+3 on judge pass) but not where we thought it was.

Worse: gpt-5.4, which we'd believed was performing well, was actually at
3/7 not 6/7. We'd been comparing models with a metric that flipped
38% of the time.

This is **the** lesson of caliper: **a measurement bug at the metric layer
is more dangerous than any bug in the system being measured**. It
contaminates every decision downstream.

## Round 6: The variance reckoning

Even with the judge bug fixed, we noticed something weird: re-running the
same task twice didn't always give the same result.

We did a systematic variance run: 7 tasks × 2 runs × 2 models = 28 runs.

Result: **judge verdicts disagreed across runs in 5 out of 14 (model, task)
pairs — 36% inconsistency.**

For Sonnet, token spreads on the same task were as high as 43%. For
gpt-5.4, token spreads were as high as **125%** — the same task ran for
3K tokens in one run and 14K tokens in another.

This invalidated almost all of our single-shot v0 vs v1 vs v2 comparisons.
Most of the deltas we'd seen were within the noise floor.

Two things came out of this:

1. We added `temperature=0` to the judge call so at least the *judge* part
   was deterministic. (The agent calls remained at default temperature
   because we wanted to test real-world stochasticity.)
2. We made N≥2 the default everywhere, with a warning when N=1 results
   were used.

**The 36% inconsistency number is the entire reason caliper enforces
N≥2 as a default rather than a recommendation.**

## Round 7: The bucketed baseline

We curated 12 stable tasks across 4 buckets (lookup / search / compare /
navigate) and ran them at N=2 with both models. This became the "v7
baseline".

Per-bucket results immediately showed the most interesting finding of the
8 weeks:

| Bucket | Sonnet | gpt-5.4 |
|---|---|---|
| lookup | 6/6 (100%) | 4/6 (67%) |
| search | 6/6 (100%) | 3/6 (50%) |
| **compare** | **3/6 (50%)** | **2/6 (33%)** |
| navigate | 6/6 (100%) | 4/6 (67%) |

**Both models failed half the `compare` tasks.** No amount of tool or
prompt iteration was going to fix this — there had to be something
structural about the task type or about the benchmark.

Two of the three compare tasks were Apple — "compare the prices of the
latest MacBook Air models" and "compare iPhone 15 Pro vs Pro Max".
Investigating further led to round 8.

## Round 8: Reference answers expire

The Apple tasks were "failing" because:

- **Reference answer** (from WebVoyager 2023): "MacBook Air M2 from $1099"
- **Sonnet's answer** (correct against today's apple.com in 2026): "MacBook
  Air M5 from $1099"

The judge was scoring the M5 answer as INCORRECT because the chip
generation didn't match the reference. **The agent was correct against
reality and wrong against the benchmark.**

Same for iPhone 15 Pro → iPhone 17 Pro (current model).

The fix was a single edit to the judge prompt:

```
- Reference answer: ...
+ Reference answer (may be outdated, written 2023/2024): ...
+
+ Grading rules:
+ - The agent visited the live site NOW. If the task asks for "latest" or
+   "current", accept factually-plausible current answers even when the
+   specific version/name in the reference differs.
+ - For non-time-sensitive tasks (pronunciations, math, fixed documentation),
+   the agent's answer must still match the reference.
```

Effect on the compare bucket:

| Model | v7 compare | v8 compare |
|---|---|---|
| Sonnet | 3/6 (50%) | **5/6 (83%)** |
| gpt-5.4 | 2/6 (33%) | **6/6 (100%)** |

Pass rate jumped without breaking other buckets (verified by spot-checking
lookup/search/navigate).

**Stale references are a pervasive problem in any benchmark with
time-sensitive answers.** The fix is a judge prompt rule, not a tool
change.

## Meta-lessons

Across the 8 rounds, the most important pattern was this:

**The biggest improvements came from finding bugs in the measurement
layer, not from optimizing the system being measured.**

| Round | Type | Real impact |
|---|---|---|
| v1 (bp read) | Tool layer | +3 pass (real) |
| v2 (snapshot trim) | Format layer | -19% tokens (real) |
| v3 (compact text) | Format layer | -24% tokens (real) |
| **v5 (judge bug)** | **Measurement layer** | **Revealed all previous numbers were wrong** |
| **v6 (variance)** | **Measurement layer** | **Revealed 36% of single-shot verdicts were noise** |
| v7 (bucketing) | Method layer | Revealed the compare-bucket structural failure |
| **v8 (stale-ref)** | **Measurement layer** | **+2 to +4 pass per model from a single prompt edit** |

Three of the highest-ROI changes (v5, v6, v8) were measurement-layer
fixes. They didn't change the agent or the tools at all. They changed
how we *interpreted* what the agent was doing.

**This is why caliper exists.** The single most valuable thing it can
provide is a measurement layer that doesn't lie. Everything else is
secondary.

## What we'd do differently

If we were starting browser-pilot iteration today, knowing what we know:

1. **Day 1**: Write the JSON verdict parser test (`test_incorrect_is_not_parsed_as_correct`).
   This is the single most valuable line of code we wrote in 8 weeks.

2. **Day 1**: Set N≥2 as the default. Don't trust any single-run result.

3. **Day 2**: Build the failure attribution table before optimizing
   anything. Tag every failure with TOOL_BUG / TOOL_LIMIT / SKILL_GAP /
   LLM_BEHAVIOR / SITE_ISSUE / REF_STALE.

4. **Day 3**: Track cost in $ from the start, not tokens. We never knew
   our real cost during v0-v8 because we were measuring tokens.

5. **Day 5**: Run a 2-model A/B (Sonnet + Haiku) at the first opportunity.
   This would have caught the judge bug in week 1 instead of week 5,
   because the GPT-shaped numbers would have been suspiciously high.

6. **Day 7**: Add stale-ref tolerance to the judge prompt for any
   benchmark with time-sensitive references. WebVoyager has many.

These 6 things take maybe a day total to set up. They would have saved
us 6 of the 8 weeks. **Caliper bakes them in as defaults.**

## Reference: the actual numbers

For posterity, the real Sonnet performance arc on 7 representative tasks
across versions (corrected after the v5 judge bug fix):

| Version | Pass rate | Total tokens | Notes |
|---|---|---|---|
| v0 | 2/7 | 578K | Apparent 7/7 was a lie |
| v1 | 5/7 | 501K | bp read + nav fix |
| v2 | 6/7 | 404K | snapshot trim |
| v3 | 5/7 | 308K | compact text + answer fix |
| v5 | 6/7 | 292K | structured judge revealed real numbers |
| v8 | (extrapolated from 12-task baseline) | ~290K | stale-ref tolerance |

Pass rate from 2/7 → 6/7 is **the real story of 8 weeks**, not the 7/7 →
7/7 illusion. Total tokens dropped 49%. Both numbers are real and
verifiable against the saved test-results JSON files.

This is the story caliper exists to prevent for everyone else.
