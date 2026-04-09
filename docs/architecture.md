# Architecture

## Core insight

Caliper is **a thin opinionated layer on top of [Inspect AI](https://inspect.aisi.org.uk/)**.

Inspect AI already provides 80% of what an agent eval framework needs. Caliper
adds the remaining 20% — the parts that enforce the methodology in
[methodology.md](methodology.md).

```
┌─────────────────────────────────────────────────────────────┐
│  Consumer projects                                            │
│  browser-pilot/eval/   computer-pilot/eval/   chatbot-bench/ │
│        │                       │                    │        │
│        └───────────┬───────────┴────────────────────┘        │
│                    ▼                                          │
├─────────────────────────────────────────────────────────────┤
│  Caliper (~500 lines Python)                                  │
│  ├─ scorers/        judge_stale_ref, lazy_detection,         │
│  │                  json_verdict, cost_threshold              │
│  ├─ solvers/        text_protocol_agent (CLI tool wrapper)    │
│  ├─ metrics/        cost calculator, pricing tables           │
│  ├─ report/         bucket aggregation, A/B comparison        │
│  └─ datasets/       webvoyager loader, task format            │
├─────────────────────────────────────────────────────────────┤
│  Inspect AI (the foundation we don't reinvent)                │
│  ├─ Task / Solver / Scorer abstractions                       │
│  ├─ Multi-provider LLM API (Anthropic, OpenAI, Google, ...)   │
│  ├─ Tool use (native function calling + MCP + custom)         │
│  ├─ Sandbox (Docker / Kubernetes / Modal / local)             │
│  ├─ Eval sets, epochs, retries, resumption                    │
│  ├─ Cache token tracking (I / CW / CR / O)                    │
│  └─ Web viewer (`inspect view`)                               │
├─────────────────────────────────────────────────────────────┤
│  LLM providers                                                 │
│  Anthropic / OpenAI / Google / Mistral / vLLM / local          │
└─────────────────────────────────────────────────────────────┘
```

## Two integration modes

Caliper supports two ways for agent projects to use its measurement layer.
Both share the same scoring logic (via ``caliper.scoring``):

```
Mode A: Full mode (Inspect AI eval loop)
  inspect eval → Task → bp_agent solver → scorers → BucketReport

Mode B: Measurement-only mode (standalone API)
  any agent → CaliperRecord → CaliperEvaluator.evaluate() → BucketReport
  any agent → JSON file → caliper score records.json → report
```

**Mode A** is the original design and is best for caliper-native projects.
Your project defines ``@task`` functions and runs via ``inspect eval``.

**Mode B** was added in Phase 1 close to support external projects that
have their own agent loop. The key abstraction is ``CaliperRecord`` — a
simple dataclass that any framework can produce. The project decides what
tasks to evaluate and what "correct" means; caliper provides the standard
measurement methodology.

### CaliperRecord — the universal data contract

```python
from caliper import CaliperRecord, CaliperEvaluator

records = [
    CaliperRecord(
        sample_id="task-1",
        bucket="lookup",               # project-defined category
        goal="What is the derivative of x^2 at x=5.6?",
        agent_answer="11.2",           # agent's final answer
        observed=True,                  # agent actually looked at the target
        reference_answer="11.2",        # optional: for LLM judge
        input_tokens=50000,             # optional: for token metrics
        output_tokens=3000,
    ),
]

evaluator = CaliperEvaluator(judge_model="anthropic/claude-sonnet-4-6")
report = await evaluator.evaluate(records)
```

Required fields (enforce methodology at the type level):
- ``sample_id`` — per-sample failure attribution
- ``bucket`` — per-group aggregation
- ``goal`` — task description (fed to LLM judge)
- ``agent_answer`` — empty = explicit failure
- ``observed`` — mandatory for lazy detection

Optional fields: ``reference_answer`` (for LLM judge), ``verify_specs``
/ ``verify_results`` (for deterministic verification), token usage,
``commands_run``, ``epoch``, ``metadata``.

## What lives where

### Inspect AI provides (we don't write)

- The agent loop infrastructure (Mode A only)
- Multi-provider model client with cache token reporting
- Sandboxed tool execution
- Sample/Dataset abstractions
- Eval orchestration and parallelism
- The web viewer for trace inspection

### Caliper provides (~1,200 lines Python as of Phase 1 close)

- **Data contract**: ``CaliperRecord`` — the universal interface between
  any agent system and caliper's measurement layer
- **Scoring kernel** (``caliper.scoring``): pure functions independent
  of Inspect AI:
  - ``score_lazy(answer, observed)`` — catches "answered without looking"
  - ``score_judge(goal, answer, ref, model)`` — LLM judge with stale-ref
    tolerance and structured JSON verdict parsing
  - ``score_verify(specs_or_results)`` — deterministic post-hoc checks
  - ``build_judge_prompt`` / ``parse_judge_verdict`` — shared prompt + parser
- **Inspect AI scorers** (``caliper.scorers``): thin wrappers that bridge
  ``TaskState`` to the pure scoring kernel:
  - ``judge_stale_ref`` — calls ``score_judge`` internally
  - ``lazy_detection`` — calls ``score_lazy`` internally
  - ``verify_commands`` — calls ``score_verify`` internally
- **Solvers** for non-standard agent loops:
  - ``text_protocol_agent`` — wraps a CLI tool, parses commands from LLM
    free text. Supports ``session_prologue`` for per-sample state reset.
- **Metrics**: ``UsageSummary`` — cross-provider token normalisation with
  ``cache_hit_rate`` and honesty flags (``has_cache_info``,
  ``has_reasoning_info``)
- **Report layer**:
  - ``BucketReport`` — aggregate by ``metadata.bucket``
  - ``ABDiff`` — diff two reports with 2σ noise floor
  - ``render_bucket_table`` / ``render_ab_diff`` — ASCII table output
- **Public API**: ``CaliperEvaluator`` — one-liner: records → report
- **CLI**:
  - ``caliper report <log.eval>`` — bucket table from Inspect AI log
  - ``caliper diff <base.eval> <cand.eval>`` — A/B comparison
  - ``caliper score <records.json>`` — evaluate CaliperRecords from JSON
- **Datasets**: ``load_webvoyager_jsonl`` — JSONL → Inspect Samples with
  bucket tags

### What consumers provide

**Mode A** (Inspect AI full mode): a ``@task`` function + dataset + adapter
code (e.g. ``bp_agent()`` factory). Everything else comes from the stack.

**Mode B** (measurement-only): a list of ``CaliperRecord`` objects. The
project runs its own agent loop and constructs records from the output.
caliper handles scoring, aggregation, and reporting.

### Adapter packages (planned to move — see roadmap M3.0)

Currently adapter packages (``caliper-browser-pilot``,
``caliper-computer-pilot``, ``caliper-chatbot``) live in caliper's
monorepo workspace at ``packages/``. This is a temporary development
convenience. After Phase 2 stabilises the core API, adapters will move
to their respective agent project repos (see roadmap M3.0: Adapter
Repository Split), and caliper's repo will contain only the core
framework.

## Two example use cases

### Example 1: Browser-pilot iteration

This is the case caliper was extracted from. The setup looks like:

```python
# browser-pilot/eval/tasks.py
from inspect_ai import task, Task
from inspect_ai.dataset import Sample
from caliper.solvers import text_protocol_agent
from caliper.scorers import judge_stale_ref_tolerant, lazy_detection, cost_tracker
from caliper.datasets import load_webvoyager

@task
def browser_pilot_v9(model: str = "claude-sonnet-4-6", epochs: int = 2) -> Task:
    return Task(
        dataset=load_webvoyager(
            "data/v8_curated.jsonl",
            buckets={
                "lookup":   ["Cambridge Dictionary--3", "Wolfram Alpha--0", "Wolfram Alpha--2"],
                "search":   ["Allrecipes--3", "Coursera--0", "Huggingface--3"],
                "compare":  ["Apple--0", "Apple--3", "Allrecipes--0"],
                "navigate": ["GitHub--3", "BBC News--5", "ArXiv--2"],
            },
        ),
        solver=text_protocol_agent(
            cli_name="bp",
            observation_commands={"read", "snapshot", "eval", "screenshot",
                                  "locate", "tabs", "cookies"},
            max_turns=12,
            system_prompt_file="../plugin/skills/browser-pilot/SKILL.md",
        ),
        scorer=[
            judge_stale_ref_tolerant(model="claude-sonnet-4-6"),
            lazy_detection(),
            cost_tracker(),
        ],
        epochs=epochs,
    )
```

Run:

```bash
inspect eval tasks.py@browser_pilot_v9 --model anthropic/claude-sonnet-4-6
inspect view  # web viewer
caliper report logs/  # bucket aggregation + cost report
```

The same shape would work for `cu` (computer-pilot) by swapping the
`cli_name` and SKILL file.

### Example 2: Chatbot maxTurns strategy A/B

This is a fundamentally different shape: instead of testing whether the
agent completes a task, we're testing **what happens when the budget runs
out**. The "strategy" is the thing being iterated.

```python
# chatbot-bench/strategies.py
from caliper.solvers import limit_strategy_solver

class HardCutStrategy:
    """Just throw an error when budget hit. (LangChain default behavior.)"""
    def on_limit_reached(self, messages, llm):
        return Termination(text=None, kind="error")

class ForceFinalize:
    """Make one more call with tool_choice=none to summarize."""
    def on_limit_reached(self, messages, llm):
        final = llm.call(
            messages + [{"role": "user", "content": "Based only on what you've found so far, give your final answer. No more tools."}],
            tool_choice="none",
        )
        return Termination(text=final.text, kind="finalized")

class PauseTurn:
    """Anthropic-style soft pause: return state, no error."""
    def on_limit_reached(self, messages, llm):
        return Termination(text=None, kind="paused", resumable=True)

# ... 6 more strategies from the design space

@task
def chatbot_limit_ab() -> Task:
    return Task(
        dataset=load_limit_forcing_tasks("data/budget_exhausting_tasks.jsonl"),
        solver=limit_strategy_solver(strategy=ForceFinalize(), max_turns=10),
        scorer=[
            chatbot_ux_judge(),  # custom: rates 5 dimensions of the user-facing output
            lazy_detection(),
            cost_tracker(),
        ],
        epochs=3,  # higher N because chatbot UX is high-variance
    )
```

The matrix:

```
9 strategies × 12 limit-forcing tasks × maxTurns ∈ {10, 15, 20} × 2 models × 3 runs = 1944 runs
```

Caliper handles all of this through Inspect AI's eval orchestration. The
report layer produces a "strategy × bucket × ux_dimension" table that
directly answers "which strategy is best for which task type".

This use case is the one most people in the chatbot maxTurns research
space don't have a good answer for. Caliper makes it cheap to answer.

## The "self-evaluation" axis

Caliper's components are themselves agent-related artifacts: judge prompts,
scorer logic, parsers. They benefit from the same iteration discipline.

The framework therefore has a `tests/self_eval/` directory containing
caliper-format tasks that test caliper's own components. See
[self-evaluation.md](self-evaluation.md) for details.

## Why not build from scratch?

We considered it. We rejected it because:

1. **Inspect AI's web viewer alone is months of work to replicate**. It lets
   you click into any sample, see the full conversation with token
   breakdown, see scorer details, compare epochs. Building this for caliper
   would be the single largest engineering investment.

2. **Inspect AI's multi-provider abstraction is already correct**. Including
   the gpt-5 reasoning model quirk (no temperature parameter), the cache
   token field on Anthropic, the streaming format differences. We'd rebuild
   all of this and find new bugs.

3. **Inspect AI is maintained by UK AISI**. Caliper as a personal project
   has no such backing. Depending on a government-funded foundation gives
   us survivability we can't otherwise have.

4. **The stuff we actually need to write is small** (~500 lines). The right
   strategy is to keep that small, not to inflate it.

## Why not just use Inspect AI directly without caliper?

You can. Inspect AI is excellent. But you'd rediscover the methodology
lessons from the 8 weeks of browser-pilot iteration on your own. Caliper
exists to encode those lessons as the path of least resistance:

- The default judge scorer **already** has the anti-substring-bug fix
- The default agent loop **already** tracks lazy behavior
- The default report **already** computes cost in $ and cache hit rate
- The default config **already** sets `epochs=2` with a warning if you go
  below

If you'd find these defaults useful, use caliper. If you're confident you
won't trip on these traps, use Inspect AI directly.

## Workspace layout — single git repo, multiple Python packages

Caliper is structured as a **uv workspace**: one git repo, four
sibling Python packages, single venv, single lockfile. This is the
hybrid of "thin core" and "scenarios live with the framework" — see
`docs/roadmap.md` Phase R for the rationale.

```
caliper/                              # git repo root
├── pyproject.toml                    # uv workspace declaration
├── packages/
│   ├── caliper/                      # ★ CORE — ~800 line ceiling
│   │   ├── pyproject.toml
│   │   ├── src/caliper/
│   │   │   ├── protocols.py          # SolverState, Strategy, TaskMetadata — typed contracts
│   │   │   ├── parsers/              # shell.py, commands.py, answer.py — pure functions
│   │   │   ├── runtime/              # subprocess.py, env.py — async helpers
│   │   │   ├── solvers/              # text_protocol agent loop (generic)
│   │   │   ├── strategies/           # Strategy Protocol class only, zero implementations
│   │   │   ├── scorers/              # json_verdict, judge_stale_ref, lazy_detection, multi_dim base
│   │   │   ├── mocks/                # mock-tool framework infrastructure
│   │   │   ├── metrics/              # cost, pricing (M1.2)
│   │   │   ├── report/               # bucket, ab, multi_dim (M1.4 / M1.5)
│   │   │   └── datasets/             # generic loaders for public benchmarks (M1.3)
│   │   └── tests/{unit, self_eval}/
│   │
│   ├── caliper-browser-pilot/        # ★ ADAPTER — knows about bp
│   │   ├── pyproject.toml
│   │   └── src/caliper_browser_pilot/
│   │       ├── tools.py              # BP_OBSERVATION_COMMANDS, bp_truncate_snapshot, bp_skill_path
│   │       ├── solver.py             # bp_agent() factory wrapping caliper.solvers.text_protocol_agent
│   │       └── tasks/                # 12 v8 tasks (M1.3) + 4 heroku smoke (M1.7)
│   │
│   ├── caliper-computer-pilot/       # ★ ADAPTER — Phase 3a skeleton, knows about cu
│   │   └── src/caliper_computer_pilot/
│   │       ├── tools.py              # CU_OBSERVATION_COMMANDS (TODO M3a)
│   │       ├── solver.py             # cu_agent() (TODO M3a)
│   │       └── tasks/                # ports computer-pilot's 3 agent tests (TODO M3a)
│   │
│   └── caliper-chatbot/              # ★ SCENARIO — Phase 3b skeleton
│       └── src/caliper_chatbot/
│           ├── strategies/           # 9 LimitStrategy implementations (TODO M3b)
│           ├── scorers/              # multi-dim chatbot UX judge (TODO M3b)
│           ├── mocks/                # 5 mock task implementations (TODO M3b)
│           ├── tasks/                # 5 budget-exhausting task definitions (TODO M3b)
│           └── solver.py             # limit_strategy_agent (TODO M3b)
│
├── examples/                         # tiny one-file demos
│   ├── quickstart.py                 # 30-second on-ramp
│   └── cambridge_smoke.py            # M1.1 example
│
├── baselines/                        # anchor numbers (M1.6 onward)
└── docs/                             # all narrative + reference docs
```

### The dependency contract

Three hard rules make this structure work:

1. **`caliper` core never imports from any `caliper-*` adapter package.**
   The dependency arrow always points one way. This is what keeps core
   small and stable.

2. **Adapter packages never import from each other.**
   `caliper-browser-pilot` cannot use anything from `caliper-chatbot`
   and vice versa. Adapters are siblings, not a graph. If two adapters
   need the same code, the candidate goes to caliper core (rule 3).

3. **Promotion to core requires the rule of three.**
   Code starts in an adapter. If the same abstraction appears in
   two adapters, it becomes a *candidate* for promotion. Promotion
   requires a self-eval test, a doc note, and explicit intent.
   Default is to NOT promote — premature abstraction is the worse
   failure mode.

### Why this shape and not the alternatives

| Choice | Why we rejected it |
|---|---|
| **Monolith** (all scenarios inside `caliper`) | Core balloons to 5000+ lines as scenarios accumulate. Scenario PRs can break core regression tests. The "thin layer" promise dies. This is the LangChain failure mode. |
| **Multi-repo** (separate git repos per scenario) | Premature for a 1-week-old project. 4 repos × 4 CI configs × 4 dependency syncs is friction without payoff at this scale. We can split later if needed (a workspace is a single-direction door — easy to split, hard to merge). |
| **Workspace + multi-package** (current choice) | One clone, one venv, cross-package refactor is one PR, package boundaries are enforced by import rules. The pattern proven by pytest, inspect-ai, sklearn. |

### The typed solver-scorer contract

Solvers and scorers communicate through `state.store`, which is an
untyped dict by default. Caliper defines `caliper.protocols.SolverState`
(a Pydantic-backed `StoreModel`) as the **single source of truth** for
what a solver writes and what scorers read. Both sides access fields
via `state.store_as(SolverState)`:

```python
# In a solver
async def solve(state, generate):
    ss = state.store_as(SolverState)
    ss.agent_answer = "..."
    ss.observed_page = True
    ss.commands_run += 1

# In a scorer
async def score(state, target):
    ss = state.store_as(SolverState)
    return Score(value=bool(ss.agent_answer), explanation=...)
```

This makes the contract enforceable by type. A solver that forgets to
set `agent_answer` produces a default empty string, not a `KeyError`,
and the scorer's expectation is documented in the protocol. Renaming a
field is a single-file change.

### The Strategy axis

`caliper.protocols.Strategy` is a `Protocol` class that defines the
hooks an agent loop calls at decision points that aren't "what tool to
call next" — for example, what to do when the turn budget is exhausted.

Caliper core provides only the protocol. Concrete strategies live in
scenario packages — the chatbot maxTurns scenario is the canonical
first user (`caliper-chatbot/strategies/`), but any future scenario
that needs meta-policies (retry strategies, temperature schedules,
budget allocation) implements the same protocol so reports and A/B
tooling work uniformly across them.

This is the answer to the recurring question "where does X live in
caliper?" — protocols in core, implementations in scenarios.
