"""``caliper`` CLI — thin wrapper over the report API.

Three subcommands:

    caliper report  <log.eval>                 → bucket table
    caliper diff    <baseline.eval> <candidate.eval>
                                                → A/B diff with noise floor
    caliper score   <records.json>             → evaluate CaliperRecords
                                                  from a JSON file

The CLI is intentionally minimal: argparse stdlib only (no click
dependency), one file, no business logic. Everything substantive
lives in ``caliper.report`` and ``caliper.evaluator``; this module
just dispatches.

Why a CLI exists at all (Inspect AI already has ``inspect view``):
``inspect view`` shows per-sample detail and the live progress
during ``inspect eval``. Neither of those is per-bucket aggregation,
A/B comparison, or standalone scoring — those are caliper's
value-add.

Registered as ``caliper`` via ``[project.scripts]`` in
``packages/caliper/pyproject.toml``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def cmd_report(args: argparse.Namespace) -> int:
    from caliper.report import load_bucket_report, render_bucket_table

    if not args.log.exists():
        print(f"caliper report: log not found: {args.log}", file=sys.stderr)
        return 2

    report = load_bucket_report(args.log)
    print(render_bucket_table(report))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    """Evaluate CaliperRecords from a JSON file."""
    import asyncio
    import json

    from caliper.evaluator import CaliperEvaluator
    from caliper.record import CaliperRecord
    from caliper.report import render_bucket_table

    if not args.records.exists():
        print(f"caliper score: file not found: {args.records}", file=sys.stderr)
        return 2

    try:
        raw = json.loads(args.records.read_text())
    except json.JSONDecodeError as e:
        print(f"caliper score: invalid JSON: {e}", file=sys.stderr)
        return 2

    if not isinstance(raw, list):
        print(
            "caliper score: expected a JSON array of CaliperRecord objects",
            file=sys.stderr,
        )
        return 2

    if not raw:
        print("caliper score: records array is empty", file=sys.stderr)
        return 2

    try:
        records = [CaliperRecord(**r) for r in raw]
    except TypeError as e:
        print(f"caliper score: invalid record shape: {e}", file=sys.stderr)
        return 2

    evaluator = CaliperEvaluator(
        judge_model=args.judge_model,
    )

    report = asyncio.run(evaluator.evaluate(records, task_name=args.records.stem))
    print(render_bucket_table(report))

    if args.output:
        out_path = Path(args.output)
        out_data = {
            "task_name": report.task_name,
            "model_name": report.model_name,
            "overall": {
                "n_runs": report.overall.n_runs,
                "pass_count": report.overall.pass_count,
                "pass_rate": round(report.overall.pass_rate, 4),
                "lazy_count": report.overall.lazy_count,
                "lazy_rate": round(report.overall.lazy_rate, 4),
            },
            "buckets": {
                b.bucket: {
                    "n_runs": b.n_runs,
                    "pass_count": b.pass_count,
                    "pass_rate": round(b.pass_rate, 4),
                    "lazy_count": b.lazy_count,
                }
                for b in report.buckets
            },
        }
        out_path.write_text(json.dumps(out_data, indent=2) + "\n")
        print(f"\nReport saved: {out_path}")

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    from caliper.report import load_ab_diff, render_ab_diff

    for label, p in (("baseline", args.baseline), ("candidate", args.candidate)):
        if not p.exists():
            print(f"caliper diff: {label} log not found: {p}", file=sys.stderr)
            return 2

    diff = load_ab_diff(args.baseline, args.candidate)
    print(render_ab_diff(diff))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caliper",
        description=(
            "Caliper — read-time aggregation and A/B compare of Inspect AI eval logs."
        ),
    )
    sub = parser.add_subparsers(
        dest="cmd",
        metavar="<command>",
        required=True,
    )

    p_report = sub.add_parser(
        "report",
        help="print a per-bucket table for one .eval log",
        description=(
            "Read an Inspect AI .eval log and print a per-bucket "
            "table with pass / lazy / mean tokens / uncached input / "
            "cache hit rate columns."
        ),
    )
    p_report.add_argument("log", type=Path, help="path to .eval log file")
    p_report.set_defaults(func=cmd_report)

    p_score = sub.add_parser(
        "score",
        help="evaluate CaliperRecords from a JSON file",
        description=(
            "Read a JSON array of CaliperRecord objects and evaluate "
            "them. Each record represents one agent-task output. "
            "This is the CLI entry point for 'measurement-only mode' "
            "— external projects produce CaliperRecords in their own "
            "eval loop and feed them to caliper for scoring, "
            "aggregation, and reporting."
        ),
    )
    p_score.add_argument("records", type=Path, help="path to records.json")
    p_score.add_argument(
        "--judge-model",
        default="anthropic/claude-sonnet-4-6",
        help="model for the LLM judge (only used for records with reference_answer)",
    )
    p_score.add_argument(
        "--output",
        "-o",
        help="write the report as JSON to this path",
    )
    p_score.set_defaults(func=cmd_score)

    p_diff = sub.add_parser(
        "diff",
        help="A/B compare two .eval logs with noise-floor classification",
        description=(
            "Compare two .eval logs side by side. Per-bucket and "
            "overall deltas are classified as 'real' (|delta| > 2σ "
            "noise floor), 'noise' (within 2σ), or 'no estimate' "
            "(insufficient runs to compute σ). Cache regressions are "
            "called out at the end of the report."
        ),
    )
    p_diff.add_argument("baseline", type=Path, help="path to baseline .eval log")
    p_diff.add_argument("candidate", type=Path, help="path to candidate .eval log")
    p_diff.set_defaults(func=cmd_diff)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
