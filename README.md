# Caliper

> Evidence-based iteration for agent stacks.

Caliper is a measurement layer for agent evaluation. It provides the
discipline you need when iterating on an agent system: variance measurement,
LLM judge with anti-bug parsing, lazy-behavior detection, token & cache
tracking, deterministic post-hoc verification, and bucketed A/B comparison
with statistical rigor.

**Any agent project can plug into caliper** — either via the Inspect AI eval
loop (full mode) or via the standalone `CaliperRecord` API (measurement-only
mode). Both modes share the same scoring logic.

## Why does this exist

Building agents is easy. **Knowing whether your last change made things better
is hard.** Most teams iterate on tools, prompts, and strategies based on
intuition because there's no cheap way to A/B test a single design decision
with statistical rigor.

Caliper was extracted from 8 weeks of iterating on
[browser-pilot](https://github.com/relixiaobo/browser-pilot). Across those 8
rounds we discovered that the highest-leverage improvements weren't in the
agent loop or the tools — they were in the **measurement layer**. Three of the
biggest wins came from finding bugs in *how we measured*, not in how we built.

Caliper bakes those measurement-discipline lessons into a reusable framework so
you don't have to rediscover them.

## Two ways to integrate

### Mode A: Full mode (Inspect AI eval loop)

Your project defines tasks and runs via `inspect eval`:

```python
from caliper.solvers import text_protocol_agent
from caliper.scorers import judge_stale_ref, lazy_detection

@task
def my_eval():
    return Task(
        dataset=my_dataset(),
        solver=text_protocol_agent(cli_name="my-tool", ...),
        scorer=[judge_stale_ref(), lazy_detection()],
    )
```

```bash
inspect eval tasks.py@my_eval --model anthropic/claude-sonnet-4-6
caliper report logs/latest.eval
```

### Mode B: Measurement-only mode (standalone API)

Your project runs its own agent loop and feeds results to caliper:

```python
from caliper import CaliperEvaluator, CaliperRecord

evaluator = CaliperEvaluator(judge_model="anthropic/claude-sonnet-4-6")

records = [
    CaliperRecord(
        sample_id="task-1",
        bucket="lookup",
        goal="What is the derivative of x^2 at x=5.6?",
        agent_answer="11.2",
        observed=True,
        reference_answer="11.2",
    ),
]

report = await evaluator.evaluate(records)
print(report.overall.pass_rate)
```

Or via CLI (any language can produce the JSON):

```bash
caliper score records.json --output report.json
```

## What it gives you

- **Structured LLM judge** with anti-substring-bug JSON parsing and
  stale-reference tolerance for time-sensitive benchmarks
- **Lazy detection**: catches agents that answer from training data without
  looking at the target
- **Deterministic verification** (`verify_commands`): post-hoc DOM/CLI checks
  for Layer 1 smoke tests — no LLM judge needed, fast and free
- **Token & cache tracking**: cross-provider `UsageSummary` with
  `cache_hit_rate` and honesty flags
- **Variance measurement**: N≥2 enforced; diff refuses to call a delta "real"
  at N=1
- **Bucketed reporting**: per-task-category pass/lazy/tokens breakdown
- **A/B comparison**: 2σ noise floor, cache regression warnings
- **Session hygiene**: `session_prologue` resets tool state between samples
  (e.g. bp disconnect/connect to prevent Chrome tab pollution)
- **Self-evaluation**: caliper's own components are tested with caliper

## What it doesn't do

- It's **not an agent framework** (use Inspect AI / LangChain / CrewAI for that)
- It's **not a benchmark dataset** (it works with WebVoyager, your own tasks,
  deterministic fixtures, mock tasks)
- It's **not a model provider** (Inspect AI handles that)

## Status

**Phase 1 complete** (M0.1 → M1.7b). Phase 2 (self-eval) in progress.

| Metric | Value |
|---|---|
| Core production code | ~1,200 lines |
| Tests | 243 passing |
| Scorers | 3 (judge_stale_ref, lazy_detection, verify_commands) |
| CLI commands | 3 (report, diff, score) |
| Integration modes | 2 (Inspect AI full mode + CaliperRecord standalone) |
| v9 baseline | 19/24 Sonnet, with 4-round post-mortem correction chain |

Current workspace structure (adapters planned to move to their own repos
after Phase 2 — see [roadmap M3.0](docs/roadmap.md)):

| Package | Role | Status |
|---|---|---|
| `caliper` | Core framework — scoring, evaluator, protocols, parsers, solvers, metrics, report, CLI | Phase 1 complete |
| `caliper-browser-pilot` | Adapter for the `bp` CLI | Phase 1 complete; 4 smoke + 12 v8 tasks |
| `caliper-computer-pilot` | Adapter for the `cu` CLI | Skeleton; Phase 3a |
| `caliper-chatbot` | Scenario for chatbot maxTurns A/B | Skeleton; Phase 3b |

## Quick links

- **[Quick Start](docs/quick-start.md) — evaluate your agent in 5 minutes**
- [Why this exists](docs/why.md) — the case for evidence-based iteration
- [Methodology](docs/methodology.md) — the 5 core principles
- [Architecture](docs/architecture.md) — two integration modes, what lives where
- [Roadmap](docs/roadmap.md) — phases, milestones, adapter split plan
- [Lessons learned](docs/lessons-learned.md) — the 8-week story + Phase 1 post-mortems
- [Test sets](docs/test-sets.md) — where tasks come from, the 3-layer strategy
- [Self-evaluation](docs/self-evaluation.md) — how caliper tests itself
- [Chatbot maxTurns scenario](docs/chatbot-maxturns.md) — the worked Phase 3b example

## License

MIT — see [LICENSE](LICENSE).
