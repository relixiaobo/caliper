"""M2.3: UsageSummary aggregation consistency self-eval.

Verifies that caliper's aggregation pipeline (SampleResult →
BucketStats → BucketReport) produces token totals that are
**byte-for-byte identical** to an independent field-by-field sum of
the same input data. This is the "sum it two ways and compare"
defense against aggregation bugs that silently corrupt token
metrics.

The existing unit tests in test_metrics_usage.py verify
``UsageSummary.__add__`` and ``from_model_usage`` individually.
This suite tests the **full pipeline** — from raw numbers to
bucket report — ensuring no field gets dropped, double-counted, or
rounded incorrectly at any aggregation level.

Three scenarios:
1. **Single-provider** (Anthropic-only): all samples have cache info
2. **Mixed-provider** (Anthropic + Bedrock): silent provider must not
   dilute cache_hit_rate
3. **Cross-bucket**: overall totals must equal sum of per-bucket totals

No LLM calls. No .eval logs. Runs in <1 second. Target: 100%.
"""

from __future__ import annotations

from functools import reduce

from caliper.metrics import UsageSummary
from caliper.report.bucket import BucketReport, SampleResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk(
    sample_id: str,
    bucket: str,
    *,
    input_tokens: int = 1000,
    output_tokens: int = 200,
    cache_read: int = 0,
    cache_write: int = 0,
    has_cache_info: bool = True,
    judge_passed: bool = True,
) -> SampleResult:
    cache_aware = input_tokens + cache_read + cache_write if has_cache_info else 0
    return SampleResult(
        sample_id=sample_id,
        epoch=1,
        bucket=bucket,
        judge_passed=judge_passed,
        is_lazy=False,
        usage=UsageSummary(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=0,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            has_reasoning_info=False,
            has_cache_info=has_cache_info,
            cache_aware_input_tokens=cache_aware,
        ),
    )


def _manual_sum(results: list[SampleResult]) -> UsageSummary:
    """Independent aggregation: reduce via __add__, NOT through
    BucketReport. This is the second path for cross-checking."""
    return reduce(lambda a, b: a + b, [r.usage for r in results])


# ---------------------------------------------------------------------------
# Scenario 1: single-provider (Anthropic-only)
# ---------------------------------------------------------------------------


