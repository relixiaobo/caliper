"""Tests for CaliperEvaluator — the standalone evaluation API.

These test the full pipeline: CaliperRecord → score → aggregate →
BucketReport, without touching Inspect AI's eval loop. The LLM judge
is mocked; everything else runs for real.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from caliper import CaliperEvaluator, CaliperRecord


def _make_records(
    n: int = 4,
    *,
    bucket: str = "smoke",
    observed: bool = True,
    with_reference: bool = False,
    with_verify: bool = False,
    agent_answer: str = "done",
) -> list[CaliperRecord]:
    """Build a batch of test records."""
    records = []
    for i in range(n):
        r = CaliperRecord(
            sample_id=f"t{i}",
            bucket=bucket,
            goal=f"do thing {i}",
            agent_answer=agent_answer,
            observed=observed,
            epoch=1,
            input_tokens=1000 * (i + 1),
            output_tokens=200,
            has_cache_info=True,
        )
        if with_reference:
            r.reference_answer = f"answer {i}"
        if with_verify:
            r.verify_results = [{"passed": True, "description": f"check {i}"}]
        records.append(r)
    return records


# ---------------------------------------------------------------------------
# Lazy-only mode (no judge, no verify)
# ---------------------------------------------------------------------------


def test_evaluate_lazy_only_all_pass():
    """Records with agent_answer + observed=True → all pass, none lazy."""
    evaluator = CaliperEvaluator()
    records = _make_records(4)
    report = asyncio.run(evaluator.evaluate(records, task_name="test"))

    assert report.overall.n_runs == 4
    assert report.overall.pass_count == 4
    assert report.overall.pass_rate == 1.0
    assert report.overall.lazy_count == 0
    assert report.task_name == "test"


def test_evaluate_lazy_detected():
    """Records with observed=False → lazy, and in lazy-only mode
    still counted as 'passed' (agent_answer non-empty) because there's
    no judge to override."""
    evaluator = CaliperEvaluator()
    records = _make_records(2, observed=False)
    report = asyncio.run(evaluator.evaluate(records))

    # In lazy-only mode: pass = bool(agent_answer), lazy = separate
    assert report.overall.pass_count == 2  # agent_answer is non-empty
    assert report.overall.lazy_count == 2  # but lazy because not observed


def test_evaluate_empty_answer_fails():
    """Empty agent_answer → not passed (even without a judge)."""
    evaluator = CaliperEvaluator()
    records = _make_records(2, agent_answer="")
    report = asyncio.run(evaluator.evaluate(records))

    assert report.overall.pass_count == 0


def test_evaluate_empty_records_raises():
    evaluator = CaliperEvaluator()
    import pytest

    with pytest.raises(ValueError, match="no records"):
        asyncio.run(evaluator.evaluate([]))


# ---------------------------------------------------------------------------
# With LLM judge (mocked)
# ---------------------------------------------------------------------------


def _mock_judge(passed: bool):
    """Patch score_judge to return a fixed result."""
    from caliper.record import JudgeResult

    result = JudgeResult(passed=passed, reason="mock", raw_response="mock")
    return patch(
        "caliper.evaluator.score_judge",
        new_callable=lambda: AsyncMock(return_value=result),
    )


def test_evaluate_with_judge_passing():
    evaluator = CaliperEvaluator()
    records = _make_records(3, with_reference=True)

    with _mock_judge(passed=True):
        report = asyncio.run(evaluator.evaluate(records))

    assert report.overall.pass_count == 3
    assert report.overall.pass_rate == 1.0


def test_evaluate_with_judge_failing():
    evaluator = CaliperEvaluator()
    records = _make_records(3, with_reference=True)

    with _mock_judge(passed=False):
        report = asyncio.run(evaluator.evaluate(records))

    assert report.overall.pass_count == 0


# ---------------------------------------------------------------------------
# With verify results (pre-computed)
# ---------------------------------------------------------------------------


def test_evaluate_with_precomputed_verify():
    """Pre-computed verify results bypass run_cli entirely."""
    evaluator = CaliperEvaluator()
    records = _make_records(2, with_verify=True)
    report = asyncio.run(evaluator.evaluate(records))

    assert report.overall.pass_count == 2
    assert report.overall.pass_rate == 1.0


def test_evaluate_with_failing_verify():
    evaluator = CaliperEvaluator()
    records = [
        CaliperRecord(
            sample_id="t1",
            bucket="smoke",
            goal="check boxes",
            agent_answer="done",
            observed=True,
            verify_results=[{"passed": False, "description": "checkbox unchecked"}],
        )
    ]
    report = asyncio.run(evaluator.evaluate(records))
    assert report.overall.pass_count == 0


# ---------------------------------------------------------------------------
# Bucket aggregation
# ---------------------------------------------------------------------------


def test_evaluate_groups_by_bucket():
    evaluator = CaliperEvaluator()
    records = _make_records(2, bucket="lookup") + _make_records(2, bucket="search")
    report = asyncio.run(evaluator.evaluate(records))

    assert report.overall.n_runs == 4
    assert len(report.buckets) == 2
    lookup = report.bucket_named("lookup")
    search = report.bucket_named("search")
    assert lookup is not None and lookup.n_runs == 2
    assert search is not None and search.n_runs == 2


# ---------------------------------------------------------------------------
# Token metrics
# ---------------------------------------------------------------------------


def test_evaluate_aggregates_tokens():
    evaluator = CaliperEvaluator()
    records = _make_records(2)  # 1000+2000 input, 200+200 output
    report = asyncio.run(evaluator.evaluate(records))

    u = report.overall.total_usage
    assert u.input_tokens == 3000
    assert u.output_tokens == 400
    assert u.has_cache_info is True


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def test_diff_identical_reports():
    evaluator = CaliperEvaluator()
    records = _make_records(4)
    report = asyncio.run(evaluator.evaluate(records))

    diff = evaluator.diff(report, report)
    assert diff.overall.pass_rate.delta == 0.0
