"""Tests for caliper.report.bucket — load + aggregate eval logs.

Two layers of testing:

1. **Synthetic mock samples** (most tests). Construct ``EvalSample``
   objects directly with controlled scores / metadata / model_usage,
   then exercise ``SampleResult.from_eval_sample`` and
   ``BucketStats.from_results``. This isolates the aggregation logic
   from any real eval log fixture.

2. **Real eval log integration** (``test_loads_real_v8_lookup_log``).
   Loads a checked-in cambridge_smoke or v8_lookup ``.eval`` file
   from ``logs/`` and asserts the resulting ``BucketReport`` has the
   expected shape. Skips gracefully if no log is present (so CI on
   a clean clone doesn't fail just because nobody ran an eval yet).

Edge cases covered (per the M1.4 spec):
- empty bucket
- multi-model usage (solver + judge in same sample)
- missing bucket metadata → ``UNGROUPED_BUCKET``
- cache-silent provider (Bedrock-style)
- mixed-provider aggregation (Bedrock + Anthropic)
- missing scorers in a sample
"""

from __future__ import annotations

from pathlib import Path

import pytest
from inspect_ai.log import EvalSample
from inspect_ai.model import ModelUsage
from inspect_ai.scorer import Score

from caliper.report.bucket import (
    DEFAULT_JUDGE_SCORER,
    DEFAULT_LAZY_SCORER,
    TOTAL_BUCKET,
    UNGROUPED_BUCKET,
    BucketStats,
    SampleResult,
    load_bucket_report,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic EvalSample factories
# ---------------------------------------------------------------------------


def _mk_sample(
    *,
    sample_id: str,
    epoch: int = 1,
    bucket: str | None = "lookup",
    judge_passed: bool = True,
    is_lazy: bool = False,
    model_usages: dict[str, ModelUsage] | None = None,
) -> EvalSample:
    """Build a minimal EvalSample for testing.

    Only the fields the bucket loader actually reads are populated.
    Inspect AI's EvalSample requires more fields than this in
    practice, but pydantic validation accepts the subset for
    in-memory construction.
    """
    metadata: dict = {}
    if bucket is not None:
        metadata["bucket"] = bucket

    scores = {
        DEFAULT_JUDGE_SCORER: Score(value=judge_passed),
        DEFAULT_LAZY_SCORER: Score(value=1.0 if is_lazy else 0.0),
    }

    return EvalSample(
        id=sample_id,
        epoch=epoch,
        input="dummy input",
        target="dummy target",
        metadata=metadata,
        scores=scores,
        model_usage=model_usages or {},
    )


def _anthropic_full(
    input_tokens: int = 500,
    output_tokens: int = 100,
    cache_read: int = 0,
    cache_write: int = 0,
) -> ModelUsage:
    """Anthropic-style ModelUsage with all cache fields populated."""
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_cache_read=cache_read,
        input_tokens_cache_write=cache_write,
    )


def _bedrock_minimal(
    input_tokens: int = 500, output_tokens: int = 100
) -> ModelUsage:
    """Bedrock-style ModelUsage: only input/output, no cache fields."""
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


# ---------------------------------------------------------------------------
# SampleResult.from_eval_sample
# ---------------------------------------------------------------------------


def test_from_eval_sample_basic_pass():
    s = _mk_sample(
        sample_id="t1",
        bucket="lookup",
        judge_passed=True,
        is_lazy=False,
        model_usages={
            "anthropic/claude-sonnet-4-6": _anthropic_full(
                input_tokens=400, output_tokens=80, cache_read=200
            )
        },
    )
    r = SampleResult.from_eval_sample(s)
    assert r.sample_id == "t1"
    assert r.bucket == "lookup"
    assert r.judge_passed is True
    assert r.is_lazy is False
    assert r.usage.input_tokens == 400
    assert r.usage.cache_read_tokens == 200
    assert r.usage.has_cache_info is True


def test_from_eval_sample_judge_fail():
    s = _mk_sample(sample_id="t1", judge_passed=False)
    r = SampleResult.from_eval_sample(s)
    assert r.judge_passed is False


def test_from_eval_sample_lazy():
    s = _mk_sample(sample_id="t1", is_lazy=True)
    r = SampleResult.from_eval_sample(s)
    assert r.is_lazy is True


def test_from_eval_sample_missing_bucket_uses_ungrouped():
    s = _mk_sample(sample_id="t1", bucket=None)
    r = SampleResult.from_eval_sample(s)
    assert r.bucket == UNGROUPED_BUCKET


