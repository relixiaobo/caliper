# Roadmap

This is the live tracking doc for caliper development. Phases are designed
to be small enough to ship in one focused session each. Each phase has
explicit milestones with success criteria so progress is unambiguous.

**Update this file every time a milestone is completed.** The git history
of this file is the project log.

## Phase R: Workspace restructure (2026-04-07)

**Goal**: Lock in the hybrid architecture (core + scenarios as sibling
workspace packages) before any more code lands. The structure decision
is the expensive part; the file moves are mechanical.

**Why this phase exists**: After M1.1, a structural review showed that
the original single-package layout would crack under Phase 3 (chatbot
scenario adds ~1500 lines and a new `Strategy` axis). Restructuring at
v0.0.1 with 6 source files is virtually free; restructuring at v0.5.0
with 50 files is painful. So we did it now, in one shot.

### Milestones

- [x] **R0** Decision: hybrid architecture
  - One git repo, four sibling packages, uv workspace
  - Hard rule: `caliper` core never imports from any `caliper-*` adapter
  - Hard rule: adapters never import from each other
  - Promotion to core requires the rule of three
  - **Recorded in**: `docs/architecture.md` "Workspace layout" section

- [x] **R1** Workspace skeleton
  - `pyproject.toml` declares `[tool.uv.workspace]` members
  - 4 packages created: `caliper`, `caliper-browser-pilot`,
    `caliper-computer-pilot`, `caliper-chatbot`
  - Each has its own `pyproject.toml` and `README.md`

- [x] **R2** Core protocols + parsers + runtime helpers
  - `caliper.protocols` — `SolverState` (Pydantic StoreModel), `Strategy`
    Protocol class, `validate_task_metadata()`
  - `caliper.parsers.{shell,commands,answer}` — split out of
    text_protocol.py
  - `caliper.runtime.{subprocess,env}` — split out of text_protocol.py
    and `cambridge_smoke.py`

- [x] **R3** Move scorers + drop redundant params
  - All three M1.1 scorers moved to `packages/caliper/`
  - `lazy_detection` lost its `observation_commands` parameter (it was
    unused — the solver is the only authority)
  - `multi_dim.py` skeleton added for chatbot scorer (Phase 3b)
  - All scorers now read state via `state.store_as(SolverState)`,
    eliminating string-key access entirely

- [x] **R4** caliper-browser-pilot adapter content
  - `tools.py`: `BP_OBSERVATION_COMMANDS`, `bp_truncate_snapshot`
    (bp-specific JSON shape — moved out of caliper core), `bp_skill_path()`
    (env-var-first SKILL.md resolver, replaces hardcoded path)
  - `solver.py`: `bp_agent()` factory wrapping the generic solver with
    bp defaults

- [x] **R5** Skeletons for caliper-computer-pilot and caliper-chatbot
  - Empty modules + docstrings + `# TODO` markers pointing at the
    relevant roadmap milestones (M3a / M3b) and design docs

- [x] **R6** Tests moved + new tests added
  - 11 json_verdict tests (moved)
  - 12 text_protocol parser tests (moved)
  - **NEW**: 7 protocols tests (SolverState + metadata validation)
  - **NEW**: 4 runtime/env tests
  - **NEW**: 8 shell parser tests (`is_unterminated_shell`,
    `command_verb`)
  - **NEW**: 7 caliper-browser-pilot tools tests (snapshot formatter,
    SKILL path resolver)
  - **NEW**: 2 skeleton smoke tests (chatbot, cu)
  - `examples/cambridge_smoke.py` rewritten to import via
    `caliper_browser_pilot.bp_agent` and `caliper.runtime.load_dotenv`,
    no more hardcoded paths
  - `examples/quickstart.py` added — 30-second on-ramp

- [x] **R7** Verification
  - **51/51 unit tests pass** across all 4 packages
  - End-to-end smoke run (Cambridge Dictionary--3): judge_pass=True,
    lazy=False, 15,441 tokens (v8 baseline anchor: 14K — within range),
    7 messages, 2 commands_run, observed_page=True
  - Store keys are now `SolverState:agent_answer` etc., confirming
    the typed contract is wired through

- [x] **R8** Doc updates
  - `architecture.md` — full workspace layout + dependency contract +
    typed solver-scorer contract + Strategy axis section
  - `roadmap.md` — Phase R recorded (this section); Phase 3 reorganised
    around the new structure (see below)
  - `README.md` — status updated to reflect 4-package workspace
  - `context.md` — file pointers updated to packages/ paths

### Phase R effects

- caliper core stays at <1000 lines (currently ~600)
- Scenario PRs cannot touch core regression tests by accident
- Adding a new task is 2 minutes (drop a Sample in the right tasks/ dir)
- Adding a new CLI is half a day (new adapter package, ~150 lines)
- Adding chatbot maxTurns scenario is bounded to ~1500 lines that live
  in `caliper-chatbot/`, not in core
- Cross-package refactoring is one PR (single repo)

---

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

