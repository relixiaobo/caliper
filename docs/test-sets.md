# Test Sets: Strategy and Sources

> Caliper provides the framework. But a framework without test data is
> useless — and test data is harder than the framework.

This document is the strategy for how caliper handles the **test set
problem**: where tasks come from, how they're vetted, how they're
maintained, and how to think about them in layers.

It complements [`methodology.md`](methodology.md) (which covers *how*
to iterate) and [`architecture.md`](architecture.md) (which covers
*what* the framework provides). This document covers *what data you
feed into it*.

---

## Why test sets are the hard part

Caliper's value proposition is "evidence-based iteration". But evidence
requires *good test data*. And good test data is genuinely hard, for
reasons that aren't obvious until you've burned a few weeks on them.

The 8-week browser-pilot iteration that motivated caliper hit at least
five distinct test-set problems:

1. **Stale references**: WebVoyager's "compare MacBook Air models"
   reference said "M2 chip $1099" (written 2023). In 2026 the answer is
   "M5 chip $1099". The agent was correct against the live site but
   wrong against the benchmark. We discovered this in v8 and added
   stale-reference tolerance to the judge prompt.

2. **Site state drift**: Cambridge Dictionary added a Cloudflare wait
   page that broke our navigation timeout detection. Allrecipes
   periodically reformats their search results. ESPN data updates daily.

3. **Sample size vs cost**: Our v6 7-task set was too small to
   distinguish signal from noise. We expanded to 12 tasks at v7. Going
   to 100+ would cost ~10x more per benchmark run.

4. **Coverage bias**: Our 12 tasks were heavily lookup/search/navigate.
   We only discovered "compare" was a structural failure mode after
   bucketing the v7 results. Without the bucket, the failures would
   have been a uniform background.

5. **Maintenance**: Every WebVoyager reference answer that mentions
   "latest" or "current" rots over time. There's no automated way to
   detect this.

These aren't unique to browser-pilot. **Any team building agent eval
infrastructure will hit some subset of these.**

## The full dimensions of test set difficulty

Beyond the five we hit, here's the complete list of dimensions that
make test sets hard:

| Dimension | What it means | Example |
|---|---|---|
| **Staleness** | Reference answers expire | "Latest MacBook Air" reference from 2023 |
| **Site drift** | Real sites change layout / add anti-bot | Cambridge Cloudflare interstitial |
| **Sample size vs cost** | More samples = better stats but more $ | 12 vs 100 vs 643 tasks |
| **Distribution bias** | Test set ≠ what real users do | curated benchmark vs production traffic |
| **Solvability unknown** | No one labeled "this should take K turns" | Forces you to guess `max_turns` |
| **Coverage blind spots** | You only test what you think to test | We didn't test "compare" until v7 |
| **Maintenance burden** | Who keeps the test set fresh? | Quarterly re-validation? Who pays? |
| **License** | Can you use other people's benchmarks? | WebVoyager is academic-only |
| **Reproducibility** | Same task twice can give different results | Live network, time-sensitive data |
| **Author bias** | Test set reflects what *you* wanted to test | "Compare" tasks were rare because we don't shop |
| **Contamination** | Public benchmarks leak into training data | SWE-bench has known contamination issues |
| **Verification difficulty** | Open-ended answers hard to grade | "Summarize this article" — what's correct? |

You don't need to solve all 12. But you need to **know which ones
apply to your use case** and have a strategy for each.

---

## The layered strategy

Caliper's recommendation: **don't pursue a single perfect test set.
Use 5 layers, each with a different purpose, sample size, and
stability requirement.**

```
                                    ▲
                                Layer 5
                              Real-world
                                Replay
                              (10–100)
                            ────────────
                          Layer 4
                       Synthetic/Mock
                         (varies)
                       ──────────────
                     Layer 3
                  Broad Coverage
                    (100–500)
                  ────────────────
                Layer 2
            Stable Baselines
               (20–50)
            ─────────────────
          Layer 1
      Smoke Tests
        (5–10)
      ────────────
```

The pyramid metaphor matters: lower layers are cheap, high-volume,
fast-feedback. Higher layers are expensive, lower-volume, more signal-
rich. **You run lower layers more often, higher layers less often.**

Each layer answers a different question. You need all of them.

---

### Layer 1: Smoke tests (5–10 tasks)

**Purpose**: "Is anything obviously broken?" — 30 seconds to run.

