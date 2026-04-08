"""Tests for caliper.report.ab — A/B diff with noise floor + cache regression.

Three test layers:

1. **MetricDelta classification** — feeds synthetic baseline/candidate
   values through ``compute_ab_diff`` and asserts the right
   classification (real / noise / no estimate).

2. **Cache regression detection** — verifies the
   "tokens dropped + cache_hit_rate dropped" pattern triggers a
   warning, and that benign cases don't.

3. **End-to-end with synthetic SampleResults** — builds two
   ``BucketReport`` objects from hand-constructed ``SampleResult``
   lists and checks the full ``ABDiff`` shape.
"""

from __future__ import annotations

from caliper.metrics import UsageSummary
from caliper.report.ab import (
    compute_ab_diff,
)
from caliper.report.bucket import BucketReport, SampleResult


# ---------------------------------------------------------------------------
# Synthetic SampleResult / BucketReport builders
# ---------------------------------------------------------------------------


def _mk_sample_result(
    *,
    sample_id: str,
    epoch: int = 1,
    bucket: str = "lookup",
    judge_passed: bool = True,
    is_lazy: bool = False,
    input_tokens: int = 1_000,
    output_tokens: int = 200,
    cache_read: int = 0,
    cache_write: int = 0,
    has_cache_info: bool = True,
) -> SampleResult:
    cache_aware = (
        input_tokens + cache_read + cache_write if has_cache_info else 0
    )
    usage = UsageSummary(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        has_reasoning_info=False,
        has_cache_info=has_cache_info,
        cache_aware_input_tokens=cache_aware,
    )
    return SampleResult(
        sample_id=sample_id,
        epoch=epoch,
        bucket=bucket,
        judge_passed=judge_passed,
        is_lazy=is_lazy,
        usage=usage,
    )


def _mk_report(results: list[SampleResult], *, name: str = "test") -> BucketReport:
    return BucketReport.from_sample_results(
        results, task_name=name, model_name="anthropic/claude-sonnet-4-6"
    )


# ---------------------------------------------------------------------------
# MetricDelta classification
# ---------------------------------------------------------------------------


def test_self_diff_n1_classifies_as_no_estimate():
    """A self-diff (same log twice) with n=1 must produce
    'no estimate' classifications, not 'noise' or 'real'."""
    sample = _mk_sample_result(sample_id="t1")
    base = _mk_report([sample])
    cand = _mk_report([sample])
    diff = compute_ab_diff(base, cand)

    bucket = diff.bucket_diffs[0]
    for metric in (
        bucket.pass_rate,
        bucket.mean_total_tokens,
        bucket.mean_uncached_input_tokens,
        bucket.cache_hit_rate,
    ):
        assert metric.classification == "no estimate", (
            f"{metric.metric}: expected 'no estimate' for n=1, "
            f"got {metric.classification}"
        )


def test_within_noise_with_n4_identical_runs_classified_as_noise():
    """Two runs with the same per-sample numbers (zero variance)
    should not produce real changes — but the noise floor is also
    zero, so a non-zero delta would still be real. We use truly
    identical results to verify the n>=2 path runs without crash."""
    base_results = [
        _mk_sample_result(sample_id=f"t{i}", input_tokens=1_000)
        for i in range(4)
    ]
    cand_results = [
        _mk_sample_result(sample_id=f"t{i}", input_tokens=1_000)
        for i in range(4)
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]
    # Identical inputs → delta=0 → noise (or "no estimate" if SE=0)
    # When SE=0 on both sides, noise_2sigma=0, and abs(delta)>0 is False, so
    # is_significant=False → classification="noise". That's correct.
    assert bucket.mean_total_tokens.delta == 0.0
    assert bucket.mean_total_tokens.classification == "noise"


def test_real_change_when_delta_exceeds_noise_floor():
    """Real change: delta much larger than per-run variance."""
    # 4 baseline samples around 1000 tokens (small variance)
    base_results = [
        _mk_sample_result(sample_id=f"b{i}", input_tokens=1_000 + i * 10)
        for i in range(4)
    ]
    # 4 candidate samples around 5000 tokens (clearly different)
    cand_results = [
        _mk_sample_result(sample_id=f"c{i}", input_tokens=5_000 + i * 10)
        for i in range(4)
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]

    assert bucket.mean_total_tokens.delta is not None
    assert bucket.mean_total_tokens.delta > 3_900  # ~ 4000 tokens diff
    assert bucket.mean_total_tokens.classification == "real"