def test_single_provider_anthropic_consistency():
    """All samples come from Anthropic — all have cache info.
    Two-path cross-check: BucketReport vs manual __add__ sum."""
    results = [
        _mk("s1", "lookup", input_tokens=1000, cache_read=500, cache_write=50),
        _mk("s2", "lookup", input_tokens=800, cache_read=200, cache_write=0),
        _mk("s3", "lookup", input_tokens=1200, cache_read=0, cache_write=100),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    manual = _manual_sum(results)

    # Every field must match.
    u = report.overall.total_usage
    assert u.input_tokens == manual.input_tokens
    assert u.output_tokens == manual.output_tokens
    assert u.cache_read_tokens == manual.cache_read_tokens
    assert u.cache_write_tokens == manual.cache_write_tokens
    assert u.cache_aware_input_tokens == manual.cache_aware_input_tokens
    assert u.total_tokens == manual.total_tokens
    assert u.uncached_input_tokens == manual.uncached_input_tokens
    assert u.has_cache_info == manual.has_cache_info
    assert u.cache_hit_rate == manual.cache_hit_rate


# ---------------------------------------------------------------------------
# Scenario 2: mixed-provider (Anthropic + Bedrock)
# ---------------------------------------------------------------------------


def test_mixed_provider_bedrock_dilution_regression():
    """CRITICAL: Bedrock (cache-silent) + Anthropic (cache-aware) in
    the same bucket. The cache-silent provider's input tokens must NOT
    enter the cache_hit_rate denominator.

    This is the end-to-end pipeline version of the Codex M1.2 P2
    regression test in test_metrics_usage.py — that test checks
    __add__ directly; this one checks through BucketReport."""
    results = [
        # Bedrock sample: no cache info
        _mk("bedrock-1", "compare", input_tokens=500, has_cache_info=False),
        _mk("bedrock-2", "compare", input_tokens=600, has_cache_info=False),
        # Anthropic sample: has cache info
        _mk("anthropic-1", "compare", input_tokens=400, cache_read=600),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    manual = _manual_sum(results)

    u = report.overall.total_usage
    # Token totals match between paths.
    assert u.input_tokens == manual.input_tokens == 1500
    assert u.cache_read_tokens == manual.cache_read_tokens == 600
    assert u.total_input_tokens == manual.total_input_tokens == 2100

    # The critical check: cache-aware input is ONLY the Anthropic
    # sample's contribution (400 + 600 = 1000), not the full 2100.
    assert u.cache_aware_input_tokens == manual.cache_aware_input_tokens == 1000

    # cache_hit_rate is computed against the aware subset only.
    assert u.cache_hit_rate == manual.cache_hit_rate == 0.6  # 600/1000
    assert u.has_cache_info is True


def test_all_silent_bucket_stays_silent():
    """A bucket with ONLY cache-silent providers must have
    cache_hit_rate=None, not 0.0."""
    results = [
        _mk("b1", "smoke", input_tokens=500, has_cache_info=False),
        _mk("b2", "smoke", input_tokens=300, has_cache_info=False),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    manual = _manual_sum(results)

    assert report.overall.total_usage.cache_hit_rate is None
    assert manual.cache_hit_rate is None
    assert report.overall.total_usage.has_cache_info is False


# ---------------------------------------------------------------------------
# Scenario 3: cross-bucket consistency
# ---------------------------------------------------------------------------


def test_overall_equals_sum_of_buckets():
    """The overall totals in BucketReport.overall must exactly equal
    the sum of all per-bucket totals. This catches bugs where the
    overall aggregation path differs from the per-bucket path."""
    results = [
        _mk("l1", "lookup", input_tokens=1000, cache_read=500),
        _mk("l2", "lookup", input_tokens=1200, cache_read=300),
        _mk("s1", "search", input_tokens=800, cache_read=200),
        _mk("s2", "search", input_tokens=900, cache_read=100),
        _mk("c1", "compare", input_tokens=2000, cache_read=1000),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")

    # Sum per-bucket totals independently.
    bucket_sum = reduce(
        lambda a, b: a + b,
        [b.total_usage for b in report.buckets],
    )

    overall = report.overall.total_usage

    assert overall.input_tokens == bucket_sum.input_tokens
    assert overall.output_tokens == bucket_sum.output_tokens
    assert overall.cache_read_tokens == bucket_sum.cache_read_tokens
    assert overall.cache_write_tokens == bucket_sum.cache_write_tokens
    assert overall.cache_aware_input_tokens == bucket_sum.cache_aware_input_tokens
    assert overall.total_tokens == bucket_sum.total_tokens
    assert overall.uncached_input_tokens == bucket_sum.uncached_input_tokens


def test_per_bucket_mean_tokens_is_consistent():
    """BucketStats.mean_total_tokens must equal
    total_usage.total_tokens / n_runs for each bucket."""
    results = [
        _mk("l1", "lookup", input_tokens=1000, output_tokens=200),
        _mk("l2", "lookup", input_tokens=2000, output_tokens=400),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    bucket = report.buckets[0]

    expected_mean = bucket.total_usage.total_tokens / bucket.n_runs
    assert bucket.mean_total_tokens == expected_mean


def test_n_runs_matches_sample_count():
    """overall.n_runs must equal len(results)."""
    results = [_mk(f"s{i}", "lookup") for i in range(7)]
    report = BucketReport.from_sample_results(results, task_name="test")
    assert report.overall.n_runs == 7


def test_pass_count_matches_filter():
    """pass_count must equal the number of results where
    judge_passed=True."""
    results = [
        _mk("p1", "lookup", judge_passed=True),
        _mk("p2", "lookup", judge_passed=True),
        _mk("f1", "lookup", judge_passed=False),
    ]
    report = BucketReport.from_sample_results(results, task_name="test")
    assert report.overall.pass_count == 2
    assert report.overall.n_runs == 3


# ---------------------------------------------------------------------------
# Scenario 4: Real ModelUsage fixtures through from_model_usage
# (Codex adversarial review fix: exercise the REAL construction path,
# not pre-computed UsageSummary objects, and compare against raw
# arithmetic that does NOT call __add__)
# ---------------------------------------------------------------------------


def _mk_from_model_usage(
    sample_id: str,
    bucket: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int | None = None,
    cache_write: int | None = None,
    reasoning: int | None = None,
    model: str | None = None,
) -> SampleResult:
    """Build a SampleResult through the REAL from_model_usage path."""
    from inspect_ai.model import ModelUsage

    mu = ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens
        + output_tokens
        + (cache_read or 0)
        + (cache_write or 0),
        input_tokens_cache_read=cache_read,
        input_tokens_cache_write=cache_write,
        reasoning_tokens=reasoning,
    )
    usage = UsageSummary.from_model_usage(mu, model=model)
    return SampleResult(
        sample_id=sample_id,
        epoch=1,
        bucket=bucket,
        judge_passed=True,
        is_lazy=False,
        usage=usage,
    )


def test_real_model_usage_anthropic_vs_raw_arithmetic():
    """Construct SampleResults through from_model_usage (the real
    production path), then compare BucketReport totals against
    raw field-by-field arithmetic (NO __add__, NO UsageSummary
    operations). This is the Codex adversarial review fix: the
    'independent' path must be genuinely independent."""
    results = [
        _mk_from_model_usage(
            "a1",
            "lookup",
            input_tokens=1000,
            output_tokens=200,
            cache_read=500,
            cache_write=50,
        ),
        _mk_from_model_usage(
            "a2",
            "lookup",
            input_tokens=800,
            output_tokens=300,
            cache_read=200,
            cache_write=0,
        ),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    u = report.overall.total_usage

    # Raw arithmetic — no UsageSummary methods, just Python math.
    raw_input = 1000 + 800
    raw_output = 200 + 300
    raw_cache_read = 500 + 200
    raw_cache_write = 50 + 0
    raw_total_input = raw_input + raw_cache_read + raw_cache_write
    raw_total = raw_total_input + raw_output
    raw_uncached = raw_input + raw_cache_write
    raw_cache_aware = raw_total_input  # both are Anthropic, all cache-aware
    raw_cache_hit = raw_cache_read / raw_cache_aware

    assert u.input_tokens == raw_input
    assert u.output_tokens == raw_output
    assert u.cache_read_tokens == raw_cache_read
    assert u.cache_write_tokens == raw_cache_write
    assert u.total_input_tokens == raw_total_input
    assert u.total_tokens == raw_total
    assert u.uncached_input_tokens == raw_uncached
    assert u.cache_aware_input_tokens == raw_cache_aware
    assert u.cache_hit_rate == raw_cache_hit


def test_real_model_usage_mixed_providers_vs_raw_arithmetic():
    """Mixed Anthropic + Bedrock through from_model_usage, compared
    against raw arithmetic with explicit cache-aware denominator
    logic."""
    results = [
        # Anthropic: has cache info
        _mk_from_model_usage(
            "anthropic-1",
            "compare",
            input_tokens=400,
            output_tokens=100,
            cache_read=600,
            cache_write=0,
        ),
        # Bedrock: no cache info (None fields)
        _mk_from_model_usage(
            "bedrock-1",
            "compare",
            input_tokens=500,
            output_tokens=150,
            # cache_read=None, cache_write=None (defaults)
        ),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    u = report.overall.total_usage

    # Raw arithmetic with explicit cache-aware logic.
    # Anthropic sample: input=400, cache_read=600, cache_write=0
    #   total_input = 400+600+0 = 1000, cache_aware_input = 1000
    # Bedrock sample: input=500, cache_read=0(None→0), cache_write=0(None→0)
    #   total_input = 500, cache_aware_input = 0 (has_cache_info=False)
    raw_input = 400 + 500
    raw_output = 100 + 150
    raw_cache_read = 600 + 0
    raw_total_input = raw_input + raw_cache_read  # 900 + 600 = 1500
    raw_cache_aware = 1000 + 0  # only Anthropic contributes
    raw_cache_hit = 600 / 1000  # 0.6 — Bedrock excluded from denominator

    assert u.input_tokens == raw_input
    assert u.output_tokens == raw_output
    assert u.cache_read_tokens == raw_cache_read
    assert u.total_input_tokens == raw_total_input
    assert u.cache_aware_input_tokens == raw_cache_aware
    assert u.cache_hit_rate == raw_cache_hit
    assert u.has_cache_info is True  # at least one has it


def test_real_model_usage_openai_responses_cold_cache():
    """OpenAI Responses adapter (gpt-5): cache_read=None means cold
    cache, NOT 'unknown'. With model hint, from_model_usage should
    treat it as 0 and has_cache_info=True."""
    results = [
        _mk_from_model_usage(
            "gpt5-1",
            "search",
            input_tokens=2000,
            output_tokens=500,
            # cache_read=None → cold cache with model hint
            model="openai/gpt-5.4",
        ),
    ]

    report = BucketReport.from_sample_results(results, task_name="test")
    u = report.overall.total_usage

    assert u.input_tokens == 2000
    assert u.output_tokens == 500
    assert u.cache_read_tokens == 0  # None → 0 with model hint
    assert u.has_cache_info is True
    assert u.cache_hit_rate == 0.0  # cold cache, not unknown