**Characteristics**:
- Hand-written, fully deterministic
- Zero external dependencies (or only the most stable)
- Zero cost or near-zero cost
- Run on every code change

**Example tasks** (browser-pilot):
- Login to `the-internet.herokuapp.com` (a stable test site)
- Check both checkboxes on a checkbox page
- Select "Option 2" from a dropdown
- Wait for dynamic loading and read the result

**Source**: Hand-write them. Smoke tests are not where you need
breadth; you need 5 minutes of "did I break anything basic".

**What caliper provides**:
- Templates for common smoke patterns
- A `caliper smoke` command (Phase 4) that runs these specifically
- Defaults to N=1 because the goal is fast feedback, not statistics

**What you learn**: Whether the basic agent loop, the LLM call, the
tool invocation, and the judge all still work end-to-end. **Not** how
good the agent is.

---

### Layer 2: Stable baselines (20–50 tasks)

**Purpose**: "Is my last change real?" — the A/B comparison layer.

**Characteristics**:
- Hand-curated from public benchmarks
- Bucketed by task type (lookup / search / compare / navigate / ...)
- Prefer golden references where available
- Each task has a documented reason for inclusion
- Run at N≥2 (typically N=3) for variance measurement
- The data file is **committed to git** with a version tag
- Used for cross-version A/B comparison

**Example**: The 12 WebVoyager tasks in browser-pilot's v8 baseline,
documented in `reference/curated-tasks.md`. They were curated from
the 643-task WebVoyager source by hand-validating each one for
stability and bucket coverage.

**Sources** (browser/web tasks):
- **WebVoyager** — 643 real-website tasks; staleness is a known issue
- **AssistantBench** — 214 hand-crafted tasks with verified short
  answers; *very* clean
- **GAIA** — 466 general-assistant tasks with exact-match references
- **Web Bench** (Skyvern) — 2454 live-site tasks (largest current set)
- **Online-Mind2Web** — 300 live-site tasks (subset of Mind2Web)
- **WebArena** — 800+ tasks but requires self-hosting

For other domains:
- **macOSWorld** (computer use) — 200 tasks across 30 apps
- **OSWorld** (general desktop) — 369 tasks
- **SWE-bench Verified** (coding) — known training contamination, use
  with caveat
- **BFCL** (function calling) — tests *just* tool call correctness
- **Terminal-Bench** (terminal coding) — small but well-curated

**What caliper provides**:
- `caliper.datasets.webvoyager` — load and convert WebVoyager JSONL
  to caliper Sample format
- `caliper.datasets.assistantbench` — same for AssistantBench
- `caliper curate` (Phase 4) — interactive tool for selecting subsets
- Bucket assignment via metadata
- Per-task variance tracking across runs

**What you learn**: Whether a code change moves the needle on the
*specific subset* you trust most. This is your A/B comparison layer.

---

### Layer 3: Broad coverage (100–500 tasks)

**Purpose**: "Does my improvement generalize?" — 10× the volume of
Layer 2 to make per-task noise less important.

**Characteristics**:
- Larger subsets of public benchmarks (or full benchmarks)
- Less hand-curation; accept that some tasks are noisy
- Individual task signal is weak; **aggregate signal is strong**
- N=1 is acceptable (sample size compensates for variance)
- Run less frequently than Layer 2 (weekly, not per-commit)

**Example**: The full 643-task WebVoyager benchmark instead of the
curated 12.

**Sources**: Same as Layer 2, but use them at scale rather than in
curated subsets.

**What caliper provides**:
- The same dataset loaders, but unfiltered
- Statistical aggregation tools that compute confidence intervals
- Failure attribution distributions across the larger sample
- Bucket reports that show which task categories drive aggregate

**What you learn**: Whether a change is *robust* across many tasks,
not just the 12 you happen to have curated. The signal here is weaker
per task but stronger in aggregate.

**Important**: Layer 3 results should be **reported as aggregates**,
not as per-task tables. A 100-task table is unreadable. Group by
bucket, by failure tag, by source, by complexity.

---

### Layer 4: Synthetic / mock (varies)

**Purpose**: "Test specific behaviors that real-world tasks can't
isolate."

**Characteristics**:
- Mock tools instead of real network calls
- Fully deterministic (same input → same output)
- Zero variance from external sources
- Used to test framework features, not agent capability
- Sample size depends on what's being tested

