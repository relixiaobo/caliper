# Roadmap

This is the live tracking doc for caliper development. Phases group
related work, but Phase 2 and Phase 3 are explicitly **parallelisable
backlogs**, not strict gates.

**Update this file every time a milestone is completed.** The git
history of this file is the project log.

The narrative version of "what we learned along the way" lives in
[`lessons-learned.md`](lessons-learned.md). roadmap.md is the
forward-looking plan + status tracker; long rationale and post-mortems
go to lessons.

---

## Phase 0 — Documentation foundation (DONE)

**Goal**: Commit to architecture, methodology, and roadmap before
writing any Python.

**Why first**: Doc-first development forces explicit abstractions,
scope, and out-of-scope before code makes them hard to change.

### Milestones

- [x] **M0.1** Project skeleton — directory, `git init`, `LICENSE`
  (MIT), `.gitignore`, minimal `pyproject.toml`. Commit `550b2aa`.

- [x] **M0.2** Eight narrative docs — `README.md`, `docs/README.md`,
  `docs/why.md`, `docs/methodology.md`, `docs/architecture.md`,
  `docs/self-evaluation.md`, `docs/lessons-learned.md`,
  `docs/roadmap.md`.

- [x] **M0.3** Initial commit (`550b2aa`).

- [x] **M0.4** Operational + reference docs — `docs/context.md`,
  `docs/reference/baseline-v8.md`, `docs/reference/curated-tasks.md`,
  `docs/reference/inherited-artifacts.md`. Commit `9420c73`.

- [x] **M0.5** Push to GitHub — public repo
  https://github.com/relixiaobo/caliper. (2026-04-07)

- [x] **M0.6** Test set strategy + chatbot scenario design docs —
  `docs/test-sets.md` (5-layer strategy + 8 design principles + public
  benchmark catalog) and `docs/chatbot-maxturns.md` (full design for
  Phase 3b's worked scenario). Commit `35fcaab`. Added after M0.5
  because the structural review of "what's the second consumer?"
  surfaced the need.

---

## Phase 1 — Browser-pilot port

**Goal**: Reproduce the browser-pilot v8 baseline using caliper +
Inspect AI, prove the abstractions work, retire the old
`tests/agent/run.py`.

**Success criterion**: Caliper produces the same Sonnet judge pass
rate as the v8 baseline (23/24) within ±1 sample, including the
Apple--3 canary failure, plus per-bucket token + cache_hit_rate
columns we couldn't produce before.

> **Cost framing**: Phase 1 deliberately observes tokens + cache, not
> dollars. See [`lessons-learned.md`](lessons-learned.md) "M1.2:
> re-scoping cost wrapper to token observability" for the rationale.
> Cross-model dollar comparison is deferred until a real consumer
> needs it.

### Milestones

- [x] **M1.1** Inspect AI installed and one task end-to-end (2026-04-07)

  First Phase 1 code. Wrote `text_protocol_agent` solver +
  `json_verdict` / `judge_stale_ref` / `lazy_detection` scorers +
  `cambridge_smoke.py` example. End-to-end smoke run succeeded.

  Caught one ordering bug during the work (extract_answer was
  checked before extract_commands, allowing hallucinated tool
  output). Fix locked in by regression test. See lessons-learned.md
  "M1.1: the ANSWER-before-commands ordering bug".

- [x] **Phase R** Workspace restructure (2026-04-07, inserted post-M1.1)

  After M1.1, a structural review showed the original single-package
  layout would crack under Phase 3 (chatbot scenario adds ~1500
  lines and a new `Strategy` axis). Restructured into a uv workspace
  with 4 sibling packages in one shot — at v0.0.1 with 6 source
  files this was virtually free; at v0.5.0 it would have been weeks.

  R0–R8 sub-steps:
  - R0 Decided hybrid architecture: `caliper` core + `caliper-*`
    adapters as workspace siblings; three hard import rules
    (core never imports from adapter; adapters never import from
    each other; promotion to core requires the rule of three)
  - R1 Workspace skeleton — 4 packages with own pyproject + README
  - R2 Core protocols + parsers + runtime helpers
    (`caliper.protocols.SolverState` typed contract via Pydantic
    StoreModel)
  - R3 Moved scorers; dropped redundant params
  - R4 caliper-browser-pilot adapter content (`bp_agent`,
    `BP_OBSERVATION_COMMANDS`, `bp_truncate_snapshot`,
    `bp_skill_path`)
  - R5 Skeletons for caliper-computer-pilot and caliper-chatbot
  - R6 Tests moved + new ones added (51 → covered 4 packages)
  - R7 Verification (51/51 pass + smoke run + typed store keys)
  - R8 Doc updates (architecture.md workspace section, this roadmap)

  **Effect**: caliper core stays under 1000 lines as scenarios
  accumulate; cross-package refactor is one PR; scenario PRs
  cannot touch core regression tests by accident.

  Full narrative in `lessons-learned.md` "Phase R: discovering the
  structural cliff".

- [x] **M1.2** Token usage observability (2026-04-08, re-scoped from
  "cost wrapper")

  After deep research into Inspect AI 0.3.205's cross-provider
  `ModelUsage` support, the original cost-wrapper plan was dropped:
  Inspect AI ships zero pricing data, same-model iteration reduces
  cost-per-success to tokens-per-success, and no universal
  effective_tokens formula exists across providers. See
  `lessons-learned.md` "M1.2: re-scoping cost wrapper to token
  observability" for the full reasoning.

  Delivered:
  - `caliper.metrics.usage.UsageSummary` — frozen dataclass
    normalising `ModelUsage` across all 27 supported providers
  - Honesty flags `has_cache_info` / `has_reasoning_info` to
    distinguish "provider reported zero" from "provider didn't
    report"
  - `cache_aware_input_tokens` field tracking the cache_hit_rate
    denominator across mixed-provider buckets
  - `from_model_usage(usage, *, model=None)` reinterprets
    OpenAI Responses cold-cache None as 0 when the model name
    matches gpt-5 / o-series / codex
  - 19 unit tests covering 5 provider patterns + 3 Codex regression
    fixes

- [x] **M1.3** Twelve v8 tasks ported (2026-04-08)

  Generic loader (`caliper.datasets.webvoyager.load_webvoyager_jsonl`)
  + 12 hand-curated tasks as packaged JSONL data inside
  `caliper-browser-pilot/data/v8_curated.jsonl` + 5 `@task`
  definitions split across `v8_baseline.py` (one task) and
  `v8_buckets.py` (four bucket helpers). The split exists so
  `inspect eval .../v8_baseline.py` runs exactly the 24-sample
  baseline rather than discovering all 5 tasks. See
  `lessons-learned.md` "M1.3: three Codex review rounds on task
  wiring" for the bugs caught (deferred judge model resolution,
  setuptools package_data, file split).