def test_from_eval_sample_multi_model_usage_aggregates():
    """Solver model + judge model in same sample → summed."""
    s = _mk_sample(
        sample_id="t1",
        model_usages={
            "anthropic/claude-sonnet-4-6": _anthropic_full(
                input_tokens=1_000, output_tokens=200, cache_read=500
            ),
            # Judge call uses Haiku
            "anthropic/claude-haiku-4-5": _anthropic_full(
                input_tokens=300, output_tokens=50
            ),
        },
    )
    r = SampleResult.from_eval_sample(s)
    assert r.usage.input_tokens == 1_300
    assert r.usage.output_tokens == 250
    assert r.usage.cache_read_tokens == 500
    assert r.usage.has_cache_info is True


def test_from_eval_sample_no_model_usage():
    s = _mk_sample(sample_id="t1", model_usages={})
    r = SampleResult.from_eval_sample(s)
    assert r.usage.total_tokens == 0
    assert r.usage.has_cache_info is False


def test_from_eval_sample_missing_scorers_defaults_to_false():
    """If a scorer is missing from the sample's scores dict, the
    loader treats it as failed/not-lazy rather than crashing."""
    s = EvalSample(
        id="t1",
        epoch=1,
        input="x",
        target="y",
        metadata={"bucket": "lookup"},
        scores={},  # no scorers at all
        model_usage={},
    )
    r = SampleResult.from_eval_sample(s)
    assert r.judge_passed is False
    assert r.is_lazy is False


# ---------------------------------------------------------------------------
# Codex M1.4 P2 regression: substring bug variant in scorer normalisation
#
# bool('I') == True. If the bucket loader uses bool(score.value), an
# Inspect AI scorer like exact() that returns Score(value='I') for
# INCORRECT will be silently counted as a pass — exactly the v0-v4
# substring bug pattern, reborn in the report layer.
#
# The fix is to delegate to inspect_ai.scorer.value_to_float, which
# knows about CORRECT='C' / INCORRECT='I' / partial='P' / noanswer='N'
# plus booleans, numbers, and yes/no/true/false strings.
# ---------------------------------------------------------------------------


def _mk_sample_with_score(judge_value, lazy_value=0.0) -> EvalSample:
    """Same as _mk_sample but takes raw Score values directly."""
    return EvalSample(
        id="t1",
        epoch=1,
        input="x",
        target="y",
        metadata={"bucket": "lookup"},
        scores={
            DEFAULT_JUDGE_SCORER: Score(value=judge_value),
            DEFAULT_LAZY_SCORER: Score(value=lazy_value),
        },
        model_usage={},
    )


def test_judge_score_string_INCORRECT_is_NOT_a_pass_REGRESSION():
    """REGRESSION TEST for the Codex M1.4 P2 finding.

    Inspect AI's standard exact() scorer returns Score(value='I') for
    INCORRECT and Score(value='C') for CORRECT. ``bool('I')`` is True
    in Python, so a naive ``bool(score.value)`` would mark every
    INCORRECT sample as a pass — exactly the substring bug from
    browser-pilot v0-v4, reborn in caliper's own report layer.

    This is the most important test in this file. If it ever fails,
    the bucket report is silently wrong about pass rates whenever
    the user plugs in a non-caliper judge scorer.
    """
    s = _mk_sample_with_score(judge_value="I")
    r = SampleResult.from_eval_sample(s)
    assert r.judge_passed is False, (
        "Score(value='I') is INCORRECT and must NOT be counted as a pass"
    )


def test_judge_score_string_CORRECT_is_a_pass():
    s = _mk_sample_with_score(judge_value="C")
    r = SampleResult.from_eval_sample(s)
    assert r.judge_passed is True


def test_judge_score_string_PARTIAL_is_NOT_a_full_pass():
    """Partial credit (Score(value='P'), float 0.5) does not count
    as a full pass — bucket pass_rate is 'fully passed' not 'made
    some progress'."""
    s = _mk_sample_with_score(judge_value="P")
    r = SampleResult.from_eval_sample(s)
    assert r.judge_passed is False


def test_judge_score_string_NOANSWER_is_NOT_a_pass():
    s = _mk_sample_with_score(judge_value="N")
    r = SampleResult.from_eval_sample(s)
    assert r.judge_passed is False


def test_judge_score_yes_no_strings_normalised():
    """value_to_float also normalises yes/no/true/false strings."""
    assert SampleResult.from_eval_sample(_mk_sample_with_score("yes")).judge_passed is True
    assert SampleResult.from_eval_sample(_mk_sample_with_score("no")).judge_passed is False
    assert SampleResult.from_eval_sample(_mk_sample_with_score("true")).judge_passed is True
    assert SampleResult.from_eval_sample(_mk_sample_with_score("false")).judge_passed is False


