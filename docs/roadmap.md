# Roadmap

This is the live tracking doc for caliper development. Phases are designed
to be small enough to ship in one focused session each. Each phase has
explicit milestones with success criteria so progress is unambiguous.

**Update this file every time a milestone is completed.** The git history
of this file is the project log.

## Phase 0: Documentation scaffolding (current)

**Goal**: Commit to architecture, methodology, and roadmap before writing
any Python.

**Why first**: Doc-first development forces us to be explicit about
abstractions, scope, and out-of-scope before code makes them hard to
change. The cost of writing docs is low; the cost of refactoring code
because the docs were ambiguous is high.

### Milestones

- [x] **M0.1** Project skeleton
  - directory created at `~/Documents/Coding/caliper/`
  - `git init`, `LICENSE` (MIT), `.gitignore`, minimal `pyproject.toml`
  - **Done when**: `git log` has at least one commit, `cat LICENSE` shows MIT

- [x] **M0.2** Seven narrative docs written
  - `README.md`, `docs/README.md`, `docs/why.md`, `docs/methodology.md`,
    `docs/architecture.md`, `docs/self-evaluation.md`,
    `docs/lessons-learned.md`, `docs/roadmap.md` (this file)
  - **Done when**: All 8 files exist and are non-stub

- [x] **M0.3** Initial commit
  - **Done when**: `git log --oneline` shows the commit; the working tree is clean
  - Commit: `550b2aa Initial documentation scaffolding`

- [x] **M0.4** Operational + reference docs (added after the "could
  another agent pick this up?" check)
  - `docs/context.md` — operational context (related repos, env, file
    pointers)
  - `docs/reference/baseline-v8.md` — anchor numbers
  - `docs/reference/curated-tasks.md` — 12 v8 tasks with full specs
  - `docs/reference/inherited-artifacts.md` — verbatim code/prompts
  - **Done when**: A new contributor can start Phase 1 without needing
    to read `browser-pilot/tests/agent/run.py`

- [ ] **M0.5** Push to remote (optional, when ready)
  - GitHub repo created
  - First push
  - **Done when**: Remote URL is reachable and matches local

### Phase 0 effects (what we'll know after this phase)

- Whether the proposed architecture survives the act of writing it down
- Whether the methodology principles are clear enough to encode as code
- Whether the roadmap is realistic before any code commitment

---

## Phase 1: Browser-pilot migration (Week 2)

**Goal**: Reproduce the browser-pilot v8 baseline using caliper + Inspect AI,
prove the abstractions work, retire the old `tests/agent/run.py`.

**Success criterion**: Caliper produces the same judge pass rate as v8
baseline (Sonnet 23/24) within the 95% confidence interval, plus a fresh
cost-aware report we couldn't produce before.

> **Before starting Phase 1**, read [`context.md`](context.md) for
> environment setup and file pointers, and skim
> [`reference/inherited-artifacts.md`](reference/inherited-artifacts.md)
> for the verbatim code/prompts you'll port.

### Milestones

- [ ] **M1.1** Inspect AI installed and one task end-to-end
  - `uv add inspect-ai anthropic openai`
  - Write `src/caliper/__init__.py` placeholder
  - Write `src/caliper/solvers/text_protocol.py` (~150 lines) — uses the
    extractor from
    [`reference/inherited-artifacts.md` §4](reference/inherited-artifacts.md)
  - Write `src/caliper/scorers/json_verdict.py` (~50 lines) — port the
    parser from [§2](reference/inherited-artifacts.md), include the
    `test_keyword_incorrect_fallback_NOT_substring_bug` regression test
  - Write `src/caliper/scorers/judge_stale_ref.py` (~80 lines) — port
    the prompt from [§1](reference/inherited-artifacts.md) verbatim
  - Write `src/caliper/scorers/lazy_detection.py` (~60 lines) — use the
    `OBSERVATION_COMMANDS` set from [§3](reference/inherited-artifacts.md)
  - Write `examples/cambridge_smoke.py` — use the
    `Cambridge Dictionary--3` task from
    [`reference/curated-tasks.md`](reference/curated-tasks.md)
  - Run: `inspect eval examples/cambridge_smoke.py --model anthropic/claude-sonnet-4-6`
  - **Done when**: One task completes end-to-end and `inspect view` shows
    the trace

- [ ] **M1.2** Cost wrapper
  - `src/caliper/metrics/pricing.py` with per-model pricing table
    (Sonnet, Haiku, GPT-5.4, etc., dated 2026-01)
  - `src/caliper/metrics/cost.py` with `cost_usd()` function reading
    Inspect AI's I/CW/CR/O fields
  - `src/caliper/scorers/cost_tracker.py` exposing cost as a metric
  - **Done when**: A run reports `$ per run`, `cache_hit_rate`, and
    `effective_tokens`

- [ ] **M1.3** Twelve v8 tasks ported
  - `examples/browser_pilot_v8/data.jsonl` — 12 curated tasks with bucket
    metadata, sourced from
    [`reference/curated-tasks.md`](reference/curated-tasks.md)
  - `examples/browser_pilot_v8/tasks.py` — `@task` definition
  - **Done when**: `inspect eval examples/browser_pilot_v8/tasks.py
    --epochs 2` runs all 24 samples

- [ ] **M1.4** Bucket report
  - `src/caliper/report/bucket.py` reads `.eval` log files, aggregates by
    `metadata.bucket`
  - CLI: `caliper report logs/`
  - **Done when**: Bucket report matches the v8 baseline structure
    (lookup/search/compare/navigate columns)

- [ ] **M1.5** A/B compare tool
  - `src/caliper/report/ab.py` diffs two `.eval` files
  - Refuses to label improvements that are within 2σ of noise floor
  - **Done when**: Running on (v7-old, v8-old) shows the +2 stale-ref delta
    with proper noise-aware framing

- [ ] **M1.6** v9 baseline produced
  - The first cost-aware baseline. Run with caliper, save as `baselines/v9.json`
  - Compare to anchor numbers in
    [`reference/baseline-v8.md`](reference/baseline-v8.md)
  - **Done when**: Differences from v8 are explainable (real cost is now
    visible; cache hit rate is reported; Sonnet pass rate is 22-24/24,
    gpt-5.4 is 16-18/24)

- [ ] **M1.7** Old `run.py` retired
  - browser-pilot's `tests/agent/run.py` and `v7_baseline.py` deleted (or
    moved to `tests/agent/legacy/` and clearly marked deprecated)
  - browser-pilot's `tests/agent/` becomes a thin wrapper around
    `inspect eval` that points at the caliper-based task definitions
  - **Done when**: `npm run test:agent` runs caliper, not the old runner