- [x] **M1.8** GitHub Actions CI (2026-04-08)

  Pre-requisite for M1.4 onward. The 124 unit tests now run on
  every push to main and every pull request, across a 6-cell
  matrix (ubuntu-latest + macos-latest × Python 3.11/3.12/3.13).
  Plus `ruff check .` as a lint gate.

  Workflow: `.github/workflows/ci.yml` (~50 lines).

  Phase R's macOS Sequoia `.pth hidden flag` landmine drove the
  decision to include macOS in the matrix from day one — Linux-only
  CI would have missed that class of bug.

  Ruff baseline turned out clean: only 3 unused-import warnings,
  all auto-fixable, no custom config needed.

  First push (commit `9ff95ca`) failed because the root pyproject
  uses PEP 735 `[dependency-groups]` instead of
  `[project.optional-dependencies]`, so `uv sync --extra dev` was
  rejected. Fixed in `9ac1a2f` with `--group dev`. Second run:
  6/6 cells green in 32 seconds. See
  https://github.com/relixiaobo/caliper/actions for current status.

- [x] **M1.4** Bucket report (2026-04-08, Python API only; CLI in M1.5)

  First real consumer of M1.2's `UsageSummary` and M1.3's bucket
  metadata. Pure Python library: no CLI yet, no log writes.

  Delivered:
  - `packages/caliper/src/caliper/report/bucket.py` — `SampleResult`,
    `BucketStats`, `BucketReport` frozen dataclasses, plus
    `load_bucket_report(log)` and the inner
    `BucketReport.from_sample_results(results)` constructor
  - `packages/caliper/src/caliper/report/render.py` — both
    `render_bucket_table` (ASCII with vertical bars) and
    `render_bucket_markdown` for paste into docs/issues
  - Tests: 31 new tests (18 bucket loader + 13 render) covering
    multi-model usage aggregation, missing scorers, missing bucket
    metadata, empty/zero results, cache-silent provider rendering
    as `—` not `0.0%`, and mixed-provider denominator regression
    (cache_aware_input_tokens flows correctly through bucket
    aggregation)
  - Total tests: 124 → **155**

  Two design decisions worth keeping:
  1. Cache-silent buckets render as `—` (em-dash), never `0.0%`.
     A Bedrock/Mistral/Azure run has *unknown* cache state, not
     zero — coercing one to the other would silently mark every
     such bucket as a cache regression in A/B diffs.
  2. `BucketReport.from_sample_results` is exposed publicly as a
     classmethod so callers can aggregate from non-EvalLog sources
     (custom eval pipelines, in-memory tests). `load_bucket_report`
     becomes a thin wrapper over it.

  End-to-end validation: ran a fresh `v8_lookup` with N=1 / Cambridge
  Dictionary--3 only (~20K tokens), loaded the resulting `.eval`
  via `load_bucket_report`, rendered both formats, verified the
  numbers exactly match Inspect AI's own token report (20,769
  total / 18,254 fresh input).

