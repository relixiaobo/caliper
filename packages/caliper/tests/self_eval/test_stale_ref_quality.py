"""M2.4: Stale-ref tolerance self-eval — 4-quadrant analysis.

Tests the judge's ability to distinguish 4 quadrants:

    Q1: non-stale reference + correct answer   → CORRECT
    Q2: non-stale reference + wrong answer      → INCORRECT
    Q3: stale reference + factually current answer → CORRECT (tolerance)
    Q4: stale reference + wrong answer          → INCORRECT

Q3 is the critical quadrant — it's where the judge must ACCEPT an
answer that differs from the reference because the reference is
outdated. M2.1 found 2 failures in this quadrant:
  - stale-04: ranking queries ("most liked model on HF")
  - stale-06: "most recent" content ("latest arXiv paper")

This suite expands Q3 coverage with more ranking and "most recent"
cases to measure the specific failure rate on that pattern.

**This test calls a real LLM and costs API money.**
Run explicitly:

    uv run pytest tests/self_eval/test_stale_ref_quality.py -v -s

Expected cost: ~20 calls × ~500 tokens ≈ ~$0.05
Target: ≥90% overall, with Q3 breakdown reported separately.
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

pytestmark = pytest.mark.self_eval

DATA_PATH = Path(__file__).parent / "stale_ref_data.jsonl"

load_dotenv()

if not os.environ.get("ANTHROPIC_API_KEY"):
    pytest.skip(
        "ANTHROPIC_API_KEY not set — skipping stale-ref self-eval",
        allow_module_level=True,
    )


def _load_cases() -> list[dict]:
    return [
        json.loads(line) for line in DATA_PATH.read_text().splitlines() if line.strip()
    ]


CASES = _load_cases()
CASE_IDS = [c["id"] for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_stale_ref_verdict(case: dict):
    result = asyncio.run(
        score_judge(
            goal=case["goal"],
            agent_answer=case["agent_answer"],
            reference_answer=case["reference"],
        )
    )
    expected_pass = case["expected"] == "correct"
    assert result.passed == expected_pass, (
        f"[{case['id']}] ({case['quadrant']}): "
        f"expected {'CORRECT' if expected_pass else 'INCORRECT'}, "
        f"got {'CORRECT' if result.passed else 'INCORRECT'}. "
        f"reason: {result.reason}"
    )


def test_overall_and_per_quadrant_accuracy():
    """Run all cases and report accuracy overall + per quadrant.
    Target: ≥90% overall. Q3 (stale_correct) is reported separately
    because it's where the M2.1 weaknesses live."""
    agreements = 0
    disagreements: list[dict] = []
    by_quad: Counter[str] = Counter()
    by_quad_wrong: Counter[str] = Counter()

    for case in CASES:
        result = asyncio.run(
            score_judge(
                goal=case["goal"],
                agent_answer=case["agent_answer"],
                reference_answer=case["reference"],
            )
        )
        expected_pass = case["expected"] == "correct"
        by_quad[case["quadrant"]] += 1

        if result.passed == expected_pass:
            agreements += 1
        else:
            disagreements.append(
                {
                    "id": case["id"],
                    "quadrant": case["quadrant"],
                    "expected": case["expected"],
                    "got": "correct" if result.passed else "incorrect",
                    "reason": result.reason[:100],
                }
            )
            by_quad_wrong[case["quadrant"]] += 1

    total = len(CASES)
    accuracy = agreements / total

    print(f"\n{'=' * 60}")
    print(f"Stale-ref self-eval: {agreements}/{total} = {accuracy:.1%}")
    print(f"{'=' * 60}")

    if disagreements:
        print(f"\nDisagreements ({len(disagreements)}):")
        for d in disagreements:
            print(
                f"  [{d['id']}] ({d['quadrant']}): expected {d['expected']}, got {d['got']} — {d['reason']}"
            )

    print(f"\nPer-quadrant accuracy:")
    for quad in [
        "non_stale_correct",
        "non_stale_wrong",
        "stale_correct",
        "stale_wrong",
        "plausible_but_false",
    ]:
        wrong = by_quad_wrong.get(quad, 0)
        right = by_quad[quad] - wrong
        n = by_quad[quad]
        marker = " ← M2.1 weakness area" if quad == "stale_correct" else ""
        print(f"  {quad:<22} {right}/{n}{marker}")

    assert accuracy >= 0.90, (
        f"Stale-ref accuracy {accuracy:.1%} < 90%. {len(disagreements)} disagreements."
    )
