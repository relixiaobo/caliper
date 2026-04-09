"""M2.1: Judge self-eval suite.

Runs caliper's LLM judge (score_judge with the default stale-ref-
tolerant prompt) against 50 hand-labeled test cases and measures
agreement with human labels. This is the ground truth for whether
the judge prompt + model combination produces correct verdicts.

**This test calls a real LLM and costs real API money.**
It is NOT part of the normal ``uv run pytest`` suite. Run it
explicitly:

    ANTHROPIC_API_KEY=sk-... uv run pytest tests/self_eval/test_judge_quality.py -v

Or via the self_eval marker:

    uv run pytest -m self_eval -v

Expected cost: ~50 calls × ~500 input tokens × ~50 output tokens
≈ 25K input + 2.5K output tokens ≈ $0.10 on Sonnet.

Target: ≥90% agreement (45/50). If below 90%, the judge prompt
needs revision before any baseline numbers can be trusted.

The 50 test cases cover 8 categories:
  - exact_correct: agent matches reference exactly
  - clear_incorrect: agent gives a wrong answer
  - stale_ref_tolerance: agent is right for today, ref is outdated
  - partial_answer: agent covers some but not all key info
  - describe_dont_do: agent describes how to find the answer
  - fabrication: agent invents specific details
  - empty_evasive: agent dodges or gives no answer
  - edge_case: formatting differences, numerical equivalence, etc.

Each case was hand-labeled by a human. The labels are the ground
truth; the judge is being measured against them.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from caliper.runtime import load_dotenv
from caliper.scoring import score_judge

# Self-eval tests are opt-in (cost money, need API key).
pytestmark = pytest.mark.self_eval

DATA_PATH = Path(__file__).parent / "judge_quality_data.jsonl"

# ---------------------------------------------------------------------------
# Load .env and skip if no API key
# ---------------------------------------------------------------------------

load_dotenv()  # pick up ANTHROPIC_API_KEY from .env if not in shell

if not os.environ.get("ANTHROPIC_API_KEY"):
    pytest.skip(
        "ANTHROPIC_API_KEY not set (checked shell + .env) — "
        "skipping judge self-eval (costs API money)",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Load test cases
# ---------------------------------------------------------------------------


def _load_cases() -> list[dict]:
    cases = []
    for line in DATA_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


CASES = _load_cases()
CASE_IDS = [c["id"] for c in CASES]


# ---------------------------------------------------------------------------
# Per-case parametrized test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_judge_verdict(case: dict):
    """Run score_judge on one hand-labeled case and check agreement."""
    result = asyncio.run(
        score_judge(
            goal=case["goal"],
            agent_answer=case["agent_answer"],
            reference_answer=case["reference"],
        )
    )

    expected_pass = case["expected"] == "correct"
    actual_pass = result.passed

    # Collect metadata for the summary test below.
    # (pytest doesn't have a great way to aggregate across parametrized
    # tests, so we also run the full suite in test_overall_accuracy.)
    assert actual_pass == expected_pass, (
        f"[{case['id']}] ({case['category']}): "
        f"expected {'CORRECT' if expected_pass else 'INCORRECT'}, "
        f"got {'CORRECT' if actual_pass else 'INCORRECT'}. "
        f"reason: {result.reason}"
    )


# ---------------------------------------------------------------------------
# Overall accuracy test
# ---------------------------------------------------------------------------


def test_overall_accuracy():
    """Run all 50 cases and assert ≥90% agreement.

    This test runs even if individual parametrized tests fail —
    the per-case tests give you the detail, this one gives you the
    headline number. Both are useful.
    """
    agreements = 0
    disagreements: list[dict] = []
    by_category: Counter[str] = Counter()
    by_category_wrong: Counter[str] = Counter()

    for case in CASES:
        result = asyncio.run(
            score_judge(
                goal=case["goal"],
                agent_answer=case["agent_answer"],
                reference_answer=case["reference"],
            )
        )
        expected_pass = case["expected"] == "correct"
        actual_pass = result.passed
        by_category[case["category"]] += 1

        if actual_pass == expected_pass:
            agreements += 1
        else:
            disagreements.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected": case["expected"],
                    "got": "correct" if actual_pass else "incorrect",
                    "reason": result.reason[:100],
                }
            )
            by_category_wrong[case["category"]] += 1

    total = len(CASES)
    accuracy = agreements / total
    target = 0.90

    # Print summary regardless of pass/fail.
    print(f"\n{'=' * 60}")
    print(f"Judge self-eval: {agreements}/{total} = {accuracy:.1%}")
    print(f"Target: ≥{target:.0%}")
    print(f"{'=' * 60}")

    if disagreements:
        print(f"\nDisagreements ({len(disagreements)}):")
        for d in disagreements:
            print(
                f"  [{d['id']}] ({d['category']}): "
                f"expected {d['expected']}, got {d['got']} "
                f"— {d['reason']}"
            )

    print(f"\nPer-category accuracy:")
    for cat in sorted(by_category):
        wrong = by_category_wrong.get(cat, 0)
        right = by_category[cat] - wrong
        print(f"  {cat:<25} {right}/{by_category[cat]}")

    assert accuracy >= target, (
        f"Judge accuracy {accuracy:.1%} < target {target:.0%}. "
        f"{len(disagreements)} disagreements — see output above."
    )
