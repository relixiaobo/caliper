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

---

# Phase 1: caliper port lessons (post-extraction)

The 8 rounds above are the **pre-history** of caliper — the war story
that justified extracting it. What follows is the **first week of the
extracted project itself**: M1.1 → M1.3 of the Phase 1 browser-pilot
port. The lessons here are different in character — they're about the
discipline of building a measurement-discipline framework, with all
the meta-recursion that implies.

## M1.1: the ANSWER-before-commands ordering bug

The first non-trivial bug found *during* Phase 1, before any external
review.

The text-protocol agent loop was supposed to behave like this: each
turn, parse the LLM's output, run any `bp` commands, feed results back,
let the LLM decide when to write `ANSWER:`. Implementation was the
obvious thing — extract `ANSWER:` first; if found, terminate; otherwise
extract commands and run them.

**The bug**: when the agent emitted both commands AND an `ANSWER:` in
the same turn (because the LLM hallucinated what it thought the
commands would return), the loop accepted the answer immediately and
**never ran the commands**. The first cambridge_smoke run produced
`judge_pass=1.0` but `lazy=1.0` — the lazy detector correctly flagged
that no observation commands had run.

**The fix**: invert the order. If the turn contains commands, run
them and feed the real output back; ANSWER is only terminal on a turn
with no commands. The hallucinated answer gets discarded; the real
output forces the next turn to revise.

**The lesson**: this is exactly the failure mode methodology
principle 1 (P1) is supposed to catch — a measurement bug that
made things look correct (judge_pass=1.0) when they were actually
broken (lazy=1.0). The reason it was caught in 30 seconds instead
of weeks is that **caliper had two independent scorers running on
the same sample**. Single-scorer measurement would have shipped this.

The cost of running two scorers per sample is small. The benefit
is they cross-check each other.

## Phase R: discovering the structural cliff

After M1.1, I asked Claude to look at the project structure and think
about whether it would survive Phase 3 (the chatbot scenario, which
adds ~1500 lines of new code per `chatbot-maxturns.md`). The answer
came back with five problems:

1. **State contract is informal**: solver and scorer communicate via
   `state.store` (an untyped dict). A typo in one side silently
   breaks the other.
2. **`lazy_detection` has a redundant param**: `observation_commands`
   on the scorer is unused — the solver is the only authority.
3. **`Strategy` not a first-class concept**: chatbot scenario needs
   `Strategy` as an experimental axis, but caliper's solver/scorer
   model doesn't have it.
4. **"Caliper provides vs consumer provides" boundary is fuzzy**:
   chatbot would want to add ~1700 lines to `caliper.*`, blowing
   the "thin layer" promise.
5. **bp SKILL.md path is hardcoded** to my dev machine.

Five issues, all small individually, all permanent if not fixed.

The decision: **stop and restructure in one shot** rather than
patch each issue separately and accumulate technical debt. The
math: at v0.0.1 with 6 source files, restructure cost ≈ 1 hour. At
v0.5.0 with 50 source files, restructure cost ≈ 1 week.

Phase R restructured caliper into a **uv workspace with 4 sibling
packages** — `caliper` core + 3 adapter packages (`browser-pilot`,
`computer-pilot`, `chatbot`). Three hard rules:

1. `caliper` core never imports from any `caliper-*` adapter
2. Adapters never import from each other
3. Promotion to core requires the rule of three (used in ≥2 adapters)

Plus the typed `SolverState` Pydantic StoreModel as the formal
contract between solvers and scorers.

**The meta-lesson**: I asked Claude to predict the structural cliff
*before* I hit it, and the prediction was right. The cost of one
hour of upfront structural review caught a problem that would
have cost weeks at Phase 3. **Structural review at every milestone
boundary is cheap insurance**.

## M1.2: re-scoping cost wrapper to token observability

The original M1.2 plan was to write a cost wrapper: pricing table +
`cost_usd()` function + `cost_tracker` scorer that emits $ per
sample. The user pushed back: "we mainly want to observe and
control token consumption, and improve cache utilization — we're
not really focused on actual price."

That triggered a deep research pass into Inspect AI 0.3.205's
cross-provider `ModelUsage` support. Reading every provider adapter
under `inspect_ai/model/_providers/*.py` revealed three structural
facts:

1. **Inspect AI ships zero pricing data**. The `ModelCost` schema
   and `compute_model_cost()` function exist, but the bundled
   YAML files for anthropic / openai / google / grok / together /
   mistral / deepseek have **zero `cost:` entries**. Every provider
   returns `total_cost=None`. There is no upstream price to "prefer
   over our own table".

