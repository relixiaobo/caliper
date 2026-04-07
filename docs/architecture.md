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

## What lives where

### Inspect AI provides (we don't write)

- The agent loop infrastructure
- Multi-provider model client with cache token reporting
- Sandboxed tool execution
- Sample/Dataset abstractions
- Eval orchestration and parallelism
- The web viewer for trace inspection

### Caliper provides (the ~500 lines we write)

- **Scorers** that encode the methodology:
  - `judge_stale_ref_tolerant` — judge with anti-substring-bug parsing and
    stale-reference handling for time-sensitive tasks
  - `lazy_detection` — observation-based check that catches "describe but
    don't do" agent cheating
  - `json_verdict` — robust JSON verdict parser, handles markdown fences,
    falls back to keyword matching with INCORRECT-first ordering
  - `cost_threshold` — flag runs that exceed a $ budget
- **Solvers** for non-standard agent loops:
  - `text_protocol_agent` — wraps a CLI tool, parses commands from LLM free
    text, suitable for any subprocess-based tool
- **Metrics**:
  - `cost_calculator` — converts Inspect AI's I/CW/CR/O fields to $ using
    a pinned-date pricing table
  - `cache_hit_rate` — first-class metric on top of token breakdown
  - `effective_tokens` — single-number cost comparison across configs with
    different cache patterns
- **Report layer**:
  - `bucket_report` — aggregate by `metadata.bucket` for per-category metrics
  - `ab_compare` — diff two `.eval` log files, flag noise-floor regressions
  - `regression_check` — for CI: refuse to merge if a baseline metric drops
    by more than the noise floor
- **Datasets**:
  - `webvoyager_loader` — convert WebVoyager JSONL to Inspect Samples with
    metadata bucket tags

## What consumers provide

A consumer project (like `browser-pilot/eval/`) writes:

1. A **task definition** (`@task` function) that wires together a solver, a
   scorer, and a dataset.
2. A **dataset** of `Sample` objects (`input`, `target`, `metadata`).
3. Project-specific **adapter code** if the tool isn't already wrapped by
   one of caliper's solvers.

That's it. Everything else — the agent loop, the LLM calls, the cache
tracking, the variance enforcement, the report — comes from the stack below.

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

## Repository layout

```
caliper/
├── README.md
├── LICENSE
├── pyproject.toml
├── docs/                   # this directory
├── src/caliper/            # added in Phase 1
│   ├── solvers/
│   ├── scorers/
│   ├── metrics/
│   ├── report/
│   └── datasets/
├── tests/
│   ├── unit/               # traditional unit tests
│   └── self_eval/          # caliper testing caliper
└── examples/
    └── quickstart.md
```

The consumer side (browser-pilot, chatbot-bench) lives in the consumer's own
repository, importing caliper as a Python dependency.