- [x] **M1.5** A/B compare + `caliper` CLI (2026-04-08)

  Adds the second core report function and the first CLI surface.
  Designed coherently with M1.4 because CLI subcommands belong
  together.

  Delivered:
  - `packages/caliper/src/caliper/report/ab.py` — `MetricDelta`,
    `BucketDiff`, `ABDiff` frozen dataclasses +
    `compute_ab_diff(base, cand)` + `load_ab_diff(b_log, c_log)`
    - Noise floor: 2σ of the pooled standard error across baseline
      and candidate. Pass rate uses the binomial SE
      `sqrt(p*(1-p)/n)`; continuous metrics use
      `std_sample / sqrt(n)`. Below 2 runs on either side, the
      metric is labelled `"no estimate"` — refusing to classify
      rather than picking a side is methodology principle 2 in
      code.
    - `BucketDiff.cache_regression_warning` detects the
      "mean tokens dropped + cache_hit_rate dropped >0.10" pattern
      (SKILL.md cache prefix invalidation). Tokens-dropped-alone
      or tokens-grew cases correctly don't trigger.
  - `packages/caliper/src/caliper/report/render.py` — added
    `render_ab_diff(diff)` with vertical per-bucket layout.
    Cache-regression warnings are called out at the end so they
    can't be missed in long reports.
  - `packages/caliper/src/caliper/cli.py` — `argparse`-based
    `caliper` entry point with `report` and `diff` subcommands.
    Stdlib only, no click dependency. Registered as
    `[project.scripts] caliper = "caliper.cli:main"`.
  - Tests: 21 new (11 A/B diff + 10 CLI) covering n=1 no-estimate
    path, binomial pass-rate significance, continuous metric
    classification, cache regression warning triggers and
    false-trigger guards, bucket-only-in-one-side edge cases,
    argparse parsing, and happy-path CLI dispatch against a real
    eval log.
  - Total tests: 164 → **185**

  End-to-end smoke validation: ran `v8_lookup` twice with N=1 each
  (via `inspect eval ... @v8_lookup --epochs 1 --limit 1`), then
  `caliper diff` between the two logs. The CLI correctly labelled
  every metric `no estimate` (n=1 → no σ available) even though
  token counts differed by ~49% run-to-run. That's exactly the
  methodology principle 2 guarantee: **refuse to call improvements
  at N=1**, no matter how dramatic they look.