def test_within_noise_when_delta_smaller_than_2sigma():
    """Small delta should be classified as noise."""
    # Wide spread baseline (high variance)
    base_results = [
        _mk_sample_result(sample_id=f"b{i}", input_tokens=v)
        for i, v in enumerate([800, 1_200, 900, 1_100])
    ]
    # Slightly different candidate but well within the noise floor
    cand_results = [
        _mk_sample_result(sample_id=f"c{i}", input_tokens=v)
        for i, v in enumerate([810, 1_210, 910, 1_110])
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]

    assert bucket.mean_total_tokens.delta == 10.0  # tiny shift
    assert bucket.mean_total_tokens.classification == "noise"


def test_pass_rate_binomial_se_used_correctly():
    """A pass-rate flip in 1/4 samples should not be 'real'
    against a 4-sample baseline — that's well within binomial noise."""
    base_results = [
        _mk_sample_result(sample_id=f"b{i}", judge_passed=True) for i in range(4)
    ]
    cand_results = [
        _mk_sample_result(sample_id="c1", judge_passed=True),
        _mk_sample_result(sample_id="c2", judge_passed=True),
        _mk_sample_result(sample_id="c3", judge_passed=True),
        _mk_sample_result(sample_id="c4", judge_passed=False),  # one failure
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]

    # baseline pass = 1.0, candidate pass = 0.75 → delta = -0.25
    assert bucket.pass_rate.delta == -0.25
    # Baseline SE is 0 (all passes), candidate SE = sqrt(0.75*0.25/4) = ~0.217
    # 2σ ≈ 0.433. |delta|=0.25 < 0.433 → noise
    assert bucket.pass_rate.classification == "noise"


# ---------------------------------------------------------------------------
# Cache regression warning
# ---------------------------------------------------------------------------


def test_cache_regression_warning_triggers_on_token_drop_plus_cache_drop():
    """The methodology principle 5 diagnostic: tokens dropped, cache
    also dropped → SKILL.md probably invalidated."""
    # Baseline: warm cache, lots of cache_read, low fresh input
    base_results = [
        _mk_sample_result(
            sample_id=f"b{i}",
            input_tokens=200,
            output_tokens=300,
            cache_read=5_000,  # warm cache
        )
        for i in range(4)
    ]
    # Candidate: cold cache, similar total but cache_read=0
    cand_results = [
        _mk_sample_result(
            sample_id=f"c{i}",
            input_tokens=200,
            output_tokens=200,  # slightly less output → total dropped
            cache_read=0,  # cold!
            cache_write=0,
        )
        for i in range(4)
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]

    warning = bucket.cache_regression_warning
    assert warning is not None
    assert "cache_hit_rate dropped" in warning
    assert "SKILL.md" in warning


def test_cache_regression_warning_does_NOT_trigger_when_only_tokens_drop():
    """Token drop alone (with cache hit rate stable) is not a
    regression — that's a real improvement."""
    base_results = [
        _mk_sample_result(
            sample_id=f"b{i}",
            input_tokens=2_000,
            cache_read=4_000,  # cache hit ratio = 4000/6000 = 0.667
        )
        for i in range(4)
    ]
    cand_results = [
        _mk_sample_result(
            sample_id=f"c{i}",
            input_tokens=1_000,
            cache_read=2_000,  # same ratio = 2000/3000 = 0.667
        )
        for i in range(4)
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]
    assert bucket.cache_regression_warning is None


