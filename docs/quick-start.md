# Quick Start: Evaluate Your Agent with Caliper

5 minutes to get caliper measuring your agent's outputs. No Inspect AI
eval loop needed, no browser, no bp.

## Install

```bash
# From source (until caliper is on PyPI):
git clone https://github.com/relixiaobo/caliper.git
cd caliper
uv sync
```

## Option A: Python API (recommended)

```python
import asyncio
from caliper import CaliperEvaluator, CaliperRecord

# 1. Your agent runs, you capture the outputs as CaliperRecords:
records = [
    CaliperRecord(
        sample_id="task-1",
        bucket="lookup",                        # your task category
        goal="What is 2+2?",                    # what the agent was asked
        agent_answer="4",                       # what the agent said
        observed=True,                          # did it actually look?
    ),
    CaliperRecord(
        sample_id="task-2",
        bucket="lookup",
        goal="Capital of France?",
        agent_answer="Paris",
        observed=False,                         # answered without looking = lazy
    ),
]

# 2. One line to evaluate:
evaluator = CaliperEvaluator()
report = asyncio.run(evaluator.evaluate(records))

# 3. Use the results:
print(f"Pass rate: {report.overall.pass_rate:.0%}")   # 100%
print(f"Lazy rate: {report.overall.lazy_rate:.0%}")    # 50%
```

## Option B: CLI (any language)

Your agent produces a JSON file:

```json
[
  {
    "sample_id": "task-1",
    "bucket": "lookup",
    "goal": "What is 2+2?",
    "agent_answer": "4",
    "observed": true
  },
  {
    "sample_id": "task-2",
    "bucket": "lookup",
    "goal": "Capital of France?",
    "agent_answer": "Paris",
    "observed": false
  }
]
```

Then:

```bash
uv run caliper score records.json
```

Output:

```
bucket       │ pass         │ lazy     │    mean tokens │    uncached in │  cache hit
─────────────┼──────────────┼──────────┼────────────────┼────────────────┼───────────
lookup       │ 2/2 100.0%   │ 1 (50%)  │              0 │              0 │          —
─────────────┼──────────────┼──────────┼────────────────┼────────────────┼───────────
TOTAL        │ 2/2 100.0%   │ 1 (50%)  │              0 │              0 │          —
```

Save as JSON:

```bash
uv run caliper score records.json --output report.json
```

## Adding an LLM judge

If your tasks have reference answers, caliper can run an LLM judge:

```python
records = [
    CaliperRecord(
        sample_id="math-1",
        bucket="lookup",
        goal="Derivative of x^2 at x=5.6?",
        agent_answer="2 * 5.6 = 11.2",
        observed=True,
        reference_answer="11.2",        # ← add this
    ),
]

# Needs ANTHROPIC_API_KEY (or configure a different judge model)
evaluator = CaliperEvaluator(judge_model="anthropic/claude-sonnet-4-6")
report = await evaluator.evaluate(records)
```

The judge uses caliper's built-in stale-ref-tolerant prompt — it won't
penalize agents that give correct-but-updated answers when a reference
is outdated.

## Adding deterministic verification

For tasks with checkable outcomes (DOM state, API response, file content):

```python
records = [
    CaliperRecord(
        sample_id="login-1",
        bucket="smoke",
        goal="Log in with username admin",
        agent_answer="Done",
        observed=True,
        # Pre-computed checks (your project already verified these):
        verify_results=[
            {"passed": True, "description": "success message shown"},
            {"passed": True, "description": "URL is /dashboard"},
        ],
    ),
]
```

No API key needed for verify-only scoring.

## A/B comparison

Compare two runs with caliper's 2σ noise floor:

```python
report_a = await evaluator.evaluate(records_v1)
report_b = await evaluator.evaluate(records_v2)

diff = evaluator.diff(report_a, report_b)
print(diff.overall.pass_rate.classification)  # "real" | "noise" | "no estimate"
```

CLI:

```bash
uv run caliper score records_v1.json -o report_a.json
uv run caliper score records_v2.json -o report_b.json
# (caliper diff currently works with .eval files; JSON diff coming in Phase 2)
```

## CaliperRecord fields

| Field | Required | Purpose |
|---|---|---|
| `sample_id` | yes | Per-sample failure attribution |
| `bucket` | yes | Per-group aggregation |
| `goal` | yes | Task description (fed to LLM judge) |
| `agent_answer` | yes | Agent's answer (empty = failure) |
| `observed` | yes | Did agent observe target? (lazy detection) |
| `reference_answer` | no | For LLM judge. Empty = skip judge |
| `verify_specs` | no | CLI commands for caliper to run |
| `verify_results` | no | Pre-computed check results |
| `input_tokens` | no | For token metrics |
| `output_tokens` | no | For token metrics |
| `cache_read_tokens` | no | For cache hit rate |
| `has_cache_info` | no | True = token fields are real data |
| `epoch` | no | For N≥2 variance measurement |
| `metadata` | no | Project-specific data (passed through) |

## What caliper guarantees

No matter how you integrate, these methodology principles are enforced:

- **Lazy detection always runs** (`observed` is mandatory)
- **Empty answer = explicit failure** (not silently skipped)
- **N≥2 for statistical claims** (diff returns "no estimate" at N=1)
- **2σ noise floor** for A/B comparisons
- **Per-sample failure attribution** in every report

## Full example

See [`examples/standalone_eval.py`](../examples/standalone_eval.py)
for a runnable demo with all three modes (lazy-only, verify, LLM judge)
and an A/B comparison.

## Next steps

- [Architecture](architecture.md) — two integration modes explained
- [Methodology](methodology.md) — the 5 principles behind caliper
- [Roadmap](roadmap.md) — what's coming in Phase 2+
