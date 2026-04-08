"""Per-bucket aggregation of an Inspect AI ``.eval`` log.

Reads an ``EvalLog``, walks every ``EvalSample``, and produces a
``BucketReport`` grouping samples by ``metadata["bucket"]``. Each
bucket carries pass / lazy counts plus an aggregated
``UsageSummary`` (which already handles the cache_aware denominator
math correctly across mixed-provider buckets — see
``caliper.metrics.usage``).

The whole module is **read-only**. Nothing is written back into the
``.eval`` log; the report is computed fresh on each call. This means
pricing/cache changes propagate immediately to old logs.

Caliper-standard contract: this loader expects the
``judge_stale_ref`` and ``lazy_detection`` scorers from
``caliper.scorers``. Custom scorers can be plugged in via the
``judge_scorer_name`` and ``lazy_scorer_name`` parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from inspect_ai.log import EvalLog, EvalSample, read_eval_log
from inspect_ai.scorer import value_to_float

from caliper.metrics import UsageSummary

# Inspect AI's score-value normaliser. Maps every shape Score.value
# can take — bool, int, float, the standard "C"/"I"/"P"/"N" strings,
# yes/no/true/false strings — to a float in [0, 1]. Caliper uses it
# to avoid the substring-bug family on score values: ``bool("I")``
# is ``True`` in Python, so any naive truthiness check on a string
# scorer's value would silently flip every INCORRECT to a pass.
# This is the same bug class as the original v0–v4 judge parser
# substring trap, applied to score values instead of judge prompts.
#
# We instantiate at module level (no args = use the default
# C/I/P/N constants) so the function is reused across every
# SampleResult conversion.
_value_to_float = value_to_float()

# Default scorer names — match the function names of caliper's
# standard scorers. Override via ``load_bucket_report`` arguments
# if you use custom scorer names.
DEFAULT_JUDGE_SCORER = "judge_stale_ref"
DEFAULT_LAZY_SCORER = "lazy_detection"

# Bucket name used for samples whose metadata doesn't carry a
# ``bucket`` key. Surfaced separately so the user notices that
# something isn't tagged, rather than silently lumping into "lookup".
UNGROUPED_BUCKET = "ungrouped"

# Total row name. Used as a sentinel by render code so the TOTAL
# row can be styled separately.
TOTAL_BUCKET = "TOTAL"


# ---------------------------------------------------------------------------
# Per-sample result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleResult:
    """One sample's slice of an eval — id + epoch + scorer outcomes
    + aggregated token usage across every model the sample touched.
    """

    sample_id: str
    epoch: int
    bucket: str
    judge_passed: bool
    is_lazy: bool
    usage: UsageSummary

    @classmethod
    def from_eval_sample(
        cls,
        sample: EvalSample,
        *,
        judge_scorer_name: str = DEFAULT_JUDGE_SCORER,
        lazy_scorer_name: str = DEFAULT_LAZY_SCORER,
    ) -> "SampleResult":
        """Pull a SampleResult out of an Inspect AI ``EvalSample``.

        - ``judge_passed``: True iff the named judge scorer's value
          is truthy. Defaults to False if the scorer is missing.
        - ``is_lazy``: True iff the named lazy scorer's value is
          ``> 0`` (the scorer returns 1.0 for lazy, 0.0 otherwise).
        - ``usage``: aggregated across every entry in
          ``sample.model_usage`` (solver model + judge model + any
          other model touched during the sample). The aggregation
          uses ``UsageSummary.__add__``, which preserves cache-aware
          denominator semantics across mixed providers.
        """
        scores = sample.scores or {}
        bucket = (sample.metadata or {}).get("bucket", UNGROUPED_BUCKET)

        # ``judge_passed`` is True iff the judge scorer's value
        # normalises to a full pass (1.0). Partial credit (0.5) does
        # NOT count as a pass — bucket pass_rate is the rate of
        # *fully* passed samples, not "made some progress".
        #
        # We use Inspect AI's value_to_float to handle every Score
        # value shape: bool True/False, the C/I/P/N string convention
        # used by exact() / match() / etc., yes/no/true/false strings,
        # and pure numerics. Naive ``bool(score.value)`` would flip
        # 'I' to True and silently inflate pass rate (the v0-v4
        # substring bug class, reborn).
        judge_score = scores.get(judge_scorer_name)
        judge_passed = (
            _value_to_float(judge_score.value) >= 1.0
            if judge_score is not None
            else False
        )

        # ``is_lazy`` is True iff the lazy scorer's value is non-zero
        # after normalisation. caliper's lazy_detection returns 1.0
        # for lazy / 0.0 for not-lazy, but a custom scorer might use
        # any of the same shapes the judge accepts.
        lazy_score = scores.get(lazy_scorer_name)
        is_lazy = (
            _value_to_float(lazy_score.value) > 0.0
            if lazy_score is not None
            else False
        )

        # Sum UsageSummary across every model this sample touched.
        # ``model_usage`` is keyed by model name and aggregated by
        # Inspect AI internally, so we just walk the dict and add.
        # When the dict is empty (sample produced no model calls
        # somehow) we fall back to ``UsageSummary.zero()``.
        usage = UsageSummary.zero()
        for model_name, model_usage in (sample.model_usage or {}).items():
            usage = usage + UsageSummary.from_model_usage(
                model_usage, model=model_name
            )

        return cls(
            sample_id=str(sample.id),
            epoch=sample.epoch,
            bucket=bucket,
            judge_passed=judge_passed,
            is_lazy=is_lazy,
            usage=usage,
        )


# ---------------------------------------------------------------------------
# Per-bucket aggregate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BucketStats:
    """One bucket's aggregated stats across all of its samples.

    Constructed via ``BucketStats.from_results(bucket_name, results)``;
    don't construct directly unless you know the invariants
    (``n_runs == len(contributing samples)``,
    ``total_usage == sum of per-sample UsageSummary``, etc.).
    """

    bucket: str
    n_runs: int                 # number of (sample × epoch) results
    n_unique_samples: int       # number of distinct sample ids
    pass_count: int
    lazy_count: int
    total_usage: UsageSummary

    # ---- derived rates --------------------------------------------------

    @property
    def pass_rate(self) -> float:
        """Fraction of runs whose judge passed (0.0 to 1.0)."""
        return self.pass_count / self.n_runs if self.n_runs else 0.0

    @property
    def lazy_rate(self) -> float:
        """Fraction of runs flagged as lazy (0.0 to 1.0)."""
        return self.lazy_count / self.n_runs if self.n_runs else 0.0

    @property
    def mean_total_tokens(self) -> float:
        """Average ``total_tokens`` per run."""
        return self.total_usage.total_tokens / self.n_runs if self.n_runs else 0.0

    @property
    def mean_uncached_input_tokens(self) -> float:
        """Average ``uncached_input_tokens`` per run.

        This is the metric you watch for SKILL.md regressions: a
        cache-prefix invalidation drives this up while the raw
        ``mean_total_tokens`` may stay flat.
        """
        return (
            self.total_usage.uncached_input_tokens / self.n_runs
            if self.n_runs
            else 0.0
        )

    @property
    def cache_hit_rate(self) -> float | None:
        """Bucket-level cache hit rate.

        Returns ``None`` when no contributing sample reported cache
        state at all (all-Bedrock bucket, all-Mistral bucket, etc.).
        Otherwise computed against ``cache_aware_input_tokens`` so
        cache-silent samples in a mixed bucket don't dilute the rate.
        """
        return self.total_usage.cache_hit_rate

    # ---- construction ---------------------------------------------------

    @classmethod
    def from_results(
        cls, bucket: str, results: list[SampleResult]
    ) -> "BucketStats":
        """Aggregate a list of ``SampleResult`` into a single bucket."""
        if not results:
            return cls(
                bucket=bucket,
                n_runs=0,
                n_unique_samples=0,
                pass_count=0,
                lazy_count=0,
                total_usage=UsageSummary.zero(),
            )
        usage = UsageSummary.zero()
        pass_count = 0
        lazy_count = 0
        ids: set[str] = set()
        for r in results:
            usage = usage + r.usage
            if r.judge_passed:
                pass_count += 1
            if r.is_lazy:
                lazy_count += 1
            ids.add(r.sample_id)
        return cls(
            bucket=bucket,
            n_runs=len(results),
            n_unique_samples=len(ids),
            pass_count=pass_count,
            lazy_count=lazy_count,
            total_usage=usage,
        )


# ---------------------------------------------------------------------------
# Whole-log report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BucketReport:
    """Per-bucket breakdown of an entire eval log, plus a TOTAL row.

    The ``buckets`` list is sorted alphabetically (so reports are
    deterministic across runs); ``overall`` is computed across every
    sample regardless of bucket. Together they give both the
    fine-grained bucket view and the headline TOTAL pass rate.
    """

    buckets: list[BucketStats]
    overall: BucketStats
    samples: list[SampleResult] = field(default_factory=list)
    log_path: str | None = None
    task_name: str | None = None
    model_name: str | None = None

    def bucket_named(self, name: str) -> BucketStats | None:
        """Look up a bucket by name. Returns ``None`` if missing."""
        for b in self.buckets:
            if b.bucket == name:
                return b
        return None

    @classmethod
    def from_sample_results(
        cls,
        results: list[SampleResult],
        *,
        log_path: str | None = None,
        task_name: str | None = None,
        model_name: str | None = None,
    ) -> "BucketReport":
        """Build a ``BucketReport`` from a list of ``SampleResult``.

        This is the inner construction step used by
        ``load_bucket_report`` and is exposed publicly so callers can
        aggregate sample results from sources other than an
        ``EvalLog`` (e.g. unit tests, custom eval pipelines).

        Buckets are sorted alphabetically for deterministic output.
        ``overall`` aggregates across every result regardless of
        bucket.
        """
        if not results:
            raise ValueError("no sample results to aggregate")

        by_bucket: dict[str, list[SampleResult]] = {}
        for r in results:
            by_bucket.setdefault(r.bucket, []).append(r)

        bucket_stats = [
            BucketStats.from_results(bucket, sub_results)
            for bucket, sub_results in sorted(by_bucket.items())
        ]
        overall = BucketStats.from_results(TOTAL_BUCKET, results)

        return cls(
            buckets=bucket_stats,
            overall=overall,
            samples=results,
            log_path=log_path,
            task_name=task_name,
            model_name=model_name,
        )


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def load_bucket_report(
    eval_log: str | Path | EvalLog,
    *,
    judge_scorer_name: str = DEFAULT_JUDGE_SCORER,
    lazy_scorer_name: str = DEFAULT_LAZY_SCORER,
) -> BucketReport:
    """Build a ``BucketReport`` from an Inspect AI eval log.

    Args:
        eval_log: Either a path to a ``.eval`` log file or an
            already-loaded ``EvalLog`` object. The path form is the
            common case for the future ``caliper report`` CLI; the
            object form is for tests and in-process inspection.
        judge_scorer_name: Name of the judge scorer to read for the
            pass/fail signal. Defaults to caliper's standard
            ``judge_stale_ref``.
        lazy_scorer_name: Name of the lazy detection scorer.
            Defaults to caliper's standard ``lazy_detection``.

    Returns:
        A ``BucketReport`` with per-bucket ``BucketStats`` plus a
        TOTAL row aggregating across every sample.

    Raises:
        FileNotFoundError: if a path is given and the file is missing
        ValueError: if the log has no samples
    """
    log = _resolve_log(eval_log)

    if not log.samples:
        raise ValueError(
            f"eval log has no samples (path={getattr(log, 'location', None)!r}); "
            "nothing to aggregate"
        )

    results: list[SampleResult] = [
        SampleResult.from_eval_sample(
            s,
            judge_scorer_name=judge_scorer_name,
            lazy_scorer_name=lazy_scorer_name,
        )
        for s in log.samples
    ]

    return BucketReport.from_sample_results(
        results,
        log_path=str(getattr(log, "location", None))
        if hasattr(log, "location")
        else None,
        task_name=_safe_task_name(log),
        model_name=_safe_model_name(log),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _resolve_log(eval_log: str | Path | EvalLog) -> EvalLog:
    """Accept either a path or a loaded EvalLog and return an EvalLog."""
    if isinstance(eval_log, EvalLog):
        return eval_log
    path = Path(eval_log)
    if not path.exists():
        raise FileNotFoundError(f"eval log not found: {path}")
    return read_eval_log(str(path))


def _safe_task_name(log: EvalLog) -> str | None:
    """Best-effort extraction of the task name. Returns None on any
    structural mismatch — Inspect AI's log shape evolves and the
    bucket report shouldn't break on minor field renames."""
    try:
        return log.eval.task  # type: ignore[union-attr]
    except (AttributeError, TypeError):
        return None


def _safe_model_name(log: EvalLog) -> str | None:
    """Best-effort extraction of the primary model name."""
    try:
        return log.eval.model  # type: ignore[union-attr]
    except (AttributeError, TypeError):
        return None


__all__ = [
    "DEFAULT_JUDGE_SCORER",
    "DEFAULT_LAZY_SCORER",
    "UNGROUPED_BUCKET",
    "TOTAL_BUCKET",
    "SampleResult",
    "BucketStats",
    "BucketReport",
    "load_bucket_report",
]