2. **Same-model iteration doesn't need dollars**. The iteration
   loop caliper actually supports — SKILL.md tweaks, solver
   parameter changes, prompt edits — holds the model fixed. Within
   a fixed model, fewer tokens is **strictly cheaper**. Tokens
   are cost.

3. **No universal `effective_tokens` formula exists across
   providers**. Different providers have different cache pricing
   ratios (Anthropic cache_write=1.25×, OpenAI has no cache_write
   at all and cache_read≈0.5×, Gemini caches differently). Any
   single-number "effective tokens" metric using one set of weights
   would be silently wrong for somebody.

The conclusion: **drop the pricing table entirely**. Drop the
scorer. Drop the $ field. Replace with a single
`UsageSummary` dataclass that normalises `ModelUsage` across all 27
Inspect AI providers, with honesty flags (`has_cache_info`,
`has_reasoning_info`) to distinguish "provider reported zero" from
"provider didn't report".

**The lesson**: an aggressively-scoped feature can be the wrong
abstraction. A pricing table sounded like the obvious thing to
build, but the user's actual use case is "observe token consumption
and cache utilization in same-model iteration". Those are simpler
needs that **don't require any pricing knowledge at all**. The
result is ~70 lines of code instead of ~280, with zero ongoing
maintenance burden, and a more honest measurement layer because it
doesn't pretend to know things it can't know (like how Bedrock's
silent cache fields should be interpreted as a hit rate).

This reinforces methodology principle 1 from a different angle:
**don't build measurement abstractions that require knowledge you
can't actually verify**. Pricing tables go stale silently. Honesty
flags don't.

## Three rounds of Codex review on M1.1, M1.2, M1.3 — the meta lesson

Across M1.1, M1.2, M1.3 the same pattern repeated: I'd write code,
it'd pass all my own tests, I'd ask Codex to review it, and Codex
would find a P-level bug I hadn't seen. Total over the three
milestones: **10 P-level bugs in 3 review rounds**.

| Milestone | Round | Class | Specific finding |
|---|---|---|---|
| M1.1 | 1 | parser | Unbalanced quote heuristic false-positives on `bp type 7 "Don't"` |
| M1.1 | 1 | shell | URL with `?&` characters in `bp open` not shell-quoted |
| M1.1 | 2 | security | `run_cli` used `create_subprocess_shell` → LLM emitting `bp read; rm -rf ~` runs both |
| M1.2 | 1 | logic | `uncached_input_tokens` dropped `cache_write_tokens`; SKILL.md spike was hidden |
| M1.2 | 1 | aggregation | Mixed-bucket cache_hit_rate diluted by silent provider |
| M1.2 | 2 | provider quirk | OpenAI Responses adapter sets `cache_read=None` for cold cache; classified as "unknown" instead of "0.0" |
| M1.3 | 1 | runtime | `judge_stale_ref()` factory called `get_model()` → Task construction needed `ANTHROPIC_API_KEY` |
| M1.3 | 1 | packaging | `setuptools.packages.find` doesn't include `data/*.jsonl`; wheel install was broken |
| M1.3 | 2 | discovery | `inspect eval v8_baseline.py` discovered all 5 `@task` in the file → 48 runs instead of 24 |

Each one has a regression test now. Each one would have shipped
without the review.

**The pattern**: every single one was an "I assumed X but didn't
verify" failure. I assumed the quote-counting heuristic worked, the
shell would never see metacharacters, the silent provider's
contribution to a cache hit rate would somehow be benign, the
factory function wouldn't touch credentials, the build system would
"just include" data files. None of these assumptions held.

**The meta-lesson**: LLM-assisted development has this failure mode
**built in**. The LLM (Claude in this case) generates plausible code
that passes plausible tests, and the gaps are exactly the places I
wouldn't think to test. The fix is **mandatory structural review by
a different model with a different prompt** at every milestone
boundary. Not optional. Not "if I have time". Mandatory.

For Phase 2 onwards: every milestone closes with a Codex review
round. The 10 bugs above would have cost hours-to-days each in
production debugging. The reviews caught them in minutes.

Phase 1 also caught 3 bugs *I* found during my own work (the
ANSWER-before-commands ordering, the macOS .pth hidden flag,
the lazy detection regression in cambridge_smoke), so the total
"bugs found before they shipped" count for Phase 1 is **13**.
That's a lot of production bugs avoided.

## macOS Sequoia .pth hidden flag — operational landmine