def test_judge_score_numeric_zero_one_normalised():
    """Pure numeric scores still work after normalisation."""
    assert SampleResult.from_eval_sample(_mk_sample_with_score(1.0)).judge_passed is True
    assert SampleResult.from_eval_sample(_mk_sample_with_score(0.0)).judge_passed is False
    assert SampleResult.from_eval_sample(_mk_sample_with_score(1)).judge_passed is True
    assert SampleResult.from_eval_sample(_mk_sample_with_score(0)).judge_passed is False


def test_judge_score_boolean_still_works():
    """The original caliper judge_stale_ref returns Score(value=bool).
    That path must still work after the value_to_float change."""
    assert SampleResult.from_eval_sample(_mk_sample_with_score(True)).judge_passed is True
    assert SampleResult.from_eval_sample(_mk_sample_with_score(False)).judge_passed is False


def test_lazy_score_string_INCORRECT_is_NOT_lazy():
    """Same family for the lazy scorer: a custom lazy scorer that
    returns 'I' for not-lazy must not be flipped."""
    s = _mk_sample_with_score(judge_value=True, lazy_value="I")
    r = SampleResult.from_eval_sample(s)
    assert r.is_lazy is False


def test_lazy_score_string_CORRECT_is_lazy():
    """Mirror: 'C' is lazy=true (1.0)."""
    s = _mk_sample_with_score(judge_value=True, lazy_value="C")
    r = SampleResult.from_eval_sample(s)
    assert r.is_lazy is True


# ---------------------------------------------------------------------------
# BucketStats.from_results
# ---------------------------------------------------------------------------


def test_bucket_stats_from_empty_results():
    b = BucketStats.from_results("lookup", [])
    assert b.n_runs == 0
    assert b.pass_rate == 0.0
    assert b.cache_hit_rate is None
    assert b.mean_total_tokens == 0.0


def test_bucket_stats_aggregates_pass_lazy_counts():
    results = [
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="t1", judge_passed=True, is_lazy=False)
        ),
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="t2", judge_passed=False, is_lazy=False)
        ),
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="t3", judge_passed=True, is_lazy=True)
        ),
    ]
    b = BucketStats.from_results("lookup", results)
    assert b.n_runs == 3
    assert b.n_unique_samples == 3
    assert b.pass_count == 2
    assert b.lazy_count == 1
    assert b.pass_rate == pytest.approx(2 / 3)
    assert b.lazy_rate == pytest.approx(1 / 3)


def test_bucket_stats_counts_unique_samples_across_epochs():
    """Same sample id × 2 epochs = 2 runs but 1 unique sample."""
    results = [
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="t1", epoch=1, judge_passed=True)
        ),
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="t1", epoch=2, judge_passed=False)
        ),
    ]
    b = BucketStats.from_results("lookup", results)
    assert b.n_runs == 2
    assert b.n_unique_samples == 1
    assert b.pass_count == 1


def test_bucket_stats_mean_tokens():
    results = [
        SampleResult.from_eval_sample(
            _mk_sample(
                sample_id="t1",
                model_usages={
                    "anthropic/x": _anthropic_full(
                        input_tokens=1_000, output_tokens=200
                    )
                },
            )
        ),
        SampleResult.from_eval_sample(
            _mk_sample(
                sample_id="t2",
                model_usages={
                    "anthropic/x": _anthropic_full(
                        input_tokens=2_000, output_tokens=400
                    )
                },
            )
        ),
    ]
    b = BucketStats.from_results("lookup", results)
    # Total: 3000 input + 600 output = 3600. 2 runs → mean 1800.
    assert b.mean_total_tokens == 1800.0
    # Uncached input only: 1000 + 2000 = 3000. Mean 1500.
    assert b.mean_uncached_input_tokens == 1500.0


def test_bucket_stats_cache_hit_rate_anthropic():
    """Pure-Anthropic bucket — cache_hit_rate = total cache_read /
    total input."""
    results = [
        SampleResult.from_eval_sample(
            _mk_sample(
                sample_id="t1",
                model_usages={
                    "anthropic/x": _anthropic_full(
                        input_tokens=200, output_tokens=50, cache_read=800
                    )
                },
            )
        ),
    ]
    b = BucketStats.from_results("lookup", results)
    # 800 / (200 + 800 + 0) = 0.8
    assert b.cache_hit_rate == pytest.approx(0.8)