def test_cache_regression_warning_does_NOT_trigger_when_tokens_grew():
    """Tokens grew + cache dropped → not the SKILL.md-invalidation
    pattern we're flagging. This is a different problem (more work
    AND worse caching) that the cache regression flag specifically
    does NOT claim to detect.

    Remember: ``total_tokens`` in UsageSummary includes cache_read
    and cache_write, so you have to grow fresh input by MORE than
    you lose in cache_read to make the total grow.
    """
    # Baseline: 1000 fresh + 1000 cache_read = 2000 input; output 200
    #   → total = 2200, cache_hit = 1000/2000 = 0.5
    base_results = [
        _mk_sample_result(sample_id=f"b{i}", input_tokens=1_000, cache_read=1_000)
        for i in range(4)
    ]
    # Candidate: 5000 fresh + 0 cache_read = 5000 input; output 200
    #   → total = 5200 (GREW by 3000), cache_hit = 0.0 (dropped)
    cand_results = [
        _mk_sample_result(sample_id=f"c{i}", input_tokens=5_000, cache_read=0)
        for i in range(4)
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    bucket = diff.bucket_diffs[0]
    # Sanity: confirm we actually set up a "tokens grew" case
    assert bucket.mean_total_tokens.delta is not None
    assert bucket.mean_total_tokens.delta > 0, (
        "test precondition: tokens must have grown for this case to be meaningful"
    )
    assert bucket.cache_hit_rate.delta is not None
    assert bucket.cache_hit_rate.delta < 0, "test precondition: cache hit dropped"
    # The warning specifically targets "tokens dropped + cache dropped";
    # this is a different pathology so the flag stays silent.
    assert bucket.cache_regression_warning is None


def test_ab_diff_collects_bucket_warnings():
    """ABDiff.cache_regression_warnings collects all bucket warnings."""
    base_results = [
        _mk_sample_result(
            sample_id=f"b{i}",
            bucket="compare",
            input_tokens=200,
            cache_read=5_000,
        )
        for i in range(4)
    ]
    cand_results = [
        _mk_sample_result(
            sample_id=f"c{i}",
            bucket="compare",
            input_tokens=200,
            output_tokens=100,
            cache_read=0,
        )
        for i in range(4)
    ]
    diff = compute_ab_diff(_mk_report(base_results), _mk_report(cand_results))
    warnings = diff.cache_regression_warnings
    assert len(warnings) == 1
    assert "compare" in warnings[0]


# ---------------------------------------------------------------------------
# Bucket presence handling (one side missing)
# ---------------------------------------------------------------------------


def test_compute_ab_diff_handles_bucket_only_in_baseline():
    """A bucket present in baseline but not candidate produces a
    bucket diff with candidate-side None values."""
    base = _mk_report(
        [
            _mk_sample_result(sample_id="b1", bucket="lookup"),
            _mk_sample_result(sample_id="b2", bucket="lookup"),
        ]
    )
    cand = _mk_report(
        [
            _mk_sample_result(sample_id="c1", bucket="search"),
            _mk_sample_result(sample_id="c2", bucket="search"),
        ]
    )
    diff = compute_ab_diff(base, cand)
    buckets = {bd.bucket: bd for bd in diff.bucket_diffs}

    assert "lookup" in buckets
    assert buckets["lookup"].n_runs_baseline == 2
    assert buckets["lookup"].n_runs_candidate == 0
    assert buckets["lookup"].mean_total_tokens.candidate is None
    assert buckets["lookup"].mean_total_tokens.delta is None
    assert buckets["lookup"].mean_total_tokens.classification == "no estimate"

    assert "search" in buckets
    assert buckets["search"].n_runs_baseline == 0
    assert buckets["search"].n_runs_candidate == 2


def test_overall_diff_aggregates_across_buckets():
    """The overall (TOTAL) diff aggregates across every sample in
    both reports, not per-bucket."""
    base_samples = [
        _mk_sample_result(sample_id=f"b{i}", bucket="lookup") for i in range(2)
    ] + [
        _mk_sample_result(sample_id=f"b{i}", bucket="search") for i in range(2, 4)
    ]
    cand_samples = [
        _mk_sample_result(sample_id=f"c{i}", bucket="lookup") for i in range(2)
    ] + [
        _mk_sample_result(sample_id=f"c{i}", bucket="search") for i in range(2, 4)
    ]
    diff = compute_ab_diff(_mk_report(base_samples), _mk_report(cand_samples))
    assert diff.overall.n_runs_baseline == 4
    assert diff.overall.n_runs_candidate == 4