While debugging the Phase R restructure, the `caliper` package
suddenly stopped being importable from the venv. The `__editable__`
.pth file was in site-packages but Python couldn't see it.

After ~30 minutes of debugging (including reading `site.py` source
in Python 3.13), the cause: **macOS Sequoia marks newly-created
.pth files in site-packages with `UF_HIDDEN`** (visible via
`ls -lO` and the `com.apple.provenance` extended attribute), and
**Python 3.13's site.py refuses to process .pth files with the
hidden flag set**. So every `uv sync` would silently break the
editable install.

The fix is **don't depend on `.pth` for tests** — set explicit
`pythonpath = ["packages/*/src"]` in pytest config. Examples have
to do their own `sys.path` insertion or be invoked from a wrapper
that sets `PYTHONPATH`.

**The lesson**: package installation paths that work everywhere
**also have to work on macOS Sequoia**. This is the kind of
landmine that costs hours of investigation per occurrence and
isn't documented anywhere obvious. Recording it here so the next
person doesn't lose the same hours.

## Cumulative Phase 1 lesson summary

The first week of caliper port shipped:
- 4 git commits (M0.6, Phase R, M1.2, M1.3)
- 124 unit tests across 4 packages
- ~600 lines of `caliper` core code (+adapter packages)
- 13 caught-before-shipping bugs (10 from Codex review, 3 from
  internal testing/dogfooding)
- 0 production incidents

The discipline that made this work is the same discipline the v0–v8
browser-pilot iteration *lacked*: **assume your own measurement is
broken until proven otherwise, and have a way to prove it**. For
caliper this means:

1. Two independent scorers per sample (judge + lazy detection)
   cross-checking each other
2. A typed state contract (`SolverState`) so solver/scorer
   communication can't drift silently
3. Mandatory structural review at every milestone boundary
4. Honesty flags on observability data so "unknown" can never be
   confused with "zero"
5. Regression tests for every bug caught, named after the failure
   mode (the substring bug regression test is the prototype for
   this naming convention)

These five practices are the operational form of the 5 methodology
principles. Phase 1 shows they work at the scale of "build a
framework". Phase 2 (self-eval) and Phase 3 (second consumer)
will show whether they generalise.

## M1.6: the post-mortem that needed its own post-mortem

M1.6 produced caliper's first self-measured baseline against the
12 v8 curated tasks. The target was Sonnet 22-24/24 and GPT-5.4
16-18/24, ±1 of the v8 anchors, with Apple--3 reproducing its
canary failure mode.

**Neither target held.** Sonnet 19/24, GPT-5.4 13/24 with 24/24
lazy, Apple--3 passed both epochs, 5 other Sonnet samples hit
max_turns=12 instead.

The first-pass write-up of this deviation (commit 1536416, the
original `baselines/v9.json` `methodology_notes`, and the first
draft of this section) labelled all of it "environmental drift"
and called it "the most important methodological finding of
Phase 1". **That write-up was wrong in exactly the way the rest
of this file exists to prevent.** I wrote it after reading
**one** Sonnet trace and **zero** GPT-5.4 traces, then applied a
single root-cause label to five distinct failures. The only
reason I noticed was the user asking me to "fundamentally
analyze the test process and results", which forced me to go
look at the evidence I should have read on day one.

This section is what the post-mortem should have said the first
time. The original overclaims are recorded below under "what
does not hold" so the failure is on the permanent record.

### The meta-error: a measurement bug in my own narrative

Methodology principle 4 is "failure attribution before aggregate
reporting". The first draft violated it: I aggregated 5 failures
into one narrative before attributing **one** of them from
trace evidence. The *numbers* in `v9.json` were correct; the
*story* about them was not.

This is the same failure mode as the v0 substring bug from the
pre-history above: a broken metric (here, my first-pass
narrative) that made things look like a clean story, so I
happily wrote conclusions against it. The lesson isn't new —
it's literally the reason caliper exists — but apparently I
needed to fail at it one more time to internalise it as a
workflow habit, not just an abstract principle.

Going forward: any baseline deviation claim in this project
must cite at least one trace per failure class, and the claim
must be falsifiable. "5 TOOL_LIMIT failures split 2/1/2 across
three root causes" is falsifiable. "Environmental drift" is
not.

### What actually caused the 5 Sonnet failures

