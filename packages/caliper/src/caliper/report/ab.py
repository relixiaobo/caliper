"""A/B diff between two ``BucketReport`` objects.

Compares a baseline eval log against a candidate eval log and
classifies every per-bucket metric delta as either:

- **real change** — ``|delta| > 2σ`` of the pooled standard error
  across both runs (methodology principle 2: improvements smaller
  than the noise floor are noise)
- **within noise** — delta is inside the 2σ window
- **insufficient data** — fewer than 2 runs in either bucket so the
  noise floor can't be estimated; refuse to call any change real

The dedicated ``cache_regression_warning`` detects the SKILL.md
prefix-invalidation pattern: ``mean tokens dropped + cache hit rate
also dropped``. That's the methodology principle 5 diagnostic
signal — a cache regression masquerading as a token improvement —
turned into an actionable warning the report layer surfaces
automatically.

Reads SampleResult lists straight from BucketReport objects (no
re-parsing of .eval logs). The full pipeline is:

    .eval log → load_bucket_report → BucketReport
                                          │
              ┌───────── compute_ab_diff ─┘
              ▼
    ABDiff (with MetricDelta per metric per bucket)
              │
              ▼
    render_ab_diff → ASCII for terminal
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from inspect_ai.log import EvalLog

from caliper.report.bucket import (
    BucketReport,
    BucketStats,
    SampleResult,
    load_bucket_report,
)

# 2σ window for the significance test. methodology principle 2
# explicitly says "smaller than the noise floor is noise"; we
# follow the conventional 2σ threshold (~95% confidence).
_NOISE_SIGMA_MULTIPLIER = 2.0


# ---------------------------------------------------------------------------
# Per-metric delta with noise classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricDelta:
    """One metric's value in baseline + candidate, plus the noise-aware
    delta classification.

    Fields:
        metric: short name of the metric (e.g. "pass_rate")
        baseline: the metric value in the baseline run, or None if
            the metric isn't applicable to that bucket (e.g.
            cache_hit_rate=None for an all-Bedrock bucket)
        candidate: the metric value in the candidate run
        delta: ``candidate - baseline`` (None if either side is None)
        noise_2sigma: 2σ window of the difference distribution,
            computed from per-run variance pooled across both runs.
            None when there's insufficient data (fewer than 2 runs
            in either bucket) — in that case the delta can't be
            classified.
    """

    metric: str
    baseline: float | None
    candidate: float | None
    delta: float | None
    noise_2sigma: float | None

    @property
    def is_significant(self) -> bool | None:
        """True iff |delta| exceeds the noise floor.

        Returns None when either side is missing data or when the
        noise floor couldn't be estimated. The renderer should show
        such metrics with an explicit "(no noise estimate)" tag
        rather than silently labelling them.
        """
        if self.delta is None or self.noise_2sigma is None:
            return None
        return abs(self.delta) > self.noise_2sigma

    @property
    def classification(self) -> str:
        """Human-readable label: 'real', 'noise', or 'no estimate'."""
        sig = self.is_significant
        if sig is None:
            return "no estimate"
        return "real" if sig else "noise"


# ---------------------------------------------------------------------------
# Per-bucket diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BucketDiff:
    """Diff for one bucket: pass rate + 3 token metrics."""

    bucket: str
    n_runs_baseline: int
    n_runs_candidate: int

    pass_rate: MetricDelta
    mean_total_tokens: MetricDelta
    mean_uncached_input_tokens: MetricDelta
    cache_hit_rate: MetricDelta

    @property
    def cache_regression_warning(self) -> str | None:
        """Detect "tokens dropped + cache hit rate dropped" pattern.

        This is the SKILL.md cache invalidation signal: total tokens
        look better but the cacheable prefix was wiped. Without this
        flag, an A/B that "improves" tokens by editing SKILL.md would
        be reported as a win when it's actually a temporary spike on
        the next run after cache rewarms.

        Returns the warning string when triggered, None otherwise.

        Trigger: ``mean tokens dropped`` AND ``cache hit rate dropped
        by more than 0.10``. The 0.10 threshold matches the kind of
        cache-prefix invalidation that's worth investigating; smaller
        drops are noise.
        """
        token_delta = self.mean_total_tokens.delta
        cache_delta = self.cache_hit_rate.delta
        if token_delta is None or cache_delta is None:
            return None
        token_baseline = self.mean_total_tokens.baseline or 0
        if token_delta >= 0:
            return None
        if cache_delta >= -0.10:
            return None
        token_pct = (
            -100.0 * token_delta / token_baseline if token_baseline else 0.0
        )
        return (
            f"⚠ {self.bucket}: mean tokens dropped {token_pct:.1f}% "
            f"but cache_hit_rate dropped {-cache_delta:.2f}. "
            f"Likely SKILL.md cache prefix was invalidated. Investigate."
        )


# ---------------------------------------------------------------------------
# Whole-log diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ABDiff:
    """A/B diff between two BucketReport objects.

    ``bucket_diffs`` covers every bucket present in either log
    (sorted alphabetically). Buckets only in baseline → candidate
    side has all-None values. Same for candidate-only buckets.
    ``overall`` aggregates across the TOTAL of both reports.
    """

    baseline: BucketReport
    candidate: BucketReport
    bucket_diffs: list[BucketDiff]
    overall: BucketDiff

    @property
    def cache_regression_warnings(self) -> list[str]:
        """All cache-regression warnings across all buckets."""
        warnings = []
        for d in self.bucket_diffs:
            w = d.cache_regression_warning
            if w is not None:
                warnings.append(w)
        # The TOTAL row's warning is interesting too, but only if no
        # individual bucket already warned (otherwise we double-count).
        if not warnings:
            overall_warning = self.overall.cache_regression_warning
            if overall_warning is not None:
                warnings.append(overall_warning)
        return warnings


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def load_ab_diff(
    baseline: str | Path | EvalLog | BucketReport,
    candidate: str | Path | EvalLog | BucketReport,
) -> ABDiff:
    """Build an ``ABDiff`` from two eval logs (or two reports).

    Each argument can be a path to a ``.eval`` file, an in-memory
    ``EvalLog``, or an already-loaded ``BucketReport``. The most
    common case is two paths from the CLI; the report-object form
    is for tests and in-process inspection.
    """
    base_report = _resolve_report(baseline)
    cand_report = _resolve_report(candidate)
    return compute_ab_diff(base_report, cand_report)


def compute_ab_diff(
    baseline: BucketReport, candidate: BucketReport
) -> ABDiff:
    """Compute the diff between two ``BucketReport`` objects."""
    # Index baseline and candidate by bucket name so we can iterate
    # the union (a bucket might exist in only one of the two logs).
    base_by_bucket = {b.bucket: b for b in baseline.buckets}
    cand_by_bucket = {b.bucket: b for b in candidate.buckets}
    base_samples_by_bucket = _samples_by_bucket(baseline.samples)
    cand_samples_by_bucket = _samples_by_bucket(candidate.samples)

    bucket_names = sorted(set(base_by_bucket) | set(cand_by_bucket))

    bucket_diffs = [
        _build_bucket_diff(
            name,
            base_by_bucket.get(name),
            cand_by_bucket.get(name),
            base_samples_by_bucket.get(name, []),
            cand_samples_by_bucket.get(name, []),
        )
        for name in bucket_names
    ]

    overall = _build_bucket_diff(
        baseline.overall.bucket,  # "TOTAL"
        baseline.overall,
        candidate.overall,
        baseline.samples,
        candidate.samples,
    )

    return ABDiff(
        baseline=baseline,
        candidate=candidate,
        bucket_diffs=bucket_diffs,
        overall=overall,
    )


# ---------------------------------------------------------------------------
# Internals: per-metric delta + noise floor computation
# ---------------------------------------------------------------------------


def _resolve_report(arg: str | Path | EvalLog | BucketReport) -> BucketReport:
    """Accept any of: BucketReport, EvalLog, str/Path. Return a BucketReport."""
    if isinstance(arg, BucketReport):
        return arg
    return load_bucket_report(arg)


def _samples_by_bucket(
    samples: list[SampleResult],
) -> dict[str, list[SampleResult]]:
    by: dict[str, list[SampleResult]] = {}
    for s in samples:
        by.setdefault(s.bucket, []).append(s)
    return by


def _build_bucket_diff(
    name: str,
    base_stats: BucketStats | None,
    cand_stats: BucketStats | None,
    base_samples: list[SampleResult],
    cand_samples: list[SampleResult],
) -> BucketDiff:
    """Compute every metric delta for a single bucket."""
    n_b = base_stats.n_runs if base_stats else 0
    n_c = cand_stats.n_runs if cand_stats else 0

    return BucketDiff(
        bucket=name,
        n_runs_baseline=n_b,
        n_runs_candidate=n_c,
        pass_rate=_pass_rate_delta(base_stats, cand_stats),
        mean_total_tokens=_continuous_delta(
            "mean_total_tokens",
            _per_run_total_tokens(base_samples),
            _per_run_total_tokens(cand_samples),
            base_stats.mean_total_tokens if base_stats else None,
            cand_stats.mean_total_tokens if cand_stats else None,
        ),
        mean_uncached_input_tokens=_continuous_delta(
            "mean_uncached_input_tokens",
            _per_run_uncached(base_samples),
            _per_run_uncached(cand_samples),
            base_stats.mean_uncached_input_tokens if base_stats else None,
            cand_stats.mean_uncached_input_tokens if cand_stats else None,
        ),
        cache_hit_rate=_continuous_delta(
            "cache_hit_rate",
            _per_run_cache_hit(base_samples),
            _per_run_cache_hit(cand_samples),
            base_stats.cache_hit_rate if base_stats else None,
            cand_stats.cache_hit_rate if cand_stats else None,
        ),
    )


def _per_run_total_tokens(samples: list[SampleResult]) -> list[float]:
    return [float(s.usage.total_tokens) for s in samples]


def _per_run_uncached(samples: list[SampleResult]) -> list[float]:
    return [float(s.usage.uncached_input_tokens) for s in samples]


def _per_run_cache_hit(samples: list[SampleResult]) -> list[float]:
    """Per-run cache_hit_rate. Skips samples whose provider didn't
    report cache (has_cache_info=False) so the variance estimate
    only uses cache-aware data points."""
    return [
        s.usage.cache_hit_rate or 0.0
        for s in samples
        if s.usage.has_cache_info and s.usage.cache_aware_input_tokens > 0
    ]


def _pass_rate_delta(
    base: BucketStats | None, cand: BucketStats | None
) -> MetricDelta:
    """Pass rate is binomial. SE = sqrt(p * (1 - p) / n)."""
    base_value = base.pass_rate if base else None
    cand_value = cand.pass_rate if cand else None

    delta: float | None
    if base_value is None or cand_value is None:
        delta = None
    else:
        delta = cand_value - base_value

    se_b = _binomial_se(base) if base else None
    se_c = _binomial_se(cand) if cand else None
    noise = _pool_noise(se_b, se_c)

    return MetricDelta(
        metric="pass_rate",
        baseline=base_value,
        candidate=cand_value,
        delta=delta,
        noise_2sigma=noise,
    )


def _binomial_se(stats: BucketStats) -> float | None:
    """Standard error of a binomial proportion. Returns None if
    fewer than 2 runs."""
    if stats.n_runs < 2:
        return None
    p = stats.pass_rate
    return math.sqrt(p * (1 - p) / stats.n_runs)


def _continuous_delta(
    metric: str,
    base_values: list[float],
    cand_values: list[float],
    base_mean: float | None,
    cand_mean: float | None,
) -> MetricDelta:
    """Delta for a continuous metric. SE = std / sqrt(n) per side."""
    delta: float | None
    if base_mean is None or cand_mean is None:
        delta = None
    else:
        delta = cand_mean - base_mean

    se_b = _sample_se(base_values)
    se_c = _sample_se(cand_values)
    noise = _pool_noise(se_b, se_c)

    return MetricDelta(
        metric=metric,
        baseline=base_mean,
        candidate=cand_mean,
        delta=delta,
        noise_2sigma=noise,
    )


def _sample_se(values: list[float]) -> float | None:
    """Standard error of the mean for a sample of values.

    Returns None when there are fewer than 2 values (Bessel's
    correction would divide by zero). The caller treats None as
    "insufficient data" and refuses to label any delta involving
    this metric as significant.
    """
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    # Bessel-corrected sample variance
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    if variance < 0:
        # Floating-point pathology guard
        return 0.0
    std = math.sqrt(variance)
    return std / math.sqrt(n)


def _pool_noise(se_b: float | None, se_c: float | None) -> float | None:
    """Pool two standard errors and apply the 2σ multiplier.

    Returns None if either side is missing — without both halves of
    the variance estimate, we can't classify the delta. The
    classification then defaults to "no estimate" rather than
    silently picking a side.
    """
    if se_b is None or se_c is None:
        return None
    return _NOISE_SIGMA_MULTIPLIER * math.sqrt(se_b * se_b + se_c * se_c)


__all__ = [
    "MetricDelta",
    "BucketDiff",
    "ABDiff",
    "compute_ab_diff",
    "load_ab_diff",
]
