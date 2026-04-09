"""CaliperEvaluator — the one-liner API for external projects.

This is the public entry point for "measurement-only mode": projects
that run their own agent loop and feed results to caliper for scoring,
aggregation, and comparison. No Inspect AI eval loop required.

Usage:

    from caliper import CaliperRecord
    from caliper.evaluator import CaliperEvaluator

    evaluator = CaliperEvaluator(judge_model="anthropic/claude-sonnet-4-6")

    records = [
        CaliperRecord(
            sample_id="task-1",
            bucket="lookup",
            goal="What is 2+2?",
            agent_answer="4",
            observed=True,
            reference_answer="4",
        ),
        # ... more records
    ]

    report = await evaluator.evaluate(records)
    print(report.overall.pass_rate)

    # Compare two runs:
    diff = evaluator.diff(baseline_report, new_report)
    print(diff.overall.pass_rate.classification)  # "noise" | "real"

The evaluator:
1. Runs ``score_lazy`` on every record (mandatory).
2. Runs ``score_judge`` on records that have a ``reference_answer``
   (optional, requires a model API key).
3. Runs ``score_verify`` on records that have ``verify_specs`` or
   ``verify_results`` (optional).
4. Converts scored records to ``SampleResult`` objects.
5. Aggregates via ``BucketReport.from_sample_results``.
6. Exposes ``diff()`` for A/B comparison with 2σ noise floor.

See ``caliper.scoring`` for the individual pure functions and
``caliper.record`` for the ``CaliperRecord`` data contract.
"""

from __future__ import annotations

from caliper.metrics import UsageSummary
from caliper.record import CaliperRecord
from caliper.report.ab import ABDiff, compute_ab_diff
from caliper.report.bucket import BucketReport, SampleResult
from caliper.scoring import score_judge, score_lazy, score_verify


def _record_to_usage(r: CaliperRecord) -> UsageSummary:
    """Build a UsageSummary from a CaliperRecord's token fields."""
    cache_aware = (
        r.input_tokens + r.cache_read_tokens + r.cache_write_tokens
        if r.has_cache_info
        else 0
    )
    return UsageSummary(
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        reasoning_tokens=r.reasoning_tokens,
        cache_read_tokens=r.cache_read_tokens,
        cache_write_tokens=r.cache_write_tokens,
        has_reasoning_info=r.reasoning_tokens > 0,
        has_cache_info=r.has_cache_info,
        cache_aware_input_tokens=cache_aware,
    )


class CaliperEvaluator:
    """Evaluate agent outputs without an Inspect AI eval loop.

    Args:
        judge_model: Model identifier for the LLM judge (e.g.
            ``"anthropic/claude-sonnet-4-6"``). Only needed if
            any records have a ``reference_answer``. If all records
            use ``verify_specs`` / ``verify_results`` instead,
            this can be left as default — no LLM call will be made.
        judge_prompt: Custom judge prompt template. If ``None``,
            uses caliper's built-in stale-ref-tolerant prompt.
            The template receives ``{goal}``, ``{reference_answer}``,
            ``{agent_answer}`` as format kwargs.
    """

    def __init__(
        self,
        judge_model: str = "anthropic/claude-sonnet-4-6",
        judge_prompt: str | None = None,
    ) -> None:
        self.judge_model = judge_model
        self.judge_prompt = judge_prompt

    async def evaluate(
        self,
        records: list[CaliperRecord],
        *,
        task_name: str | None = None,
        model_name: str | None = None,
    ) -> BucketReport:
        """Score a batch of records and return an aggregated report.

        Scoring steps (per record):
        1. ``score_lazy`` — always runs (``observed`` is required).
        2. ``score_judge`` — runs if ``reference_answer`` is non-empty.
        3. ``score_verify`` — runs if ``verify_specs`` or
           ``verify_results`` is provided.

        The ``judge_passed`` field on each ``SampleResult`` is set to:
        - The judge result if a reference answer is present.
        - The verify result if verify specs/results are present
          (and no reference answer).
        - ``True`` if the agent answered and neither judge nor verify
          is configured (pure lazy-detection-only mode).

        Args:
            records: List of ``CaliperRecord`` objects to score.
            task_name: Optional name for the report (surfaced in
                ``BucketReport.task_name``).
            model_name: Optional model name for the report.

        Returns:
            A ``BucketReport`` with per-bucket and overall aggregation.

        Raises:
            ValueError: if ``records`` is empty.
        """
        if not records:
            raise ValueError("no records to evaluate")

        sample_results: list[SampleResult] = []

        for record in records:
            # Step 1: lazy detection (always runs).
            is_lazy = score_lazy(record.agent_answer, record.observed)

            # Step 2: determine pass/fail.
            # Judge and verify are NOT mutually exclusive — a record
            # can carry both a reference_answer AND verify specs.
            # When both are present, BOTH must pass for judge_passed
            # to be True. This was a P2 finding in Codex review:
            # the original elif made them exclusive, which meant a
            # mixed-mode task could report passing when verify fails.
            judge_passed = True  # innocent until proven guilty

            if record.reference_answer:
                result = await score_judge(
                    goal=record.goal,
                    agent_answer=record.agent_answer,
                    reference_answer=record.reference_answer,
                    judge_model=self.judge_model,
                    judge_prompt=self.judge_prompt,
                )
                judge_passed = judge_passed and result.passed

            if record.verify_specs or record.verify_results:
                result = await score_verify(
                    verify_specs=record.verify_specs,
                    verify_results=record.verify_results,
                )
                judge_passed = judge_passed and result.passed

            if (
                not record.reference_answer
                and not record.verify_specs
                and not record.verify_results
            ):
                # No judge, no verify → pass if agent answered
                # (lazy-only mode).
                judge_passed = bool(record.agent_answer)

            sample_results.append(
                SampleResult(
                    sample_id=record.sample_id,
                    epoch=record.epoch,
                    bucket=record.bucket,
                    judge_passed=judge_passed,
                    is_lazy=is_lazy,
                    usage=_record_to_usage(record),
                )
            )

        return BucketReport.from_sample_results(
            sample_results,
            task_name=task_name,
            model_name=model_name,
        )

    def diff(self, baseline: BucketReport, candidate: BucketReport) -> ABDiff:
        """Compare two reports with 2σ noise floor.

        Returns an ``ABDiff`` with per-bucket and overall metric
        deltas, each classified as ``"real"``, ``"noise"``, or
        ``"no estimate"`` based on the pooled standard error.
        """
        return compute_ab_diff(baseline, candidate)