**Example use cases**:
- **Chatbot maxTurns testing** (see [chatbot-maxturns.md](chatbot-maxturns.md)):
  Tasks designed to *force* the budget limit, with mock tools that
  predictably need K+1 steps to complete.
- **Lazy detection validation**: Construct traces where the answer
  is in the tool history but the agent didn't observe — verify the
  lazy detector flags it.
- **Tool call accuracy**: Mock a tool, check whether the LLM picks
  the right tool with the right args for a known scenario.
- **Stress testing the judge**: Hand-labeled (answer, expected_verdict)
  pairs where you know the truth.

**Source**: Author them yourself. LLMs can generate variants, but
the seed task design is human work.

**What caliper provides**:
- `caliper.mocks` (Phase 3) — a framework for building deterministic
  mock tools and the tasks that use them
- `caliper.solvers.mock_tool_solver` — a solver wrapper that swaps
  real tool calls for mock ones in benchmark mode

**What you learn**: Whether a *specific behavior* of the framework
or the agent works as intended. Synthetic tasks isolate one variable
at a time, which real-world tasks can't.

---

### Layer 5: Real-world replay (10–100 tasks)

**Purpose**: "Did our improvement also help on the actual distribution
of user queries?"

**Characteristics**:
- Sourced from real user logs (if you have them)
- Human-labeled outcomes
- Privacy and license issues are real
- Subject to selection bias (you only log queries that get sent)
- The most representative test data, **and** the hardest to obtain

**Example**: A chatbot product team that sampled 100 production
queries, paired them with the agent's actual responses, and had
humans rate the responses for quality.

**Source**: Your own production logs. **Only available if you have
a deployed product.** Can't be borrowed from anyone else.

**What caliper provides**:
- A trace-to-Sample converter that takes JSON logs and produces
  caliper Samples
- Privacy-aware metadata fields
- Tools for managing labeled subsets
- **Cannot** provide the data itself or do the labeling for you

**What you learn**: Whether your benchmarks are representative of
real usage. This is the only layer that catches "we optimized for
the benchmark but real users do something else."

---

## How the layers compose

You don't run all layers all the time. The discipline is:

| When | Layer | Why |
|---|---|---|
| Every commit | Layer 1 (smoke) | Catch obvious breakage |
| Every PR / change | Layer 2 (baseline) | Detect real improvements/regressions |
| Weekly / nightly | Layer 3 (coverage) | Confirm generalization |
| When testing a specific feature | Layer 4 (synthetic) | Isolate one variable |
| Before any major release | Layer 5 (real-world) | Sanity check against reality |

**For browser-pilot today**: Layer 1 (4 heroku tasks) + Layer 2 (12
WebVoyager tasks) is what we have. Layers 3, 4, 5 are planned for
later phases.

---

## The 8 design principles for test sets

Beyond the layered strategy, these are principles that should hold
across all layers. They come from things we wish we'd known at the
start of browser-pilot iteration.

### 1. Test set as code, not as data

Test sets must be:
- **Committed to git** with version tags
- **Have changelogs** that explain why tasks were added/removed
- **Reviewed in PRs** the same way code is reviewed
- **Treated as public API** of the consumer project

Anti-pattern: a `tasks.csv` file that gets edited in place without
git history. You'll never know when a baseline number changed because
the test set drifted vs because the agent changed.

### 2. Every task has metadata

At minimum:
- `bucket` — which task category (lookup / search / compare / ...)
- `source` — where the task came from (WebVoyager, hand-written, ...)
- `is_time_sensitive` — does the answer change over time?
- `license` — under what license can you use this task?
- `last_validated` — date the reference was last confirmed correct
- `stability_score` — auto-computed: pass rate over the last N runs

Metadata enables bucket reports, license audits, and freshness checks.
Anti-pattern: a task that's just (input, target) with no context.

### 3. Stability score per task

Run each task N=10 once at curation time. Record the variance. Tasks
with CV > 30% are **flagged as unstable** and **excluded from the
stable baseline** (Layer 2). They can still live in Layer 3 (broad
coverage) where individual variance is averaged out.

This is the "test the test set" principle: caliper evaluates its own
test sets by measuring their reproducibility.

### 4. Reference freshness annotation

Every reference answer should be tagged with:
- The date it was last validated
- A "decay rate" estimate (how often does the answer change?)
- An `expects_staleness` flag for time-sensitive tasks

