"""Human-readable rendering of a ``BucketReport``.

Two output formats:

- ``render_bucket_table(report)`` — fixed-width ASCII table for
  terminal output. Used by the future ``caliper report`` CLI in M1.5
  and by manual REPL inspection right now.
- ``render_bucket_markdown(report)`` — Markdown table for pasting
  into docs / GitHub issues / commit messages.

Both share the same column set:

    bucket | pass        | lazy   | mean tokens | uncached in | cache hit

``cache hit`` is rendered as ``—`` (em-dash) when the bucket has
``cache_hit_rate=None``, which happens when no contributing sample
reported cache state at all (all-Bedrock bucket etc.). Coercing
``None`` to ``0%`` would be the same kind of "I don't know" → "I
know it's zero" lie that ``UsageSummary.has_cache_info`` exists to
prevent.
"""

from __future__ import annotations

from caliper.report.bucket import BucketReport, BucketStats

# ---------------------------------------------------------------------------
# Column formatting helpers
# ---------------------------------------------------------------------------

# Column widths chosen so the typical v8 baseline (12 tasks × 4
# buckets) fits in an 80-char terminal without wrapping.
_COL_BUCKET = 12
_COL_PASS = 12      # fits "23/24 100.0%"
_COL_LAZY = 8       # fits "1 (100%)"
_COL_TOKENS = 14    # fits "1,250,000"
_COL_UNCACHED = 14
_COL_CACHE = 10     # fits " 81.2%"


def _fmt_pass(b: BucketStats) -> str:
    """Format pass count as ``N/M  XX.X%``."""
    if b.n_runs == 0:
        return "—"
    pct = 100.0 * b.pass_rate
    return f"{b.pass_count}/{b.n_runs} {pct:5.1f}%"


def _fmt_lazy(b: BucketStats) -> str:
    """Format lazy count as ``N XX%``. ``0`` if none lazy."""
    if b.n_runs == 0:
        return "—"
    if b.lazy_count == 0:
        return "0"
    pct = 100.0 * b.lazy_rate
    return f"{b.lazy_count} ({pct:.0f}%)"


def _fmt_tokens(value: float) -> str:
    """Format a token count with thousands separator."""
    return f"{value:,.0f}"


def _fmt_cache_hit(b: BucketStats) -> str:
    """Format cache hit rate as ``XX.X%`` or ``—`` for unknown.

    The em-dash is the visible signal that the provider didn't
    report cache. Operators should never see ``0.0%`` for a bucket
    that had no cache to begin with.
    """
    rate = b.cache_hit_rate
    if rate is None:
        return "—"
    return f"{100.0 * rate:5.1f}%"


# ---------------------------------------------------------------------------
# ASCII table renderer
# ---------------------------------------------------------------------------


def render_bucket_table(report: BucketReport) -> str:
    """Render a fixed-width ASCII table.

    Layout:

        bucket       | pass     | lazy   | mean tokens   | uncached in   | cache hit
        ─────────────┼──────────┼────────┼───────────────┼───────────────┼──────────
        lookup       | 6/6 100.0%| 0     |        45,616 |         8,920 |   81.2%
        ...
        ─────────────┼──────────┼────────┼───────────────┼───────────────┼──────────
        TOTAL        | 23/24 95.8%| 0    |        56,153 |        20,200 |   74.0%

    Optional header row with task + model name + log path on top.
    """
    lines: list[str] = []

    # Header (task + model context, if known)
    header_bits: list[str] = []
    if report.task_name:
        header_bits.append(f"task: {report.task_name}")
    if report.model_name:
        header_bits.append(f"model: {report.model_name}")
    if report.log_path:
        header_bits.append(f"log: {report.log_path}")
    if header_bits:
        lines.append("  ".join(header_bits))
        lines.append("")

    # Column headers
    header = (
        f"{'bucket':<{_COL_BUCKET}} │ "
        f"{'pass':<{_COL_PASS}} │ "
        f"{'lazy':<{_COL_LAZY}} │ "
        f"{'mean tokens':>{_COL_TOKENS}} │ "
        f"{'uncached in':>{_COL_UNCACHED}} │ "
        f"{'cache hit':>{_COL_CACHE}}"
    )
    lines.append(header)
    lines.append(_divider())

    for b in report.buckets:
        lines.append(_format_row(b))

    lines.append(_divider())
    lines.append(_format_row(report.overall))

    return "\n".join(lines)


def _divider() -> str:
    """Horizontal divider matching the column widths."""
    return (
        "─" * _COL_BUCKET + "─┼─"
        + "─" * _COL_PASS + "─┼─"
        + "─" * _COL_LAZY + "─┼─"
        + "─" * _COL_TOKENS + "─┼─"
        + "─" * _COL_UNCACHED + "─┼─"
        + "─" * _COL_CACHE
    )


def _format_row(b: BucketStats) -> str:
    """One data row of the ASCII table."""
    return (
        f"{b.bucket:<{_COL_BUCKET}} │ "
        f"{_fmt_pass(b):<{_COL_PASS}} │ "
        f"{_fmt_lazy(b):<{_COL_LAZY}} │ "
        f"{_fmt_tokens(b.mean_total_tokens):>{_COL_TOKENS}} │ "
        f"{_fmt_tokens(b.mean_uncached_input_tokens):>{_COL_UNCACHED}} │ "
        f"{_fmt_cache_hit(b):>{_COL_CACHE}}"
    )


# ---------------------------------------------------------------------------
# Markdown table renderer
# ---------------------------------------------------------------------------


def render_bucket_markdown(report: BucketReport) -> str:
    """Render a Markdown-flavoured table for pasting into docs/issues.

    Same column set as ``render_bucket_table``. The TOTAL row uses
    bold formatting to set it apart from the per-bucket rows.
    """
    lines: list[str] = []

    if report.task_name or report.model_name:
        bits = []
        if report.task_name:
            bits.append(f"**task**: `{report.task_name}`")
        if report.model_name:
            bits.append(f"**model**: `{report.model_name}`")
        lines.append(" | ".join(bits))
        lines.append("")

    lines.append(
        "| bucket | pass | lazy | mean tokens | uncached in | cache hit |"
    )
    lines.append(
        "|---|---|---|---:|---:|---:|"
    )
    for b in report.buckets:
        lines.append(_format_md_row(b, bold=False))
    lines.append(_format_md_row(report.overall, bold=True))

    return "\n".join(lines)


def _format_md_row(b: BucketStats, *, bold: bool) -> str:
    """One data row of the Markdown table."""
    name = f"**{b.bucket}**" if bold else b.bucket
    return (
        f"| {name} "
        f"| {_fmt_pass(b)} "
        f"| {_fmt_lazy(b)} "
        f"| {_fmt_tokens(b.mean_total_tokens)} "
        f"| {_fmt_tokens(b.mean_uncached_input_tokens)} "
        f"| {_fmt_cache_hit(b)} |"
    )


__all__ = [
    "render_bucket_table",
    "render_bucket_markdown",
]