- [x] **M0.5** Push to remote
  - GitHub repo created: https://github.com/relixiaobo/caliper (public)
  - First push complete (main tracks origin/main)
  - **Done when**: Remote URL is reachable and matches local ✓ (2026-04-07)

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

- [x] **M1.1** Inspect AI installed and one task end-to-end (2026-04-07)
  - `uv add inspect-ai anthropic openai` ✓ (inspect-ai 0.3.205)
  - `src/caliper/__init__.py` placeholder ✓
  - `src/caliper/solvers/text_protocol.py` ✓ (~250 lines incl. parsers + truncator)
  - `src/caliper/scorers/json_verdict.py` ✓ — 11/11 unit tests pass,
    including `test_keyword_incorrect_fallback_NOT_substring_bug`
  - `src/caliper/scorers/judge_stale_ref.py` ✓ — v8 prompt verbatim
  - `src/caliper/scorers/lazy_detection.py` ✓ — bp observation set
  - `examples/cambridge_smoke.py` ✓ — Cambridge Dictionary--3
  - Smoke run: judge_pass=1, lazy=0, 10.5K tokens, 2 commands, 5 messages
  - **Bug found and fixed during M1.1**: solver originally checked
    `extract_answer` before `extract_commands`. When the agent emitted
    both commands and an `ANSWER:` in the same turn (hallucinating tool
    output), the answer was accepted without ever running the commands.
    Fix: extract commands first; ANSWER is only terminal on a turn with
    no commands. This is exactly the kind of measurement-layer bug
    methodology principle 1 exists to catch.

- [x] **M1.2** Token-usage observability (2026-04-08)

  **Re-scoped from the original "cost wrapper" after deep research into
  Inspect AI 0.3.205's cross-provider ``ModelUsage`` support.** The
  original plan (pricing table + `cost_usd()` scorer + `$ per run`
  metric) was dropped for three reasons:

  1. **Inspect AI ships zero cost data.** `ModelUsage.total_cost`,
     `ModelCost` schema, and `compute_model_cost()` all exist, but the
     bundled YAML files for anthropic/openai/google/grok/together/
     mistral/deepseek have **zero `cost:` entries**. Every provider
     returns `total_cost=None` in 0.3.205, so there is nothing for
     caliper to "prefer upstream" against — caliper would have to
     duplicate a pricing table it can't keep in sync.
  2. **Same-model iteration doesn't need dollars.** The iteration loop
     caliper supports (SKILL.md / solver tuning) holds the model
     fixed, so fewer tokens at the same model is strictly cheaper.
     The user clarified the real goal is token observability and
     cache-hit-rate control, not dollar comparison.
  3. **No universal "effective tokens" formula exists.** Different
     providers have different cache pricing ratios (Anthropic cache
     write=1.25×, cache read=0.1×; OpenAI has no cache write, read≈0.5×;
     Gemini caches differently), so any single-number synthetic
     metric would be silently wrong for somebody.

  **What M1.2 actually delivered:**
  - `packages/caliper/src/caliper/metrics/usage.py` — one frozen
    `UsageSummary` dataclass with normalised token fields, honesty
    flags (`has_cache_info`, `has_reasoning_info`), and derived
    properties (`total_input_tokens`, `total_tokens`,
    `uncached_input_tokens`, `cache_hit_rate: float | None`). Also
    `__add__` for bucket aggregation and `zero()` as the additive
    identity.
  - `packages/caliper/src/caliper/metrics/__init__.py` exports it.
  - `packages/caliper/tests/unit/test_metrics_usage.py` — 17 tests
    covering the five realistic provider patterns (Anthropic full,
    OpenAI Chat, Bedrock bare, Gemini reasoning-only, Mistral basic),
    the critical `cache_hit_rate is None vs 0.0` distinction, and
    `__add__` aggregation with honesty-flag OR semantics.

  **What M1.2 deliberately did NOT do** (all deferred to later):
  - No pricing table, no `cost_usd()`, no `$` field anywhere
  - No `cost_tracker` scorer — the raw `ModelUsage` is already in
    the `.eval` log via `EvalSample.model_usage`, so derived cost
    would be data duplication. Report layer (M1.4) is the first
    real consumer.
  - No `effective_tokens` single-number metric — report layer can
    add provider-aware weights if ever needed.
  - No changes to solver, scorer, example, or solver state. M1.2 is
    pure library code.
  - No changes to the `.eval` log. Cost/usage analysis is read-time
    derivation only.

  **Provider coverage verified by source reading:** Anthropic direct,
  OpenAI Chat Completions, OpenAI Responses (gpt-5), Google Gemini,
  Bedrock, Grok, Perplexity, Azure, Mistral, Groq, Together, HF local,
  MockLLM, and the 7 openai-compatible providers (Cloudflare,
  Fireworks, OpenRouter, Ollama, vLLM, SambaNova, SGLang). Only
  Anthropic direct populates `input_tokens_cache_write`; everywhere
  else it is `None` and `has_cache_info` degrades accordingly.

  **Done when:** ✓ 86/86 tests pass (69 → 86, +17 for M1.2);
  ✓ integration check on real cambridge_smoke `.eval` log loads
  `sample.model_usage` entries and produces sensible `UsageSummary`
  with correct `has_cache_info` / `cache_hit_rate` values.

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