The judge for time-sensitive tasks automatically applies the
stale-reference tolerance rule (see
`reference/inherited-artifacts.md` §1).

A reference older than 6 months on a time-sensitive task should
**fail-fast** in the loader unless explicitly marked as still valid.

### 5. License hygiene

Each task source has a license. Track it as task metadata and surface
it in reports:

```
This benchmark run uses tasks from:
  WebVoyager (academic license, non-commercial)
  AssistantBench (Apache 2.0)
  Internal smoke tests (proprietary)

Use of WebVoyager tasks in commercial deployment may require permission.
```

This isn't legal advice — but a flag prevents accidentally using
academic-only data in a product without realizing.

### 6. Test the test set ("dogfood the data")

Use a known-good agent to validate the test set itself. If a new task
fails on **every** good agent (Sonnet, Opus, GPT-5), the task is
suspect, not the agent. Either:
- The task is unsolvable as written
- The reference is wrong
- The task is too ambiguous

This catches author errors before they pollute the baseline.

The chatbot maxTurns scenario takes this further: it uses caliper to
test whether the LimitStrategy implementations are themselves correct
(see [chatbot-maxturns.md](chatbot-maxturns.md)).

### 7. LLM-generated variants for robustness testing

Golden tasks stay fixed. But for robustness testing, use an LLM to
generate paraphrased variants:

```
Original: "Find a vegetarian lasagna recipe with >100 reviews and 4.5+ stars"
Variant 1: "Show me vegetarian lasagna recipes that are well-reviewed (100+ reviews, 4.5 stars or better)"
Variant 2: "I need a vegetarian lasagna. Must be highly rated — at least 4.5 stars and 100+ reviews."
Variant 3: "Help me find a popular vegetarian lasagna recipe (4.5+ rating, plenty of reviews)"
...
```

Run all variants. If pass rate varies more than 20% across variants,
your agent is sensitive to phrasing — that's a real finding.

This is a form of Layer 4 (synthetic) — the variants don't replace
the originals, they augment.

### 8. Don't chase coverage, chase orthogonality

A benchmark with 1000 nearly-identical tasks tests one thing 1000
times. A benchmark with 12 distinct task patterns tests 12 things.

**Aim for orthogonality, not volume.** When adding tasks, ask: "What
failure mode does this expose that the existing tasks don't?" If
the answer is "none", don't add it.

This is why browser-pilot's v8 baseline has 12 tasks across 4 buckets
rather than 100 tasks dominated by lookups.

---

## Public benchmark catalog

Curated list of benchmarks, with their realistic strengths and
weaknesses. Updated occasionally; check the source for current state.

### Browser / web tasks

| Benchmark | Tasks | Strengths | Weaknesses | License |
|---|---|---|---|---|
| **WebVoyager** | 643 | Real sites, diverse domains | Staleness, references from 2023 | Academic |
| **AssistantBench** | 214 | Verified short answers, very clean | Smaller scale | Apache 2.0 |
| **Mind2Web** | 2350 | Action prediction granularity | Action-level not task-level | Research |
| **Online-Mind2Web** | 300 | Live website variant of Mind2Web | Smaller, similar staleness issues | Research |
| **WebArena** | 800+ | Self-hosted, no staleness | Requires Docker setup | Apache 2.0 |
| **VisualWebArena** | ~1000 | Visual understanding tasks | Complex setup | Apache 2.0 |
| **GAIA** | 466 | Exact-match references | Leans toward research questions | Apache 2.0 |
| **BrowseComp** (OpenAI) | ~1200 | Recent, less contaminated | Newer, less validated | OpenAI terms |
| **Web Bench** (Skyvern) | 2454 | Largest live-site benchmark | Maintenance? | Check source |

### Computer / desktop use

| Benchmark | Tasks | Notes |
|---|---|---|
| **macOSWorld** | 202 tasks, 30 apps | Used by computer-pilot |
| **OSWorld** | 369 tasks, multiple OSes | Heavier setup |
| **AndroidWorld** | Mobile equivalent | For mobile agents |
| **ScreenSpot** | UI element grounding | For visual grounding accuracy |

### Coding agents

| Benchmark | Tasks | Notes |
|---|---|---|
| **SWE-bench Verified** | 500 | Real GitHub issues; **known contamination** |
| **HumanEval** | 164 | Classic; very contaminated by now |
| **MBPP** | 974 | Classic; same |
| **BigCodeBench** | 1140 | More recent, less contamination |
| **LiveCodeBench** | Continuously updated | Designed to resist contamination |
| **Terminal-Bench** | ~80 | Used by pi-mono |