(This section has been rewritten twice. The history is recorded
in "what does not hold" below — the short version is that I had
to go back and read the traces again after a Codex review round
caught that I'd mis-classified Apple--0.)

After reading every Sonnet TOOL_LIMIT trace, the 5 failures
split **1 / 1 / 3** — with CHROME_TAB_POLLUTION clearly
dominant:

| Sample | Class | Trace evidence |
|---|---|---|
| Wolfram Alpha--0 | **SITE_RENDER** | The derivative answer (`11.2`) appears *only* inside SVG path coordinates. Agent writes: *"All three occurrences of '11.2' are SVG path coordinates, not the actual result. The result is rendered as an image."* Runs out of turns trying to extract the number through DOM selectors. |
| BBC News--5 | **REF_STALE** | First `bp open` on the reference URL returns the literal page title *"BBC - 500: Internal Server Error"*. Agent correctly falls back to a Google search but cannot recover the intended article. |
| Huggingface--3 | **CHROME_TAB_POLLUTION** | Agent logs verbatim: *"The browser is clearly rendering Coursera content even though the URL shows Hugging Face. It seems there's a tab mismatch."* Trace contains 28 Coursera and 6 Allrecipes mentions during what should be a Hugging Face task. |
| Allrecipes--0 (ep 2) | **CHROME_TAB_POLLUTION** | 26 BBC mentions appear during the Allrecipes task — previous-sample BBC state bleeding into the current sample. |
| Apple--0 (ep 2) | **CHROME_TAB_POLLUTION** | Initial `bp open` on the MacBook Air page correctly returned `From $1099` / `From $1299` prices — **not** an "empty React shell" (as the first correction draft wrongly claimed). Later in the trace, tool output switches to Allrecipes content, matching the same session-pollution signature. 137 commands in 12 turns is the agent retry-looping through this pollution. |

**CHROME_TAB_POLLUTION is the dominant finding.** The mechanism
is specific and reproducible: bp attaches to the user's *real*
Chrome (that's its design point — it keeps real logins and
cookies), which means bp's Chrome state is *not* hermetic
across samples. Previous-sample URLs, tab navigations, and
even the user's own ambient browser activity can leak into the
current sample's view of the page. caliper's
`text_protocol_agent` assumes bp is per-sample clean; it isn't.

There's also a fourth sample where CHROME_TAB_POLLUTION
*might* be present: the Wolfram Alpha trace, even though
SITE_RENDER is the proximate cause of running out of turns,
contains two session-pollution signals. Mid-trace, the agent
clicks an element and lands on Merriam-Webster, then notes
*"this appears to be the user's actual browser state — a
different tab or navigation occurred"*. And the final `bp net`
in the same trace lists exactly one request: a `GET
https://www.allrecipes.com/`. So pollution may in fact touch
4 of 5 failures, but for Wolfram the SVG issue is what
actually ended the episode.

The fix surface for CHROME_TAB_POLLUTION is concrete: either
`bp` needs to support a per-sample ephemeral profile, or
caliper's text-protocol solver needs to explicitly reset tabs
at sample start. This is a real M1.7-class bug with a real
patch, not "drift".

### What actually caused GPT-5.4's 24/24 lazy rate

The pattern is uniform across all 24 runs: each sample gets
task + initial (near-empty) snapshot, the agent emits one
turn containing `ANSWER:` directly from training data, the
conversation ends. For every failed sample:
`message_count = 3`, `commands_run = 0`, uncached input mean
= 930 tokens. Sonnet's mean on the same tasks: 96,840 tokens.

Some of the training-data answers happen to be correct (BBC
fossil-fuels article, where the reference hasn't moved). Some
are hallucinated (Allrecipes recipe names the agent never
saw). Some are simply wrong in checkable ways (GitHub
storage delta: agent says 30 GB, real answer is 48 GB).

The first draft labelled this "model drift". **That label is
not evidence-based.** I did not compare the gpt-5.4 API
behaviour on 2026-04-07 vs 2026-04-08; I only observed the
2026-04-08 behaviour. The correct label is "single-turn
training-data answer" — a behavioural description, not a
causal claim. Possible causes include:
- Initial snapshot content being fed differently than in v8
- Inspect AI OpenAI Responses adapter context formatting
- Actual model-level drift at the provider
- Text-protocol prompt interacting badly with gpt-5.4's
  tool-use training

M1.6 does not distinguish between these. A future milestone
could — run the same tasks through the legacy `run.py` path
on the same day and compare — but M1.6 as-run cannot.

What M1.6 **does** tell us, and this survives the post-mortem,
is that **caliper's `lazy_detection` scorer surfaced the
collapse immediately**. Without it, 13/24 would read as a
plausible 54% agent. With it, `lazy_rate = 1.0` shows pass
rate is measuring training-data recall, not agent capability.

### The findings that do hold

Stripping out the overclaims, what M1.6 actually proved:

1. **`lazy_detection` catches silent capability collapse.**
   gpt-5.4 at 13/24 looks fine on pass-rate alone; caliper
   shows it's 0/24 real performance. This is the M1.1
   two-scorer invariant firing exactly as designed. ✓

2. **Per-bucket failure attribution separates capability
   from environment.** After two rounds of re-reading, 5
   Sonnet failures resolved into 3 root-cause classes
   pointing at different fixes. A single bucket-free pass
   rate would have called this "Sonnet got worse". ✓

3. **Cache-hit-rate visibility surfaces provider-specific
   behaviour v8 couldn't see.** Sonnet 0.0% (Anthropic
   default doesn't enable explicit `cache_control`) vs
   gpt-5.4 73.9% (OpenAI prefix auto-cache) is a factual
   observation about how UsageSummary normalises
   cross-provider cache data. ✓

4. **bp's Chrome session is not hermetic across samples
   and it is the dominant source of Sonnet's M1.6 failures.**
   3 of 5 failures are directly attributable to session-state
   pollution (and a 4th shows pollution signals). Concrete,
   reproducible bp bug with a concrete fix (per-sample
   ephemeral profile / explicit tab reset). ✓

### The findings that do NOT hold

Claims removed across two rounds of post-mortem correction.
Recording them explicitly so the failure mode is on the
permanent record, not edited out of git history.

**From the first draft (pre-trace read):**

1. ❌ **"Environmental drift" as a single root cause.** The 5
   failures are at least 3 distinct classes, dominated by one
   specific bp bug. "Environmental" was a handwave that
   covered for not having looked.
2. ❌ **"Slow network to Anthropic API" as the driver of
   TOOL_LIMIT hits.** Per-turn API latency was never
   measured; I inferred it from 46:21 wall time. Wall time
   is consistent with slow *page loads* and long retry
   loops, not specifically with slow API.
3. ❌ **"gpt-5.4 model drift" as the cause of the lazy
   pattern.** Not measured. Replaced with the behavioural
   description "single-turn training-data answer" until
   properly tested with a controlled comparison.
4. ❌ **"The single most important methodological finding of
   Phase 1."** Rhetorical inflation. The lazy-detection win
   is real, but it's the *same* M1.1 two-scorer invariant
   firing on a second data point.
5. ❌ **"Most honest agent-eval baseline I've ever seen in my
   own work."** The *numbers* are honest; the *first-draft
   narrative* was not. Baselines are made honest by the
   analysis, not by the aggregation.

**From the second draft (after reading 5 traces, caught by
Codex review):**

6. ❌ **"Apple--0 ep 2 SITE_RENDER / empty React shell."** The
   trace shows the first `bp open` on the MacBook Air page
   already returned populated `From $1099` / `From $1299`
   entries — the page *did* render. The real failure mode is
   CHROME_TAB_POLLUTION (Allrecipes content appears later in
   the trace). I had classified it from the shape of the
   numbers ("137 commands in 12 turns, must be rerender
   retry loop") without reading deeply enough into the
   messages. Codex caught this by directly reading the
   `.eval` log.
7. ❌ **"SITE_RENDER × 2."** Only Wolfram Alpha is a clean
   SITE_RENDER case. The corrected bucket size is ×1, and
   CHROME_TAB_POLLUTION went from ×2 to ×3.

Each correction round shrank the error bars by forcing me to
read one more trace. The lesson is that **the number of
traces I've actually read is a better predictor of narrative
accuracy than the number of post-mortem iterations.**

### The meta-lesson (that actually holds)

**A post-mortem written from the shape of the numbers instead
of from the trace evidence is itself an uninstrumented agent
step.** It produces a plausible answer (the narrative) without
ever observing the page (the traces). The cure is the same as
for any lazy agent: require tool calls before ANSWER — here,
require trace citations before any root-cause claim.

I had to learn this twice in the same milestone. The first
correction round ("read the traces") caught the
"environmental drift" handwave and the bogus gpt-5.4 "model
drift" claim. The second round ("read them *again*, properly")
caught the Apple classification error, and only happened
because a Codex review actually opened the `.eval` log and
checked. Both corrections came from the same source — looking
at the evidence — and both were necessary. A claim that
survives one read can still be wrong; what matters is whether
the read is thorough and whether you were ready to admit
surprise.

That is the M1.6 lesson I'm actually confident in, because I
had to live through failing it in two different ways.
