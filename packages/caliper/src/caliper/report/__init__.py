"""Report layer — read-time aggregation of Inspect AI ``.eval`` logs.

Currently exports:
- Bucket report API (M1.4): SampleResult, BucketStats, BucketReport,
  load_bucket_report + render_bucket_table / render_bucket_markdown
- A/B diff API (M1.5): MetricDelta, BucketDiff, ABDiff,
  compute_ab_diff / load_ab_diff + render_ab_diff

Phase 3 adds multi-dim reports for the chatbot scenario.

Modules:
    bucket — per-bucket aggregation
    ab     — A/B diff with noise floor + cache regression detection
    render — human-readable formats (ASCII + Markdown)
"""

from caliper.report.ab import (
    ABDiff,
    BucketDiff,
    MetricDelta,
    compute_ab_diff,
    load_ab_diff,
)
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
from caliper.report.render import (
    render_ab_diff,
    render_bucket_markdown,
    render_bucket_table,
)

__all__ = [
    "ABDiff",
    "BucketDiff",
    "BucketReport",
    "BucketStats",
    "DEFAULT_JUDGE_SCORER",
    "DEFAULT_LAZY_SCORER",
    "MetricDelta",
    "SampleResult",
    "TOTAL_BUCKET",
    "UNGROUPED_BUCKET",
    "compute_ab_diff",
    "load_ab_diff",
    "load_bucket_report",
    "render_ab_diff",
    "render_bucket_markdown",
    "render_bucket_table",
]