### Phase 1 effects table

Update after each milestone:

| Metric | v8 (browser-pilot run.py) | v9 (caliper) | Delta | Notes |
|---|---|---|---|---|
| Sonnet judge pass | 23/24 | TBD | TBD | Should be within 95% CI |
| Sonnet total tokens | ~292K | TBD | TBD | |
| Sonnet $ / run | unknown | TBD | NEW | First time we see this |
| Sonnet cache hit rate | unknown | TBD | NEW | First time we see this |
| Sonnet $ / pass | unknown | TBD | NEW | The real optimization target |
| GPT-5.4 judge pass | 17/24 | TBD | TBD | |
| Total time per run (avg) | unknown | TBD | NEW | |

### Phase 1 risks

| Risk | Mitigation |
|---|---|
| Inspect AI's solver model doesn't fit text-protocol cleanly | Write a custom solver, not built-in `basic_agent` |
| Cost wrapper doesn't match Anthropic invoice exactly | Allow ±5% tolerance, log discrepancies |
| Bucket report doesn't match Sonnet's known numbers | Treat as a porting bug, debug against the saved logs from v8 |
| Inspect AI version changes break things mid-port | Pin version in pyproject.toml |

---

## Phase 2: Self-evaluation (Week 3)

**Goal**: Caliper can evaluate its own components. The judge, lazy
detector, and cost wrapper all have hand-labeled test suites that can be
run with `caliper eval tests/self_eval/<file>`.

**Success criterion**: Self-evaluation suite runs in CI and would have
caught the v0-v4 substring bug in 30 seconds.

### Milestones

- [ ] **M2.1** Judge self-eval suite
  - `tests/self_eval/judge_quality.py` with ≥50 hand-labeled (answer,
    expected_verdict) pairs across 6 categories (stale-ref-correct,
    obvious-wrong, describes-dont-do, factual-match, factual-wrong, empty)
  - **Done when**: Judge accuracy ≥95% on the suite; failures are
    categorized

- [ ] **M2.2** Lazy detection self-eval
  - `tests/self_eval/lazy_detection_quality.py` with ≥30 traces labeled
    (is_lazy = True/False)
  - **Done when**: Precision ≥95% (no false positives), recall ≥80%

- [ ] **M2.3** Cost accuracy self-eval
  - Run caliper for one week against real workloads
  - Compare summed cost vs Anthropic invoice
  - **Done when**: Discrepancy < 5%; otherwise file an issue and fix
    pricing table

- [ ] **M2.4** Stale-ref tolerance self-eval
  - `tests/self_eval/stale_ref_tolerance.py` with cases that distinguish
    "stale ref + correct now" from "wrong answer" from "correct fact"
  - **Done when**: All 4 quadrants (stale/non-stale × correct/wrong) are
    correctly classified

- [ ] **M2.5** JSON verdict parser robustness
  - `tests/unit/test_json_verdict_parser.py` with the substring bug
    regression test plus 10+ other edge cases
  - **Done when**: pytest passes; the substring bug regression test is
    enforced in pre-commit

