"""Human-readable rendering of report objects.

Three output formats:

- ``render_bucket_table(report)`` — fixed-width ASCII table for
  terminal output. Used by ``caliper report``.
- ``render_bucket_markdown(report)`` — Markdown table for pasting
  into docs / GitHub issues / commit messages.
- ``render_ab_diff(diff)`` — vertical per-bucket layout for A/B
  comparison output. Used by ``caliper diff``.

Bucket-level shared column set:

    bucket | pass | lazy | mean tokens | uncached in | cache hit

``cache hit`` is rendered as ``—`` (em-dash) when the bucket has
``cache_hit_rate=None``, which happens when no contributing sample
reported cache state at all (all-Bedrock bucket etc.). Coercing
``None`` to ``0%`` would be the same kind of "I don't know" → "I
know it's zero" lie that ``UsageSummary.has_cache_info`` exists to
prevent.
"""

from __future__ import annotations

from caliper.report.ab import ABDiff, BucketDiff, MetricDelta
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


# ---------------------------------------------------------------------------
# A/B diff renderer
# ---------------------------------------------------------------------------


def render_ab_diff(diff: ABDiff) -> str:
    """Render an ``ABDiff`` as a vertical per-bucket report.

    Vertical layout is more readable than a wide table when each
    bucket has 4+ metrics × 4 columns (baseline / candidate / delta /
    classification). One section per bucket plus a TOTAL section,
    with cache-regression warnings called out at the end.

    Example output:

        Baseline:  task=v8_baseline  log=...
        Candidate: task=v8_baseline  log=...

        === lookup ===
          pass:        6/6 100.0% → 6/6 100.0%   (+0.0,  noise)
          mean tokens: 45,616 → 41,200           (-9.7%, real)
          uncached:     8,920 →  7,800           (-12.6%, real)
          cache hit:    0.81 →  0.83             (+0.02, noise)

        === compare ===
          pass:        5/6  83.3% → 5/6  83.3%   (+0.0,  noise)
          mean tokens: 105,841 → 92,300          (-12.8%, real)
          uncached:    62,210 → 78,500           (+26.2%, real)
          cache hit:    0.41 →  0.18             (-0.23, real)

        === TOTAL ===
          ...

        ⚠ compare bucket: mean tokens dropped 12.8% but cache_hit_rate
          dropped 0.23. Likely SKILL.md cache prefix was invalidated.
          Investigate.
    """
    lines: list[str] = []

    # Header — task / model / log paths for both sides
    base_name = diff.baseline.task_name or "<unknown>"
    cand_name = diff.candidate.task_name or "<unknown>"
    lines.append(f"Baseline:  task={base_name}  log={diff.baseline.log_path}")
    lines.append(f"Candidate: task={cand_name}  log={diff.candidate.log_path}")
    lines.append("")

    for bucket_diff in diff.bucket_diffs:
        lines.extend(_render_bucket_section(bucket_diff))
        lines.append("")

    # TOTAL section last — clearly delineated
    lines.extend(_render_bucket_section(diff.overall, is_total=True))

    # Cache-regression warnings (if any) appended at the bottom so
    # they can't be missed in long reports.
    warnings = diff.cache_regression_warnings
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(w)

    return "\n".join(lines)


def _render_bucket_section(diff: BucketDiff, *, is_total: bool = False) -> list[str]:
    """Format one bucket's metrics block."""
    title = "TOTAL" if is_total else diff.bucket
    n_info = f"  ({diff.n_runs_baseline} → {diff.n_runs_candidate} runs)"
    section: list[str] = [f"=== {title} ==={n_info}"]
    section.append(f"  pass:         {_fmt_pass_delta(diff.pass_rate)}")
    section.append(
        f"  mean tokens:  {_fmt_continuous_delta(diff.mean_total_tokens, integer=True)}"
    )
    section.append(
        f"  uncached:     {_fmt_continuous_delta(diff.mean_uncached_input_tokens, integer=True)}"
    )
    section.append(f"  cache hit:    {_fmt_cache_hit_delta(diff.cache_hit_rate)}")
    return section


def _fmt_pass_delta(m: MetricDelta) -> str:
    """Format pass_rate as ``XX.X% → YY.Y%   (Δ%, label)``."""
    base = m.baseline
    cand = m.candidate
    if base is None or cand is None:
        return "(no data)"
    base_pct = 100.0 * base
    cand_pct = 100.0 * cand
    delta_pct = cand_pct - base_pct
    sign = "+" if delta_pct >= 0 else ""
    label = _classification_label(m)
    return f"{base_pct:5.1f}% → {cand_pct:5.1f}%   ({sign}{delta_pct:.1f}pp, {label})"


def _fmt_continuous_delta(m: MetricDelta, *, integer: bool) -> str:
    """Format a continuous-metric delta as ``X → Y  (Δ%, label)``."""
    base = m.baseline
    cand = m.candidate
    if base is None or cand is None:
        return "(no data)"
    if integer:
        base_str = f"{base:,.0f}"
        cand_str = f"{cand:,.0f}"
    else:
        base_str = f"{base:.3f}"
        cand_str = f"{cand:.3f}"
    if base != 0:
        delta_pct = 100.0 * (cand - base) / base
        sign = "+" if delta_pct >= 0 else ""
        delta_str = f"{sign}{delta_pct:.1f}%"
    else:
        delta_str = f"{cand - base:+,.0f}"
    label = _classification_label(m)
    return f"{base_str} → {cand_str}   ({delta_str}, {label})"


def _fmt_cache_hit_delta(m: MetricDelta) -> str:
    """Format cache_hit_rate as ``0.XX → 0.YY  (Δ, label)`` with em-dash
    fallback when either side is None."""
    base = m.baseline
    cand = m.candidate
    if base is None and cand is None:
        return "—  → —"
    if base is None:
        return f"—  → {cand:.2f}   (no baseline cache info)"
    if cand is None:
        return f"{base:.2f} → —   (no candidate cache info)"
    delta = cand - base
    sign = "+" if delta >= 0 else ""
    label = _classification_label(m)
    return f"{base:.2f} → {cand:.2f}   ({sign}{delta:.2f}, {label})"


def _classification_label(m: MetricDelta) -> str:
    """Map MetricDelta.classification to a render-friendly label."""
    cls = m.classification
    if cls == "real":
        return "real"
    if cls == "noise":
        return "noise"
    return "no estimate"


__all__ = [
    "render_bucket_table",
    "render_bucket_markdown",
    "render_ab_diff",
]
