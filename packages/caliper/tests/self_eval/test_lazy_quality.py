"""M2.2: Lazy detection self-eval suite.

30 hand-labeled test cases verifying that ``score_lazy`` correctly
identifies agents that answered without observing the target
environment. Unlike M2.1 (judge self-eval), this suite is
**deterministic** — no LLM calls, no API cost, runs in <1 second.

The logic being tested is trivially simple:
    is_lazy = bool(agent_answer) and not observed

But the VALUE of this suite is:
1. Pinning the exact decision boundary so a refactor can't silently
   change what "lazy" means
2. Documenting real-world cases from v9 and M1.6b traces so the
   rationale for each decision is on record
3. Covering edge cases (whitespace, unicode, JSON-formatted answers,
   evasive responses) that could trip a naive implementation

Target: 100% accuracy (it's deterministic boolean logic).

Run:
    uv run pytest tests/self_eval/test_lazy_quality.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from caliper.scoring import score_lazy

DATA_PATH = Path(__file__).parent / "lazy_detection_data.jsonl"


def _load_cases() -> list[dict]:
    cases = []
    for line in DATA_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


CASES = _load_cases()
CASE_IDS = [c["id"] for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_lazy_detection(case: dict):
    """Run score_lazy on one hand-labeled case."""
    result = score_lazy(case["agent_answer"], case["observed"])
    assert result == case["expected_lazy"], (
        f"[{case['id']}]: expected lazy={case['expected_lazy']}, "
        f"got {result}. answer={case['agent_answer']!r:.50}, "
        f"observed={case['observed']}. notes: {case['notes']}"
    )


def test_overall_accuracy():
    """All 30 cases must agree — lazy detection is deterministic."""
    total = len(CASES)
    assert total >= 30, f"Need ≥30 cases, have {total}"

    failures = []
    for case in CASES:
        result = score_lazy(case["agent_answer"], case["observed"])
        if result != case["expected_lazy"]:
            failures.append(case["id"])

    assert not failures, (
        f"{len(failures)}/{total} disagreements: {failures}. "
        "Lazy detection is deterministic — 100% is the only "
        "acceptable accuracy."
    )


def test_balanced_labels():
    """Sanity: the dataset has both lazy and non-lazy examples."""
    n_lazy = sum(1 for c in CASES if c["expected_lazy"])
    n_not = sum(1 for c in CASES if not c["expected_lazy"])
    assert n_lazy >= 10, f"Need ≥10 lazy cases, have {n_lazy}"
    assert n_not >= 10, f"Need ≥10 non-lazy cases, have {n_not}"