## Phase 3: Second + third scenarios

**Goal**: Validate that caliper's abstractions are general by populating
both the `caliper-computer-pilot` and `caliper-chatbot` workspace
packages with real implementations.

**Success criterion**: Both adapter packages produce real numbers
without requiring any change to `caliper` core. If core needs a change,
the change is small (<100 lines), motivated by both adapters
(rule-of-three), and adds a new abstraction rather than changing an
existing one.

> The package skeletons for both already exist (Phase R). The work in
> Phase 3 is filling them in.

### Phase 3a: computer-pilot adapter

Lives in `packages/caliper-computer-pilot/`. Expected size: ~300 lines
total (mirrors `caliper-browser-pilot` shape).

- [ ] **M3a.1** Implement `caliper_computer_pilot.tools`:
      `CU_OBSERVATION_COMMANDS`, `cu_truncate_snapshot` for cu's
      accessibility-tree JSON shape, `cu_skill_path()` env-var resolver
- [ ] **M3a.2** Implement `caliper_computer_pilot.solver.cu_agent()` —
      thin wrapper over `caliper.solvers.text_protocol_agent`
- [ ] **M3a.3** Port computer-pilot's 3 existing agent test tasks into
      `tasks/`. Run via `inspect eval`.
- [ ] **M3a.4** Compare to computer-pilot's existing baseline numbers
- [ ] **M3a.5** Confirm `caliper` core didn't need any changes (success
      = the only files touched outside `caliper-computer-pilot/` are
      docs and the workspace lockfile)

### Phase 3b: chatbot maxTurns scenario

Lives in `packages/caliper-chatbot/`. Expected size: ~1500 lines.
Full design is in [`docs/chatbot-maxturns.md`](chatbot-maxturns.md).
Implementation follows that doc's §8 phased rollout.

#### Phase 3b — Step 0: core protocol additions

A small amount of new code MAY land in `caliper` core to support this
scenario. The bar is "needed by both chatbot and at least one other
scenario or general use case":

- [ ] **M3b.0a** `caliper.scorers.multi_dim` — multi-dimensional scorer
      base class (currently a placeholder). RAG quality, chain-of-thought
      quality, and other future scorers will reuse it.
- [ ] **M3b.0b** `caliper.mocks` — mock-tool framework infrastructure
      (currently a placeholder). Generic infrastructure for defining
      deterministic mock tools, registering them with a solver, and
      recording/replaying traces.
- [ ] **M3b.0c** `caliper.solvers.strategy_loop` — generic agent loop
      that takes a `Strategy` hook. Used by chatbot but designed to be
      reusable by any scenario that varies meta-policy.

If any of these grow beyond ~150 lines or require changing the existing
`caliper.solvers.text_protocol` API, stop and reconsider — the goal is
to add a new abstraction, not to retrofit the existing one.

#### Phase 3b — Step 1: minimum viable closed loop (~3 days)

Per `docs/chatbot-maxturns.md` §8 Step 1:

- [ ] **M3b.1.1** Implement 3 most-differentiated strategies:
      `caliper_chatbot.strategies.hard_cut`, `force_finalize_strict`,
      `multi_stage`
- [ ] **M3b.1.2** Implement 1 mock task: `tasks.research_grants` with
      its mocks
- [ ] **M3b.1.3** Implement `caliper_chatbot.scorers.ux_judge`
      (5 dimensions: completeness, usefulness, honesty, no_fabrication,
      no_error_surface)
- [ ] **M3b.1.4** Implement `caliper_chatbot.solver.limit_strategy_agent`
      using `caliper.solvers.strategy_loop`
- [ ] **M3b.1.5** Run: 1 model × 1 budget × 1 task × 3 strategies × N=3 = 9 runs
- [ ] **M3b.1.6** Validate the judge produces sensible scores; inspect
      9 traces in `inspect view`

#### Phase 3b — Step 2: full Phase A (~1 day)

Per `docs/chatbot-maxturns.md` §4.4 Phase A:

- [ ] **M3b.2.1** Implement remaining 6 strategies: `silent_stop`,
      `force_finalize_lenient`, `soft_warn`, `pause_turn`,
      `adaptive_budget`, `token_budget`
- [ ] **M3b.2.2** Implement remaining 4 mock tasks: `debug_auth`,
      `shopping_compare`, `multi_source`, `compound_task`
- [ ] **M3b.2.3** Run the full Phase A matrix:
      1 model × 1 budget × 5 tasks × 9 strategies × 3 runs = 135 runs
- [ ] **M3b.2.4** Produce the 9-strategy × 5-dimension UX matrix

#### Phase 3b — Step 3: cross-model + budget sweep (~2 days)

- [ ] **M3b.3.1** Phase B: 3 models × top 5 strategies × 5 tasks × 3 runs
- [ ] **M3b.3.2** Phase C: budget sweep on top 3 strategies, 6 maxTurns
      values
- [ ] **M3b.3.3** Final report: ready for publication / internal review

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
