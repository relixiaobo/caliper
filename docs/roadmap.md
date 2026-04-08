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

- [ ] **M1.4** Bucket report (Python API only; CLI in M1.5)

  First real consumer of M1.2's `UsageSummary` and M1.3's bucket
  metadata. Pure Python library — no CLI yet, no log writes.

  - `packages/caliper/src/caliper/report/bucket.py` (~200 lines):
    - `SampleResult` dataclass (sample_id / epoch / bucket /
      judge_passed / is_lazy / `UsageSummary`)
    - `BucketStats` dataclass (n_samples / n_runs / pass_count /
      lazy_count / `UsageSummary` aggregate / derived rates)
    - `BucketReport` dataclass (per-bucket list + overall TOTAL)
    - `load_bucket_report(eval_log) -> BucketReport`
  - `packages/caliper/src/caliper/report/render.py` (~80 lines):
    - `render_bucket_table(report) -> str` (ASCII table)
    - `render_bucket_markdown(report) -> str`
  - Tests: 12+ unit tests using a real `.eval` log fixture from
    `logs/` plus synthetic mock EvalSamples for edge cases
    (provider-silent cache, mixed-provider aggregation, empty
    bucket, etc.)

  **Done when**: loading a real v8 baseline `.eval` log produces
  a 4-bucket + TOTAL table with `pass / lazy / mean_tokens /
  cache_hit_rate / uncached_input_tokens` columns; compare bucket
  visibly worse on cache_hit_rate per the methodology principle 5
  diagnostic signal; total tests 124 → 136+

- [ ] **M1.5** A/B compare + `caliper` CLI

  Adds the second core report function and the first CLI surface.
  Designed coherently with M1.4 because CLI subcommands belong
  together.

  - `packages/caliper/src/caliper/report/ab.py` (~150 lines):
    - `load_ab_diff(baseline_log, candidate_log) -> ABDiff`
    - Computes per-bucket deltas in pass rate, mean tokens,
      cache_hit_rate, uncached_input_tokens
    - Refuses to label improvements within the noise floor
      (default: 2σ across the available epochs)
    - Specifically flags the "total tokens dropped + cache_hit_rate
      dropped" pattern as a likely cache-prefix regression
  - `packages/caliper/src/caliper/cli.py` (~100 lines):
    - `caliper report <log.eval>` → bucket report
    - `caliper diff <baseline.eval> <candidate.eval>` → A/B diff
    - Built on `argparse` (stdlib only, no click dependency)
    - `[project.scripts]` entry in `caliper/pyproject.toml`
  - Tests: synthetic before/after pairs verifying the noise-floor
    refusal, the cache-regression flag, and CLI argument parsing

  **Done when**: `caliper report logs/<file>.eval` prints the M1.4
  table; `caliper diff` on a synthetic before/after with a known
  noise-floor delta refuses to label it an improvement

- [ ] **M1.6** v9 token+cache baseline + Apple--3 reproduce check

  The first baseline produced under caliper. Validates Phase 1's
  full thesis: caliper produces numbers comparable to v8 + new
  per-bucket token/cache visibility.

  - Run the full v8_baseline (Sonnet, 12 tasks × 2 epochs = 24
    runs); record the `.eval` log
  - Run again on GPT-5.4 (24 more runs)
  - Save anchor numbers to `baselines/v9.json` (per-bucket + TOTAL +
    Apple--3 specifically)
  - Apple--3 reproduce check: at least one of the 2 runs must hit
    the v8 failure mode (12-step limit, empty answer or judge
    incorrect). If both pass, max_turns has been silently relaxed
    or some other change occurred — investigate before declaring
    M1.6 done.

  **Done when**:
  - `baselines/v9.json` exists and is committed
  - Sonnet pass rate is 22-24/24 (within ±1 of v8's 23/24)
  - GPT-5.4 pass rate is 16-18/24 (within ±1 of v8's 17/24)
  - Apple--3 failure reproduces (matches v8 anchor)
  - Per-bucket cache_hit_rate is reported and the compare bucket
    is visibly the worst (per methodology principle 5)

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

Updated as milestones land. Token columns replaced the original
$ columns per the M1.2 re-scope.

| Metric                       | v8 (run.py) | v9 (caliper) | Delta | Notes |
|---|---|---|---|---|
| Sonnet judge pass            | 23/24       | TBD          | TBD   | Target: ±1 of v8 |
| Sonnet Apple--3 failure      | run 2 fails | TBD          | —     | Must reproduce |
| Sonnet total tokens          | ~292K       | TBD          | TBD   | Per 24-run baseline |
| Sonnet uncached_input_tokens | unknown     | TBD          | NEW   | First time visible |
| Sonnet cache_hit_rate        | unknown     | TBD          | NEW   | First time visible |
| Sonnet compare bucket cache  | unknown     | TBD          | NEW   | Expected: lowest |
| GPT-5.4 judge pass           | 17/24       | TBD          | TBD   | Target: ±1 of v8 |
| GPT-5.4 cache_hit_rate       | unknown     | TBD          | NEW   | gpt-5 cold-cache fix |
| Total wall time / 24-run     | unknown     | TBD          | NEW   | |

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
