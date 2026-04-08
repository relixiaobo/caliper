"""``caliper`` CLI — thin wrapper over the report API.

Two subcommands:

    caliper report  <log.eval>                 → bucket table
    caliper diff    <baseline.eval> <candidate.eval>
                                                → A/B diff with noise floor

The CLI is intentionally minimal: argparse stdlib only (no click
dependency), one file, no business logic. Everything substantive
lives in ``caliper.report``; this module just dispatches.

Why a CLI exists at all (Inspect AI already has ``inspect view``):
``inspect view`` shows per-sample detail and the live progress
during ``inspect eval``. Neither of those is per-bucket aggregation
or A/B comparison — those are caliper's value-add.

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
            "Caliper — read-time aggregation and A/B compare of "
            "Inspect AI eval logs."
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
