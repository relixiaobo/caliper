"""Caliper scorers — judge, lazy detection, JSON verdict parsing, multi-dim base.

All scorers in this module are tool-agnostic. They read state via the
typed ``SolverState`` contract from ``caliper.protocols`` or via
metadata the task definition chose to publish, never via string-keyed
``state.store`` access.
"""

from caliper.scorers.judge_stale_ref import judge_stale_ref
from caliper.scorers.json_verdict import parse_judge_verdict
from caliper.scorers.lazy_detection import lazy_detection
from caliper.scorers.verify_commands import verify_commands

__all__ = [
    "parse_judge_verdict",
    "judge_stale_ref",
    "lazy_detection",
    "verify_commands",
]