def test_bucket_stats_cache_hit_rate_bedrock_silent():
    """Pure-Bedrock bucket — no cache info reported anywhere → None."""
    results = [
        SampleResult.from_eval_sample(
            _mk_sample(
                sample_id="t1",
                model_usages={"bedrock/anthropic.x": _bedrock_minimal()},
            )
        ),
    ]
    b = BucketStats.from_results("lookup", results)
    assert b.cache_hit_rate is None, (
        "Bedrock provider doesn't report cache → must be None, not 0.0"
    )


def test_bucket_stats_cache_hit_rate_mixed_provider_REGRESSION():
    """REGRESSION TEST: a bucket containing both a Bedrock sample
    (cache-silent) and an Anthropic sample (cache-aware) must NOT
    let the Bedrock input tokens dilute the cache_hit_rate
    denominator. This is the same property tested at the
    UsageSummary layer; we verify it propagates through bucket
    aggregation.
    """
    results = [
        SampleResult.from_eval_sample(
            _mk_sample(
                sample_id="bedrock-sample",
                model_usages={
                    "bedrock/anthropic.x": _bedrock_minimal(
                        input_tokens=500, output_tokens=50
                    )
                },
            )
        ),
        SampleResult.from_eval_sample(
            _mk_sample(
                sample_id="anthropic-sample",
                model_usages={
                    "anthropic/claude-sonnet-4-6": _anthropic_full(
                        input_tokens=500, output_tokens=50, cache_read=500
                    )
                },
            )
        ),
    ]
    b = BucketStats.from_results("compare", results)
    # Should be 500 / (500 + 500) = 0.5, NOT 500 / 1500 = 0.333
    assert b.cache_hit_rate == pytest.approx(0.5), (
        f"mixed bucket cache_hit_rate must use cache_aware denominator, "
        f"got {b.cache_hit_rate}"
    )


# ---------------------------------------------------------------------------
# BucketReport.from_sample_results (the testable inner constructor)
# ---------------------------------------------------------------------------


def test_from_sample_results_groups_by_bucket():
    """Verify the grouping + sorting + overall aggregation logic
    without needing to construct a full EvalLog (which requires
    pydantic-validated EvalDataset / EvalConfig objects)."""
    from caliper.report.bucket import BucketReport

    results = [
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="lookup-a", bucket="lookup", judge_passed=True)
        ),
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="lookup-b", bucket="lookup", judge_passed=True)
        ),
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="search-a", bucket="search", judge_passed=False)
        ),
        SampleResult.from_eval_sample(
            _mk_sample(sample_id="search-b", bucket="search", judge_passed=True)
        ),
    ]

    report = BucketReport.from_sample_results(
        results,
        task_name="test_task",
        model_name="anthropic/claude-sonnet-4-6",
    )

    assert len(report.buckets) == 2
    assert [b.bucket for b in report.buckets] == ["lookup", "search"]  # alphabetical

    lookup = report.bucket_named("lookup")
    assert lookup is not None
    assert lookup.pass_count == 2
    assert lookup.n_runs == 2

    search = report.bucket_named("search")
    assert search is not None
    assert search.pass_count == 1
    assert search.n_runs == 2

    # TOTAL row covers all 4 samples
    assert report.overall.bucket == TOTAL_BUCKET
    assert report.overall.n_runs == 4
    assert report.overall.pass_count == 3


def test_from_sample_results_raises_on_empty():
    from caliper.report.bucket import BucketReport

    with pytest.raises(ValueError, match="no sample results"):
        BucketReport.from_sample_results([])


def test_load_bucket_report_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_bucket_report(tmp_path / "nope.eval")


# ---------------------------------------------------------------------------
# Real-log integration test (skipped gracefully if no log exists)
# ---------------------------------------------------------------------------


def _find_any_eval_log() -> Path | None:
    """Look for any .eval file in the repo's logs/ directory.

    Tests skip rather than fail if no log is present, so a clean
    clone or CI run without an eval doesn't break this test.
    """
    repo_root = Path(__file__).resolve().parents[4]
    logs = sorted((repo_root / "logs").glob("*.eval"))
    return logs[-1] if logs else None


def test_loads_real_eval_log():
    """Smoke test against whatever real log happens to be present."""
    log_path = _find_any_eval_log()
    if log_path is None:
        pytest.skip("no .eval logs in logs/; run an eval first")

    report = load_bucket_report(log_path)
    assert report.overall.n_runs >= 1
    assert report.task_name is not None
    assert report.model_name is not None
    # Should be at least one bucket (real samples have metadata.bucket)
    assert len(report.buckets) >= 1
