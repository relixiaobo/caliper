"""Tests for caliper.report.render — table + markdown output formats."""

from __future__ import annotations

from caliper.metrics import UsageSummary
from caliper.report.bucket import (
    TOTAL_BUCKET,
    BucketReport,
    BucketStats,
)
from caliper.report.render import render_bucket_markdown, render_bucket_table


def _mk_bucket(
    *,
    name: str,
    n_runs: int = 6,
    pass_count: int = 6,
    lazy_count: int = 0,
    input_tokens: int = 30_000,
    output_tokens: int = 6_000,
    cache_read: int = 0,
    cache_write: int = 0,
    has_cache_info: bool = True,
) -> BucketStats:
    """Build a BucketStats with controlled token totals."""
    cache_aware = (
        input_tokens + cache_read + cache_write if has_cache_info else 0
    )
    usage = UsageSummary(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        has_reasoning_info=False,
        has_cache_info=has_cache_info,
        cache_aware_input_tokens=cache_aware,
    )
    return BucketStats(
        bucket=name,
        n_runs=n_runs,
        n_unique_samples=n_runs,
        pass_count=pass_count,
        lazy_count=lazy_count,
        total_usage=usage,
    )


def _mk_report(buckets: list[BucketStats]) -> BucketReport:
    """Build a BucketReport with a TOTAL row computed from buckets."""
    total_usage = UsageSummary.zero()
    n_runs = 0
    pass_count = 0
    lazy_count = 0
    for b in buckets:
        total_usage = total_usage + b.total_usage
        n_runs += b.n_runs
        pass_count += b.pass_count
        lazy_count += b.lazy_count
    overall = BucketStats(
        bucket=TOTAL_BUCKET,
        n_runs=n_runs,
        n_unique_samples=n_runs,
        pass_count=pass_count,
        lazy_count=lazy_count,
        total_usage=total_usage,
    )
    return BucketReport(
        buckets=buckets,
        overall=overall,
        samples=[],
        log_path=None,
        task_name="test_task",
        model_name="anthropic/claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# render_bucket_table
# ---------------------------------------------------------------------------


def test_render_table_includes_header_with_task_and_model():
    report = _mk_report([_mk_bucket(name="lookup")])
    out = render_bucket_table(report)
    assert "task: test_task" in out
    assert "model: anthropic/claude-sonnet-4-6" in out


def test_render_table_includes_column_headers():
    report = _mk_report([_mk_bucket(name="lookup")])
    out = render_bucket_table(report)
    for header in ("bucket", "pass", "lazy", "mean tokens", "uncached in", "cache hit"):
        assert header in out


def test_render_table_includes_total_row():
    report = _mk_report([_mk_bucket(name="lookup"), _mk_bucket(name="search")])
    out = render_bucket_table(report)
    assert "TOTAL" in out


def test_render_table_pass_format_includes_count_and_percent():
    report = _mk_report([_mk_bucket(name="lookup", n_runs=6, pass_count=5)])
    out = render_bucket_table(report)
    assert "5/6" in out
    assert "83.3%" in out


def test_render_table_lazy_zero_shows_just_zero():
    report = _mk_report([_mk_bucket(name="lookup", lazy_count=0)])
    out = render_bucket_table(report)
    # The lazy column should show "0" (not "0 (0%)") when none are lazy
    lines = out.split("\n")
    lookup_line = next(line for line in lines if "lookup" in line)
    # Look between the second and third pipe for the lazy column
    parts = lookup_line.split("│")
    assert parts[2].strip() == "0"


def test_render_table_lazy_nonzero_shows_count_and_percent():
    report = _mk_report([_mk_bucket(name="lookup", n_runs=4, lazy_count=1)])
    out = render_bucket_table(report)
    assert "1 (25%)" in out


def test_render_table_cache_hit_shows_em_dash_when_unknown():
    """REGRESSION GUARD: cache_hit_rate=None must render as ``—``,
    not ``0.0%``. The Bedrock case must remain visually distinct from
    a real cold cache."""
    bedrock_bucket = _mk_bucket(
        name="navigate",
        cache_read=0,
        cache_write=0,
        has_cache_info=False,
    )
    report = _mk_report([bedrock_bucket])
    out = render_bucket_table(report)
    assert "—" in out, "cache-silent bucket must render as em-dash"
    # Look at the cache column (last column) of the navigate row only,
    # NOT the whole line — pass-rate "100.0%" contains "0.0%" as
    # substring and would false-positive an "in line" check.
    lines = out.split("\n")
    navigate_line = next(line for line in lines if "navigate" in line)
    cache_col = navigate_line.split("│")[-1].strip()
    assert cache_col == "—", f"cache column must be em-dash, got {cache_col!r}"


def test_render_table_cache_hit_shows_percent_when_known():
    bucket = _mk_bucket(
        name="lookup",
        cache_read=8_000,
        input_tokens=2_000,
        has_cache_info=True,
    )
    report = _mk_report([bucket])
    out = render_bucket_table(report)
    # 8000 / (2000 + 8000) = 0.8 = 80.0%
    assert "80.0%" in out


def test_render_table_token_thousands_separator():
    bucket = _mk_bucket(name="lookup", input_tokens=12_345, output_tokens=678)
    report = _mk_report([bucket])
    out = render_bucket_table(report)
    # Total = 13023; mean over 6 runs = 2170.5 → "2,171"
    assert "2,171" in out or "2,170" in out  # depends on rounding


# ---------------------------------------------------------------------------
# render_bucket_markdown
# ---------------------------------------------------------------------------


def test_render_markdown_starts_with_task_and_model_header():
    report = _mk_report([_mk_bucket(name="lookup")])
    out = render_bucket_markdown(report)
    assert "**task**: `test_task`" in out
    assert "**model**: `anthropic/claude-sonnet-4-6`" in out


def test_render_markdown_has_table_header_and_alignment():
    report = _mk_report([_mk_bucket(name="lookup")])
    out = render_bucket_markdown(report)
    assert "| bucket | pass | lazy | mean tokens | uncached in | cache hit |" in out
    assert "|---|---|---|---:|---:|---:|" in out


def test_render_markdown_total_row_is_bold():
    report = _mk_report([_mk_bucket(name="lookup")])
    out = render_bucket_markdown(report)
    assert "**TOTAL**" in out


def test_render_markdown_cache_unknown_shows_em_dash():
    bucket = _mk_bucket(
        name="bedrock",
        has_cache_info=False,
        cache_read=0,
        cache_write=0,
    )
    report = _mk_report([bucket])
    out = render_bucket_markdown(report)
    # Find the bedrock row (not TOTAL) and check the cache column
    # specifically — pass column "100.0%" contains "0.0%" as substring.
    bedrock_line = next(
        line for line in out.split("\n") if "bedrock" in line and "**" not in line
    )
    cache_col = bedrock_line.rstrip("|").split("|")[-1].strip()
    assert cache_col == "—", f"markdown cache column must be em-dash, got {cache_col!r}"