### Tool / function calling

| Benchmark | Tasks | Notes |
|---|---|---|
| **BFCL** (Berkeley Function Calling Leaderboard) | ~2000 | Granular function call accuracy |
| **ToolBench** | Many | Multi-tool composition |
| **API-Bank** | ~1000 | API tool calling |

### General agent / reasoning

| Benchmark | Tasks | Notes |
|---|---|---|
| **GAIA** | 466 | Cross-domain assistant tasks |
| **AgentBench** | 8 environments | Multi-environment harness |
| **GSM8K** | 1000+ | Math word problems (single-turn) |
| **MATH** | 12500 | Higher-difficulty math |

---

## How this maps to caliper components

For each layer there's a corresponding caliper module that handles it:

| Layer | Caliper module | Status |
|---|---|---|
| 1: Smoke | `caliper.smoke` (Phase 4) | Stub |
| 2: Stable baseline | `caliper.datasets.<benchmark>_loader` | Phase 1 (WebVoyager) |
| 3: Broad coverage | Same loaders, no curation filter | Phase 2 |
| 4: Synthetic/mock | `caliper.mocks` + `caliper.solvers.mock_tool_solver` | Phase 3 (chatbot scenario) |
| 5: Real-world | `caliper.io.trace_loader` | Phase 4+ |

The roadmap (`docs/roadmap.md`) covers when each module lands.

---

## Open questions

These are unresolved questions that will need answers as caliper
matures:

1. **Should caliper bundle task data, or only loaders?**
   - Bundling: easier for users, but legal exposure for licensed data
   - Loaders only: cleaner, but users have to download data themselves
   - Current preference: loaders only, with documentation pointing to
     official sources

2. **What's the right cadence for re-validating curated tasks?**
   - Monthly seems too frequent (cost)
   - Yearly seems too infrequent (drift)
   - Quarterly with on-demand re-validation when tasks fail unusually?

3. **How does caliper handle benchmark contamination?**
   - SWE-bench has known training contamination
   - Caliper should at least *flag* this in task metadata
   - Probably can't *fix* it — but documenting it is a start

4. **Should there be a "task quality score" metric?**
   - Combines stability, freshness, distinguishing power
   - Could rank tasks by how much information they contribute
   - Risk: turns into yet another metric to optimize

5. **What's the right format for cross-benchmark task definitions?**
   - WebVoyager uses JSONL with specific fields
   - GAIA uses different fields
   - Inspect AI's `Sample` is a unifying format but loses some metadata
   - Caliper's loaders should preserve source-specific metadata in `Sample.metadata`

6. **How to handle tasks that span multiple Sample structures?**
   - A task that's "research X across these 3 sources" is naturally
     one logical unit
   - Inspect AI Samples are atomic
   - Possibly a `multi_sample_task` wrapper for these

---

## Recommendations for the immediate roadmap

For caliper Phase 1 (current), the test set strategy is:

1. **Layer 1**: Use the 4 heroku tasks (already exist in browser-pilot)
2. **Layer 2**: Use the 12 v8 curated tasks (documented in
   `reference/curated-tasks.md`)
3. **Skip Layers 3, 4, 5 for now** — they require Phase 2+ work

For Phase 2, add:
- Layer 3: full WebVoyager loader (`caliper.datasets.webvoyager`)
- Layer 4 stub: enough to support chatbot maxTurns scenario (see
  `chatbot-maxturns.md`)

For Phase 3:
- Full Layer 4 with the chatbot scenario
- Begin Layer 5 design (no implementation yet — needs a real
  consumer with production data)

---

## A note on the "test set as the bottleneck"

The thesis of caliper is "evidence-based iteration is hard because
**measurement** is hard". This document expands that thesis: **test
sets are also part of measurement**, and they have their own set of
hard problems.

The framework can't solve the test set problem outright. What it can
do is:
- Make the layered strategy easy to follow
- Ship loaders for the major public benchmarks
- Ship mocks for synthetic scenarios
- Track per-task stability and freshness as first-class metadata
- Surface license / contamination concerns in reports

The human work — curating which tasks to trust, labeling production
traces, deciding what failure modes matter — **stays with the team
using caliper**. We make the work cheaper, not zero.
