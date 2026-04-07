# Self-Evaluation

> A framework that can't evaluate itself isn't trustworthy.

## The principle

Caliper's components — judge prompts, lazy detectors, cost wrappers,
verdict parsers — are themselves LLM-related artifacts. They benefit from
the same iteration discipline that caliper applies to agent stacks.

If we change a judge prompt, we should be able to ask: "did this change
make the judge more accurate, less accurate, or about the same?"

If we tweak the lazy detection rule, we should know its precision and
recall on a labeled dataset of (trace, is_lazy) pairs.

If we update a pricing table, we should verify the cost calculation
matches actual provider invoices.

**Caliper provides this self-test ability through the same task/scorer
machinery it gives consumers.** It dogfoods itself.

## Why this matters

The single biggest measurement bug in browser-pilot's 8 weeks of iteration
was the `"CORRECT" in "INCORRECT"` substring trap (see
[lessons-learned.md](lessons-learned.md)). It silently inflated 38% of all
judge results across 4 versions.

If we'd had a self-evaluation suite for the judge from day 1 — even a
single test case where the agent answer was clearly wrong and the expected
verdict was INCORRECT — we'd have caught the bug in minutes instead of
weeks.

This is the kind of bug that **only the framework can catch about itself**,
because the consumer assumes the framework is correct.

## Structure

Caliper's `tests/` directory has two layers:

```
tests/
├── unit/             # Traditional pytest unit tests
│   ├── test_extract_bp_commands.py
│   ├── test_truncate_snapshot.py
│   ├── test_pricing_table.py
│   └── test_json_verdict_parser.py    # ← regression test for the substring bug
└── self_eval/        # Caliper tasks that test caliper components
    ├── judge_quality.py
    ├── lazy_detection_quality.py
    ├── cost_accuracy.py
    └── stale_ref_tolerance.py
```

The `unit/` layer is conventional: small, deterministic, fast, no LLM calls.

The `self_eval/` layer is **caliper Tasks that score caliper components**.
Each one is a real evaluation, with hand-labeled samples, that can be run
with `caliper eval tests/self_eval/<file>`.

## Concrete example: judge self-evaluation

The `judge_stale_ref_tolerant` scorer is the most subtle and bug-prone
component in caliper. Here's how we test it.

### The dataset

```python
# tests/self_eval/judge_quality.py
from inspect_ai.dataset import Sample

JUDGE_TEST_CASES = [
    # Category 1: stale reference, correct current answer → should PASS
    Sample(
        id="apple_macbook_m5_correct",
        input={
            "task_goal": "Find the latest MacBook Air price on Apple's website",
            "reference_answer": "MacBook Air M2 from $1099",  # 2023 ref
            "agent_answer": "MacBook Air M5 starts at $1099",  # 2026 reality
        },
        target="correct",
        metadata={"category": "stale_ref_tolerated"},
    ),

    # Category 2: stale reference, agent fabricated answer → should FAIL
    Sample(
        id="apple_macbook_fabricated",
        input={
            "task_goal": "Find the latest MacBook Air price on Apple's website",
            "reference_answer": "MacBook Air M2 from $1099",
            "agent_answer": "MacBook Air costs around $50",  # nonsense
        },
        target="incorrect",
        metadata={"category": "obvious_wrong"},
    ),

    # Category 3: describe-don't-do (the GPT-5.4 cheat pattern)
    Sample(
        id="describes_navigation_only",
        input={
            "task_goal": "Find the current NBA Eastern Conference standings",
            "reference_answer": "<standings>",
            "agent_answer": "Run `bp open https://www.espn.com/nba/standings` to see standings",
        },
        target="incorrect",
        metadata={"category": "describes_dont_do"},
    ),

    # Category 4: non-stale fact, correct match → should PASS
    Sample(
        id="cambridge_zeitgeist_correct",
        input={
            "task_goal": "Look up the pronunciation and definition of 'zeitgeist'",
            "reference_answer": "UK: /ˈtsaɪt.ɡaɪst/, US: /ˈtsaɪt.ɡaɪst/; the general set of ideas",
            "agent_answer": "zeitgeist: pronounced /ˈtsaɪt.ɡaɪst/, meaning the general set of ideas",
        },
        target="correct",
        metadata={"category": "factual_match"},
    ),

    # Category 5: non-stale fact, wrong answer → should FAIL
    Sample(
        id="cambridge_wrong_definition",
        input={
            "task_goal": "Look up the pronunciation and definition of 'zeitgeist'",
            "reference_answer": "UK: /ˈtsaɪt.ɡaɪst/, US: /ˈtsaɪt.ɡaɪst/; the general set of ideas",
            "agent_answer": "zeitgeist means a type of German bread",  # wrong
        },
        target="incorrect",
        metadata={"category": "factual_wrong"},
    ),

    # Category 6: empty answer
    Sample(
        id="empty_answer",
        input={
            "task_goal": "...",
            "reference_answer": "anything",
            "agent_answer": "",
        },
        target="incorrect",
        metadata={"category": "empty"},
    ),

    # ... more cases for each category, aiming for ≥10 per category
]
```

### The task

```python
from inspect_ai import task, Task
from inspect_ai.scorer import exact_match
from caliper.scorers import judge_stale_ref_tolerant

