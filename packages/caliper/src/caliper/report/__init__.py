"""Report layer — read-time aggregation of Inspect AI ``.eval`` logs.

Currently exports the bucket report API (M1.4). M1.5 will add A/B
compare against this same primitive set; Phase 3 adds multi-dim
reports for the chatbot scenario.

Modules:
    bucket — per-bucket aggregation: SampleResult, BucketStats,
             BucketReport, load_bucket_report
    render — human-readable formats: render_bucket_table (ASCII),
             render_bucket_markdown
"""

from caliper.report.bucket import (
    DEFAULT_JUDGE_SCORER,
    DEFAULT_LAZY_SCORER,
    TOTAL_BUCKET,
    UNGROUPED_BUCKET,
    BucketReport,
    BucketStats,
    SampleResult,
    load_bucket_report,
)
from caliper.report.render import render_bucket_markdown, render_bucket_table

__all__ = [
    "DEFAULT_JUDGE_SCORER",
    "DEFAULT_LAZY_SCORER",
    "TOTAL_BUCKET",
    "UNGROUPED_BUCKET",
    "BucketReport",
    "BucketStats",
    "SampleResult",
    "load_bucket_report",
    "render_bucket_markdown",
    "render_bucket_table",
]
