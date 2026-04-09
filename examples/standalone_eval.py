"""Caliper standalone evaluation — no Inspect AI, no bp, no agent framework.

This example shows how to use CaliperRecord + CaliperEvaluator to
evaluate agent outputs from ANY source. Your project runs the agent
itself; caliper just does the measurement.

Run (no API key needed for lazy-only / verify-only mode):
    cd ~/Documents/Coding/caliper
    uv run python examples/standalone_eval.py

Run (with API key for the LLM judge):
    ANTHROPIC_API_KEY=sk-... uv run python examples/standalone_eval.py

Three scenarios demonstrated:
    1. Lazy-only mode — no LLM judge, no API key needed
    2. With verify results — pre-computed deterministic checks
    3. With LLM judge — needs an API key (skipped if not set)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "packages" / "caliper" / "src")
)

from caliper import CaliperEvaluator, CaliperRecord
from caliper.report import render_bucket_table


async def main():
    # -----------------------------------------------------------------
    # Scenario 1: Lazy-only mode (no API key needed)
    # -----------------------------------------------------------------
    # Your agent ran some tasks. You know what it answered and whether
    # it actually observed the target. caliper tells you pass/fail +
    # lazy detection.

    print("=" * 60)
    print("Scenario 1: Lazy-only mode (no API key needed)")
    print("=" * 60)

    records = [
        CaliperRecord(
            sample_id="task-1",
            bucket="lookup",
            goal="What is 2+2?",
            agent_answer="4",
            observed=True,  # agent actually computed it
            input_tokens=1000,
            output_tokens=100,
            has_cache_info=True,
        ),
        CaliperRecord(
            sample_id="task-2",
            bucket="lookup",
            goal="What is the capital of France?",
            agent_answer="Paris",
            observed=False,  # agent answered from training data!
            input_tokens=800,
            output_tokens=50,
            has_cache_info=True,
        ),
        CaliperRecord(
            sample_id="task-3",
            bucket="action",
            goal="Click the submit button",
            agent_answer="",  # agent didn't finish
            observed=False,
            input_tokens=500,
            output_tokens=0,
            has_cache_info=True,
        ),
    ]

    evaluator = CaliperEvaluator()
    report = await evaluator.evaluate(records, task_name="lazy_only_demo")
    print(render_bucket_table(report))
    print(f"Pass: {report.overall.pass_count}/{report.overall.n_runs}")
    print(f"Lazy: {report.overall.lazy_count}")
    print(f"Tokens: {report.overall.total_usage.total_tokens:,}")

    # -----------------------------------------------------------------
    # Scenario 2: With pre-computed verify results
    # -----------------------------------------------------------------
    # Your project already ran deterministic checks (DOM queries,
    # API assertions, etc.) and passes the results to caliper.
    # No LLM judge call, no subprocess execution by caliper.

    print("\n" + "=" * 60)
    print("Scenario 2: Pre-computed verification results")
    print("=" * 60)

    records_verify = [
        CaliperRecord(
            sample_id="login-test",
            bucket="smoke",
            goal="Log in with username 'admin' and password '1234'",
            agent_answer="Logged in successfully",
            observed=True,
            verify_results=[
                {"passed": True, "description": "success message shown"},
                {"passed": True, "description": "URL changed to /dashboard"},
            ],
        ),
        CaliperRecord(
            sample_id="checkbox-test",
            bucket="smoke",
            goal="Check both checkboxes on the page",
            agent_answer="Done",
            observed=True,
            verify_results=[
                {"passed": False, "description": "only 1 of 2 checkboxes checked"},
            ],
        ),
    ]

    report2 = await evaluator.evaluate(records_verify, task_name="verify_demo")
    print(render_bucket_table(report2))

    # -----------------------------------------------------------------
    # Scenario 3: With LLM judge (needs API key)
    # -----------------------------------------------------------------

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n" + "=" * 60)
        print("Scenario 3: Skipped (set ANTHROPIC_API_KEY to enable)")
        print("=" * 60)
        return

    print("\n" + "=" * 60)
    print("Scenario 3: With LLM judge")
    print("=" * 60)

    records_judge = [
        CaliperRecord(
            sample_id="compare-1",
            bucket="compare",
            goal="Compare the prices of MacBook Air 13-inch vs 15-inch",
            agent_answer="13-inch starts at $1099, 15-inch starts at $1299",
            observed=True,
            reference_answer="MacBook Air M2: 13-inch from $1099, 15-inch from $1299",
        ),
        CaliperRecord(
            sample_id="compare-2",
            bucket="compare",
            goal="Which GitHub plan has more storage, Enterprise or Team?",
            agent_answer="Enterprise has 50GB, Team has 2GB, so Enterprise has 48GB more",
            observed=True,
            reference_answer="Enterprise has 48 GB more storage than Team",
        ),
    ]

    evaluator_judge = CaliperEvaluator(
        judge_model="anthropic/claude-sonnet-4-6",
    )
    report3 = await evaluator_judge.evaluate(records_judge, task_name="judge_demo")
    print(render_bucket_table(report3))

    # -----------------------------------------------------------------
    # A/B comparison
    # -----------------------------------------------------------------
    print("\n--- A/B Diff (Scenario 1 vs Scenario 2) ---\n")
    diff = evaluator.diff(report, report2)
    from caliper.report import render_ab_diff

    print(render_ab_diff(diff))


if __name__ == "__main__":
    asyncio.run(main())