@task
def judge_quality_self_eval():
    """Run the judge against hand-labeled cases and score it with exact_match."""
    return Task(
        dataset=JUDGE_TEST_CASES,
        # The "solver" here just calls the judge under test
        solver=judge_under_test(judge_stale_ref_tolerant()),
        # The "scorer" here is exact_match: did the judge agree with the label?
        scorer=exact_match(),
    )
```

### The result

Running `caliper eval tests/self_eval/judge_quality.py` produces:

```
Judge self-evaluation results
─────────────────────────────────────────────
category                   pass    accuracy
stale_ref_tolerated        10/10   100%
obvious_wrong              10/10   100%
describes_dont_do          9/10    90%
factual_match              10/10   100%
factual_wrong              10/10   100%
empty                      10/10   100%
─────────────────────────────────────────────
TOTAL                      59/60   98%
```

The one failure in `describes_dont_do` becomes a known limitation, tracked
in an issue, and a regression target for the next judge prompt iteration.

## Other self-evaluation suites

### `lazy_detection_quality`

Hand-labeled traces:
- 20 traces where the agent observed pages and gave real answers (`is_lazy=False`)
- 10 traces where the agent answered without observation (`is_lazy=True`)
- 5 borderline cases (e.g., agent ran one observation command but didn't
  use the result)

Metric: precision (no false positives — never call a real run lazy) and
recall (catch every actual lazy run).

### `cost_accuracy`

Run a fixed set of caliper tasks for one week. At the end of the week,
compare:

- Sum of `cost_usd` reported by caliper for those runs
- The actual delta on the Anthropic / OpenAI invoice for the same period

These should agree to within 5%. Larger discrepancies indicate either a
pricing table error or a missing token category.

### `stale_ref_tolerance`

A subset of `judge_quality` focused only on the stale-reference tolerance
rule. Distinguishes:

- True stale ref + correct current answer → judge should accept
- True stale ref + wrong current answer → judge should reject
- Non-stale ref + correct answer → judge should accept (control)
- Non-stale ref + wrong answer → judge should reject (control)

### `json_verdict_parser_robustness`

Lots of weird LLM outputs that the verdict parser must handle:
- Plain `{"verdict": "correct"}`
- Markdown-fenced JSON
- Free text "INCORRECT" without JSON
- Free text "I think this is correct"
- "Correct" inside a longer explanation
- Empty response
- Response with only reasoning, no verdict

For each, the expected behavior is documented. Any change to the parser
must keep all of these passing.

## When self-evaluation runs

- **On every commit** that touches `src/caliper/scorers/` — CI runs the full
  self-evaluation suite. If the score drops, the PR is blocked.
- **On every release** — full self-eval is part of the release process,
  results published in the release notes.
- **Periodically** — even without code changes, run weekly to catch model
  drift (the same judge LLM might score the same case differently after a
  provider model update).

## The meta-claim

If caliper can't evaluate caliper, then caliper isn't trustworthy enough
to evaluate anything else. This is a forcing function on the design: every
component must be testable using the framework's own primitives. If a
component can't be tested this way, it's a sign the abstraction is wrong.

This is the strongest test of generality we have.

## What this is not

Self-evaluation is **not** the same as unit testing. Unit tests verify
individual functions are correct. Self-evaluation verifies that the
**LLM-facing components** (judges, lazy detectors, cost wrappers) work
correctly across realistic distributions of inputs — which requires
labeled samples, not just function-level assertions.

Both layers exist in caliper. They serve different purposes:

| Layer | Purpose | Where |
|---|---|---|
| Unit tests | Function-level correctness | `tests/unit/` |
| Self-evaluation | Component-level accuracy on realistic LLM outputs | `tests/self_eval/` |

## A worked example: catching the substring bug

If we'd had `tests/unit/test_json_verdict_parser.py` from day 1 with this
test case:

```python
def test_incorrect_is_not_parsed_as_correct():
    """Regression test for the v0-v4 substring bug."""
    verdict, _ = parse_verdict("INCORRECT")
    assert verdict is False, "INCORRECT should not be parsed as correct"

    verdict, _ = parse_verdict('{"verdict": "incorrect"}')
    assert verdict is False
```

…we would have caught the bug in 30 seconds. As it stands, we found it
after 8 weeks and 4 versions of "improvement" that turned out to be
illusion.

This single test case is **the most valuable line of code in caliper**.
It encodes the lesson that took us 8 weeks to learn.