- [ ] **M2.6** Self-eval in CI
  - GitHub Actions workflow that runs `caliper eval tests/self_eval/` on
    every PR that touches `src/caliper/scorers/`
  - **Done when**: A test PR with a deliberately broken judge prompt
    fails CI

### Phase 2 effects

| Metric | Before Phase 2 | After Phase 2 |
|---|---|---|
| Judge self-eval coverage | 0 cases | ≥50 cases |
| Lazy detection self-eval coverage | 0 cases | ≥30 cases |
| Cost accuracy verified vs invoice | No | Yes (±5%) |
| Substring bug protected by regression test | No | Yes |
| Self-eval runs on every scorer change | No | Yes (CI) |

---

## Phase 3: Second consumer (Week 4-5)

**Goal**: Validate that caliper's abstractions are general by integrating
a second project that's not browser-pilot.

**Success criterion**: A second project successfully uses caliper without
needing to fork or modify caliper internals.

### Candidates (pick one to start)

**A. computer-pilot migration**
- [ ] M3a.1 Write `cu_text_protocol_solver` (~100 lines, mostly mirrors
      `bp_text_protocol_solver`)
- [ ] M3a.2 Port computer-pilot's 3 existing agent test tasks to caliper
- [ ] M3a.3 Run; compare to computer-pilot's existing baseline numbers
- [ ] M3a.4 Confirm caliper internals didn't need any changes

**B. chatbot maxTurns A/B harness**
- [ ] M3b.1 Implement 9 limit-handling strategies (HardCut, ForceFinalize,
      PauseTurn, SoftWarn, MultiStage, etc.) as caliper Solvers
- [ ] M3b.2 Design 5-10 mock tools and budget-exhausting tasks
- [ ] M3b.3 Write multi-dimensional `chatbot_ux_judge` scorer (5 dimensions:
      completeness, usefulness, honesty, no-fabrication, no-error-surface)
- [ ] M3b.4 Run the matrix: 9 strategies × N tasks × 2 models × 3 runs
- [ ] M3b.5 Produce the strategy-comparison report
- [ ] M3b.6 Confirm caliper internals didn't need any changes

### Decision point after Phase 3

After both consumers are running, evaluate:

| Question | Answer needed |
|---|---|
| Did the abstractions hold? | Yes/No + what broke |
| What custom scorers/solvers were needed per consumer? | Inventory |
| What patterns are duplicated across consumers? | Candidates for promotion to caliper core |
| Is the framework worth open-sourcing? | Based on actual usability evidence |
| Should there be a v0.1.0 release? | Based on stability of abstractions |

---

## Phase 4: Polish and (optional) public release

Only proceed if Phase 3 validates the design.

- [ ] **M4.1** Write `examples/quickstart.md` — a 10-minute getting started
- [ ] **M4.2** Write `examples/browser_pilot_walkthrough.md` — full case study
- [ ] **M4.3** Write `examples/chatbot_maxturns_walkthrough.md` — second case study
- [ ] **M4.4** Pin Inspect AI version range in `pyproject.toml`
- [ ] **M4.5** Tag `v0.1.0`
- [ ] **M4.6** (Optional) PyPI upload
- [ ] **M4.7** (Optional) Blog post: "8 Rounds of Iterating browser-pilot"

---

## Effects tracking table (cross-phase)

This is the single source of truth for "did the project actually deliver
value". Update at the end of each phase.

| Phase | Date | Sonnet pass | Sonnet $/pass | Cache hit | Self-eval | 2nd consumer? |
|---|---|---|---|---|---|---|
| Pre-caliper (v8) | 2026-04-07 | 23/24 | unknown | 0% (not measured) | none | no |
| Phase 0 (docs) | TBD | n/a | n/a | n/a | n/a | n/a |
| Phase 1 (migration) | TBD | TBD | TBD | TBD | n/a | no |
| Phase 2 (self-eval) | TBD | TBD | TBD | TBD | ≥80 cases | no |
| Phase 3 (2nd consumer) | TBD | TBD | TBD | TBD | ≥80 cases | yes |
| Phase 4 (polish) | TBD | TBD | TBD | TBD | ≥100 cases | yes |

## Out of scope (explicitly not doing in Phase 0-4)

- Multi-language support (caliper is Python-only for the foreseeable future)
- A web UI of our own (Inspect AI's `inspect view` is sufficient)
- A custom DSL (Python config + YAML data is enough)
- Built-in benchmark datasets (we use what consumers provide)
- Production observability (use Langfuse / Phoenix for that)
- Real-time streaming (eval is offline by nature)

## Open questions

- Should caliper depend on `inspect-ai` directly or via an extras flag?
- Should the `pricing.py` table be a Python file or YAML? (Probably Python
  for type safety.)
- What's the right scope for a `caliper` CLI vs just using `inspect eval`?
- Should we publish baselines as immutable JSON files in a separate repo?