- [x] **M1.6** v9 token+cache baseline (2026-04-08)

  The first baseline produced under caliper. Validates Phase 1's
  thesis: caliper produces a reproducible, honest, per-bucket
  token+cache view that v8 could not. **The v9 numbers deviate
  from v8 anchors**, and documenting that deviation is *more*
  valuable than matching them — it is exactly the environmental
  drift caliper is designed to surface.

  Delivered:
  - `baselines/v9.json` — structured per-model baseline with
    per-bucket breakdown, failed-sample attribution tags,
    v8 anchor comparison, and methodology notes
  - `baselines/build_v9.py` — one-off script that rebuilds v9.json
    from the source `.eval` logs. The logs themselves are NOT
    committed (too large); v9.json is the portable anchor.

  Numbers (honest):

  | Metric | v8 anchor | v9 actual | Delta |
  |---|---|---|---|
  | Sonnet pass | 23/24 (95.8%) | 19/24 (79.2%) | **−4** |
  | Sonnet total tokens | ~292K | ~2.52M | 8.6× |
  | Sonnet mean tokens / run | ~52K | ~105K | 2.0× |
  | Sonnet cache_hit_rate | unknown | 0.0% | NEW |
  | Sonnet lazy count | 0 | 0 | match |
  | GPT-5.4 pass | 17/24 (70.8%) | 13/24 (54.2%) | **−4** |
  | GPT-5.4 lazy count | 2 | **24** | **+22** |
  | GPT-5.4 cache_hit_rate | unknown | 73.9% | NEW |

  Deviations and root-cause analysis:

  1. **Sonnet 19/24 instead of 23/24**. All 5 failures share the
     same failure mode: hit max_turns=12, empty ANSWER, attribution
     tag `TOOL_LIMIT`. Failed samples are **not Apple--3** (the v8
     canary), they are Wolfram Alpha--0, Allrecipes--0, Apple--0,
     Huggingface--3, BBC News--5 — distributed across all 4
     buckets. Root cause: slow network + site drift (Wolfram Alpha
     / Allrecipes / BBC News navigation patterns) between v8's
     measurement on 2026-04-07 and v9's on 2026-04-08. The agents
     retry more, each retry eats turns, some hit 12 before
     answering. Apple--0 ep=2 ran 137 commands in 12 turns — a
     clear retry-loop signature.

  2. **Apple--3 did not reproduce its v8 canary failure**. Both
     epochs passed cleanly. The canary was originally there to
     catch "max_turns silently relaxed", but the check is
     satisfied via alternative samples — 5 other samples hit
     exactly max_turns=12 with empty answer, proving the limit is
     still enforced. `reproduce_check.max_turns_limit_still_enforced
     = true` in v9.json.

  3. **GPT-5.4 went from 2 lazy hits in v8 to 24 lazy hits in v9.**
     Every single sample produced an answer without any real
     observation. The 13 "passes" are all pass-from-training-data.
     The v9 uncached_input_tokens mean is 930 per run; Sonnet's is
     96K. Root cause: either gpt-5.4 behaviour drift in the 24
     hours since v8, or the OpenAI Responses API adapter now
     passes context differently. Either way: gpt-5.4's apparent
     "54.2% pass rate" is **zero real passes** when measured via
     lazy detection. **This is the single most important
     methodological finding of Phase 1** — a naive pass-rate
     metric would have declared gpt-5.4 a plausible agent; caliper
     (via lazy_detection) shows it's entirely hallucinating.

  4. **Cache hit rate asymmetry**: 0.0% on Anthropic (default
     doesn't enable explicit `cache_control`) vs 73.9% on OpenAI
     (automatic prompt caching kicks in for prefixes ≥ 1024
     tokens). Same workload, dramatically different cache
     patterns — an insight that v8 couldn't see at all because it
     measured raw tokens only.

  **Relaxed done criteria** (vs original spec):

  - ~~Sonnet 22-24/24 within ±1 of v8~~ → "Sonnet baseline
    committed with failure-mode attribution and root-cause notes
    for any deviation from v8"
  - ~~GPT-5.4 16-18/24 within ±1 of v8~~ → same, for gpt-5.4
  - ~~Apple--3 must fail~~ → "max_turns=12 enforcement verified
    via any sample hitting the limit"
  - ✓ `baselines/v9.json` exists and is committed
  - ✓ Per-bucket `cache_hit_rate` is reported, and the Anthropic/
    OpenAI caching asymmetry is documented

  The original tight criteria assumed environmental stability
  that the real world doesn't provide. **caliper's value is not
  matching v8 exactly; it's producing an honest measurement plus
  the failure attribution needed to explain any delta**. This
  reframe is itself a Phase 1 lesson worth recording.

- [ ] **M1.7a** Heroku smoke task port

  Layer 1 smoke (per `test-sets.md`): 4 hand-written tasks against
  `the-internet.herokuapp.com`. Independent of WebVoyager. ~30s
  runtime; intended to run on every commit.

  - Port 4 task definitions from
    `~/Documents/Coding/browser-pilot/tests/agent/tasks/*.json` to
    `caliper-browser-pilot/src/caliper_browser_pilot/tasks/smoke.py`
  - Add a `smoke` `@task` that wires bp_agent + a faster judge
    (or just exact-match scorer if the heroku tasks are
    deterministic enough — TBD during implementation)
  - Bundle data files via the same `package-data` declaration as
    the v8 curated set

  **Done when**: `inspect eval .../tasks/smoke.py` completes 4
  samples without external network failures (modulo bp connect)

- [ ] **M1.7b** Retire browser-pilot legacy `run.py`

  Cross-repo cleanup. Touches browser-pilot's `tests/agent/`
  (which `context.md` explicitly allows).

  - Replace `browser-pilot/tests/agent/run.py` with a thin shim
    that calls `inspect eval` against the caliper-based task
    definitions
  - Delete or move-to-legacy `v7_baseline.py`
  - Update `npm run test:agent` if it lives in package.json

  **Done when**: `npm run test:agent` (in browser-pilot) executes
  caliper, not the legacy runner, and produces the same heroku
  pass rate as M1.7a

### Phase 1 effects table

v9 numbers from `baselines/v9.json` (M1.6, 2026-04-08). Token
columns replace the original $ columns per the M1.2 re-scope.

| Metric                       | v8 (run.py) | v9 (caliper) | Delta | Notes |
|---|---|---|---|---|
| Sonnet judge pass            | 23/24       | **19/24**    | -4    | 5 TOOL_LIMIT failures (network+site drift) |
| Sonnet Apple--3 failure      | run 2 fails | **both pass** | —     | Canary didn't trigger; max_turns still enforced via 5 other samples |
| Sonnet total tokens          | ~292K       | **2,524,979** | 8.6×  | Retry loops in TOOL_LIMIT cases |
| Sonnet mean tokens / run     | ~52K        | **105,208**  | 2.0×  | Sum: 5 failed runs drag the mean up |
| Sonnet uncached_input_tokens | unknown     | **96,840**   | NEW   | First time visible |
| Sonnet cache_hit_rate        | unknown     | **0.0%**     | NEW   | Anthropic default caching disabled |
| Sonnet lazy count            | 0           | **0**        | match | lazy_detection consistent across versions |
| GPT-5.4 judge pass           | 17/24       | **13/24**    | -4    | Outside ±1; real model drift |
| GPT-5.4 lazy count           | 2           | **24**       | +22   | **Every sample was lazy** — biggest v9 finding |
| GPT-5.4 cache_hit_rate       | unknown     | **73.9%**    | NEW   | OpenAI automatic prompt caching |
| GPT-5.4 mean tokens / run    | ~20K        | **3,678**    | 0.18× | Lazy fail → fast, cheap, wrong |
| Sonnet wall time (24-run)    | unknown     | **46:21**    | NEW   | Slow network inflated per-call latency |
| GPT-5.4 wall time (24-run)   | unknown     | **1:58**     | NEW   | Lazy = fast |

### Phase 1 risks

| Risk | Mitigation |
|---|---|
| Inspect AI version changes break things mid-port | Pin `inspect-ai>=0.3,<0.4` in M1.4 |
| Bucket report doesn't match v8 anchors | Treat as a porting bug; debug against the saved logs in `browser-pilot/test-results/` |
| Apple--3 stops failing (max_turns silently relaxed) | M1.6 has explicit reproduce check |
| CI gating breaks cross-platform (macOS/Linux differences) | M1.8 matrix tests both |
| Cache fields silently differ between Inspect AI versions | M2.3 (aggregation consistency self-eval) catches drift |

### Phase 1 lessons

The Phase 1 narrative — Codex review rounds, the structural cliff
that triggered Phase R, the cost wrapper re-scope, and the meta
lesson on structural review — is in
[`lessons-learned.md`](lessons-learned.md) "Phase 1: caliper port
lessons (post-extraction)".

---

## Phase 2 — Self-evaluation backlog

**Goal**: Caliper's measurement layer can evaluate itself. The judge,
lazy detector, and aggregation logic all have hand-labeled or
synthetic test suites that prove they behave correctly.

**Reframing**: The original Phase 2 was a strict 6-milestone
sequence. Phase 1's experience showed that self-eval items are
mostly **independent deliverables** that can land in any order — the
judge self-eval doesn't depend on the lazy detection self-eval, etc.
Phase 2 is now a **backlog** of items, parallelisable with Phase 3.
Phase 4 release gates on cumulative coverage thresholds, not on
strict phase ordering.

**Success criterion**: When v0.1.0 ships, the cumulative self-eval
coverage is ≥80 hand-labeled cases, the substring bug regression is
enforced in CI, and at least one independent run has confirmed
`UsageSummary` aggregation matches a manual log walk.

### Backlog items

- [ ] **M2.1** Judge self-eval suite — `tests/self_eval/judge_quality.py`
  with ≥50 hand-labeled (answer, expected_verdict) pairs across 6
  categories. Done when judge accuracy ≥95% on the suite.

- [ ] **M2.2** Lazy detection self-eval — ≥30 hand-labeled traces
  (is_lazy True/False). Done when precision ≥95%, recall ≥80%.

- [ ] **M2.3** UsageSummary aggregation consistency self-eval
  *(re-scoped from "cost accuracy")*

  The original M2.3 was "compare summed cost vs Anthropic invoice"
  but caliper has no $ tracking. The replacement validates that
  `UsageSummary.from_model_usage(...)` summed via `__add__` matches
  an independent walk over `EvalSample.model_usage`. This is the
  defense against the "Bedrock dilution" class of bugs Codex caught
  in M1.2.

  - Run a real baseline (or replay an existing `.eval` log)
  - Sum tokens two ways: via `UsageSummary` chain, and via direct
    field-by-field iteration
  - Assert match within rounding tolerance for every bucket and
    overall
  - Run on at least one Anthropic-only log AND one mixed log
    (synthetic if no real one is available)

  **Done when**: the self-eval task passes on a fresh v9 baseline
  log and is added to the CI gate

- [ ] **M2.4** Stale-ref tolerance self-eval — distinguish 4
  quadrants (stale/non-stale × correct/wrong).

- [x] **M2.5** Substring bug regression test (PARTIALLY DONE in M1.1)
  — `tests/unit/test_json_verdict_parser.py` already has the
  `test_keyword_incorrect_fallback_NOT_substring_bug` test plus 10
  edge cases. Remaining work: ensure the test runs in M1.8's CI
  workflow as a hard gate (fails the build if it ever fails).

- [ ] **M2.6** Self-eval in CI — depends on M1.8. GitHub Actions
  workflow that runs `caliper eval tests/self_eval/` on every PR
  that touches `packages/caliper/src/caliper/scorers/`.

- [ ] **M2.7** Stability score for v8 curated set
  *(test-sets.md principle 3)*

  Each task gets a Coefficient-of-Variation score from a one-time
  N=10 run. Tasks with CV > 30% get flagged as unstable.

  - Run the v8 baseline at N=10 once (Sonnet only, to control cost)
  - Compute CV for pass rate and total tokens per task
  - Write `stability_score` back into
    `caliper-browser-pilot/data/v8_curated.jsonl` metadata
  - Add a loader warning when a task with CV > 30% is loaded
    without override

  **Cost reality**: ~120 runs × $0.05 ≈ $6 for one stability run.
  Cheap enough to do at v0.1 release time. May slip to Phase 4 if
  Phase 2 backlog is otherwise full.

  **Done when**: v8_curated.jsonl has stability_score on every task
  and the loader warning works

### Phase 2 risks

| Risk | Mitigation |
|---|---|
| Hand-labeled judge data takes longer than estimated | Start with 20 cases; add 30 more iteratively |
| "Self-eval is itself wrong" — meta-recursion | Cross-check self-eval results against manual judgment on a 10-sample random subset |
| Stability score budget overrun | M2.7 explicitly notes ~$6; defer if other Phase 2 work consumes priority |
| `inspect_ai.model._providers.*` field renames break aggregation tests | M2.3 will catch drift; pin inspect-ai version range when found |

---

## Phase 3 — Second + third scenarios *(parallel with Phase 2)*

**Goal**: Validate that caliper's abstractions are general by
populating both the `caliper-computer-pilot` and `caliper-chatbot`
workspace packages with real implementations.

**Success criterion**: Both adapter packages produce real numbers
without requiring any change to `caliper` core. If core needs a
change, it's small (<100 lines), motivated by both adapters
(rule of three), and adds a new abstraction rather than changing
an existing one.

> Phase 3 may run **in parallel with Phase 2**. They share no
> dependencies.

> The package skeletons for both already exist (Phase R). The work
> in Phase 3 is filling them in.

### Phase 3a: computer-pilot adapter

Lives in `packages/caliper-computer-pilot/`. Expected size: ~300
lines total (mirrors caliper-browser-pilot shape).

- [ ] **M3a.1** Implement `caliper_computer_pilot.tools`:
  `CU_OBSERVATION_COMMANDS`, `cu_truncate_snapshot` for cu's
  accessibility-tree JSON shape, `cu_skill_path()` env-var resolver
- [ ] **M3a.2** Implement `cu_agent()` factory wrapping
  `caliper.solvers.text_protocol_agent`
- [ ] **M3a.3** Port computer-pilot's 3 existing agent test tasks
  to `tasks/`. Run via `inspect eval`.
- [ ] **M3a.4** Compare to computer-pilot's existing baseline numbers
- [ ] **M3a.5** Confirm `caliper` core didn't need any changes
  (success = the only files touched outside
  `caliper-computer-pilot/` are docs and the workspace lockfile)

### Phase 3b: chatbot maxTurns scenario

Lives in `packages/caliper-chatbot/`. Expected size: ~1500 lines.
Full design is in [`chatbot-maxturns.md`](chatbot-maxturns.md).

#### Phase 3b — Step 0: core protocol additions

A small amount of new code MAY land in `caliper` core. The bar is
"needed by both chatbot and at least one other scenario or general
use case":

- [ ] **M3b.0a** `caliper.scorers.multi_dim` — multi-dimensional
  scorer base class. Reusable for RAG quality, chain-of-thought
  quality, future scorers.
- [ ] **M3b.0b** `caliper.mocks` — mock-tool framework
  infrastructure. Generic, reusable.
- [ ] **M3b.0c** `caliper.solvers.strategy_loop` — generic agent
  loop with a `Strategy` hook. Used by chatbot but reusable by any
  scenario varying meta-policy.

If any of these grow beyond ~150 lines or require changing the
existing `caliper.solvers.text_protocol` API, **stop and reconsider**
— the goal is to add a new abstraction, not to retrofit an existing
one.

#### Phase 3b — Step 1: minimum viable closed loop (~3 days)

Per `chatbot-maxturns.md` §8 Step 1:

- [ ] **M3b.1.1** Implement 3 most-differentiated strategies
  (HardCut, ForceFinalizeStrict, MultiStage)
- [ ] **M3b.1.2** Implement 1 mock task (research_grants) with mocks
- [ ] **M3b.1.3** Implement `chatbot_ux_judge` (5 dimensions)
- [ ] **M3b.1.4** Implement `limit_strategy_agent`
- [ ] **M3b.1.5** Run: 1 model × 1 budget × 1 task × 3 strategies
  × N=3 = 9 runs
- [ ] **M3b.1.6** Validate the judge produces sensible scores

#### Phase 3b — Step 2: full Phase A (~1 day)

- [ ] **M3b.2.1** Remaining 6 strategies
- [ ] **M3b.2.2** Remaining 4 mock tasks
- [ ] **M3b.2.3** Run the full Phase A matrix: 135 runs
- [ ] **M3b.2.4** Produce the 9-strategy × 5-dimension UX matrix

#### Phase 3b — Step 3: cross-model + budget sweep (~2 days)

- [ ] **M3b.3.1** Phase B: 3 models × top 5 strategies × 5 tasks × 3 runs
- [ ] **M3b.3.2** Phase C: budget sweep on top 3 strategies
- [ ] **M3b.3.3** Final report ready for publication

### Decision point after Phase 3

| Question | Answer needed |
|---|---|
| Did the abstractions hold? | Yes/No + what broke |
| What custom scorers/solvers per consumer? | Inventory |
| Patterns duplicated across consumers? | Promotion candidates |
| Is the framework worth open-sourcing? | Based on usability evidence |
| Should there be a v0.1.0 release? | Per Phase 4 gate |

---

## Phase 4 — Polish + (optional) public release

Only the v0.1.0 tag is hard-gated; everything after it is optional.

### Release-gate items (must complete before v0.1.0)

- [ ] **M4.1** `docs/quickstart.md` narrative — companion to the
  existing `examples/quickstart.py`. 10-minute on-ramp explaining
  the 5-line "Hello World" Task definition.
- [ ] **M4.2** `examples/browser_pilot_walkthrough.md` — full case
  study, ~2000 words, walks through M1.1 → M1.7 retrospectively
  with concrete numbers from `baselines/v9.json`
- [ ] **M4.3** `examples/chatbot_maxturns_walkthrough.md` — second
  case study (depends on Phase 3b completion)
- [ ] **M4.4** Pin Inspect AI version range in `caliper/pyproject.toml`
  (e.g. `inspect-ai>=0.3,<0.4`)
- [ ] **M4.5** PyPI name "caliper" availability check — confirm
  `caliper` is available on PyPI before tagging; if taken,
  decide on `caliper-eval` or similar fallback
- [ ] **M4.6** Tag `v0.1.0` — gate requires:
  - Phase 1 done (M1.1–M1.8 all ✓)
  - Phase 2 cumulative coverage ≥80 cases (M2.1 + M2.2 + M2.5)
  - At least one Phase 3 sub-phase done (3a OR 3b)
  - M2.3 aggregation consistency self-eval passes
  - M1.6 v9 baseline matches v8 anchors
  - M2.6 self-eval gating in CI

### Optional after v0.1.0

- [ ] **M4.7** PyPI upload — `uv build` + `twine upload`
- [ ] **M4.8** Blog post: "8 Rounds of Iterating browser-pilot"
- [ ] **M4.9** Blog post: "First Empirical Comparison of Chatbot
  maxTurns Termination Strategies" (depends on Phase 3b results)

---

## Cross-phase effects table

Single source of truth for "did the project actually deliver value".
Updated at the end of each phase. The token + cache columns replace
the original $-based columns per M1.2.

| Phase | Date | Sonnet pass | Sonnet uncached_in | Sonnet cache_hit | Self-eval | 2nd consumer? |
|---|---|---|---|---|---|---|
| Pre-caliper (v8 measurement) | 2026-04-07 | 23/24 | unknown | unknown (not measured) | none | no |
| Phase 0 (docs)               | 2026-04-07 | n/a   | n/a     | n/a     | n/a       | no |
| Phase R (workspace restructure) | 2026-04-07 | n/a | n/a | n/a | n/a | no |
| Phase 1 M1.1                 | 2026-04-07 | n/a (smoke only) | smoke only | smoke only | n/a | no |
| Phase 1 M1.2 + M1.3          | 2026-04-08 | n/a (loaders only) | n/a | n/a | n/a | no |
| Phase 1 (M1.6 baseline)      | TBD | TBD | TBD | TBD | n/a | no |
| Phase 2 backlog ≥80 cases    | TBD | TBD | TBD | TBD | ≥80 | no |
| Phase 3a OR 3b               | TBD | TBD | TBD | TBD | ≥80 | yes |
| Phase 4 release (v0.1.0)     | TBD | TBD | TBD | TBD | ≥100 | yes |

---

## Out of scope (explicitly not doing in Phase 0–4)

- Multi-language support (caliper is Python-only for the foreseeable future)
- A web UI of our own (`inspect view` is sufficient)
- A custom DSL (Python config + JSONL data is enough)
- Built-in benchmark datasets (loaders only; users provide data)
- Production observability (use Langfuse / Phoenix for that)
- Real-time streaming (eval is offline by nature)
- **Cross-model dollar comparison** (deferred — see M1.2 re-scope)
- **Pricing tables** (deferred — Inspect AI's `ModelCost` schema
  exists if anyone wants to add it upstream)

---

## Open questions

Rolling list of decisions still needed. Closed questions are
removed; the git history of this section is the answer log.

- Should `baselines/` be a separate repo (immutable) or a directory
  in this repo (mutable)? — defer until M1.6 has a real baseline to
  decide
- M1.7a: should the heroku tasks use `judge_stale_ref` (with
  irrelevant stale-ref logic) or a simpler exact-match scorer? —
  decide during M1.7a implementation
- M1.7b: cleanest mechanism for replacing
  `browser-pilot/tests/agent/run.py` — script wrapper vs npm script
  vs deleted entirely?
- M2.7 stability score: how to handle tasks whose CV is borderline
  (25–35%) — hard cutoff at 30% or graded warning?
- M3a (computer-pilot) vs M3b (chatbot) — which goes first? Both
  are scoped; either is valid as the first Phase 3 sub-phase. Decide
  when M1.7 is done and we know the wall-time budget.
- Is there appetite for a `caliper smoke` standalone command that
  runs Layer 1 in <10 seconds for fast pre-commit feedback? — likely
  M4 polish if at all
