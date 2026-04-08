"""Tests for caliper.cli — argparse + dispatch to report subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest

from caliper.cli import build_parser, main


# ---------------------------------------------------------------------------
# Argparse parsing
# ---------------------------------------------------------------------------


def test_parser_has_report_subcommand():
    parser = build_parser()
    args = parser.parse_args(["report", "logs/example.eval"])
    assert args.cmd == "report"
    assert args.log == Path("logs/example.eval")


def test_parser_has_diff_subcommand():
    parser = build_parser()
    args = parser.parse_args(["diff", "base.eval", "cand.eval"])
    assert args.cmd == "diff"
    assert args.baseline == Path("base.eval")
    assert args.candidate == Path("cand.eval")


def test_parser_requires_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_report_requires_log_arg():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["report"])


def test_parser_diff_requires_two_args():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["diff", "only_one.eval"])


# ---------------------------------------------------------------------------
# main() dispatch — returns non-zero on missing files (exit code surface)
# ---------------------------------------------------------------------------


def test_main_report_missing_log_returns_2(tmp_path: Path, capsys):
    rc = main(["report", str(tmp_path / "nope.eval")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_main_diff_missing_baseline_returns_2(tmp_path: Path, capsys):
    candidate = tmp_path / "cand.eval"
    candidate.write_text("")  # exists but empty (won't actually load)
    rc = main(["diff", str(tmp_path / "missing.eval"), str(candidate)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "baseline" in captured.err
    assert "not found" in captured.err


def test_main_diff_missing_candidate_returns_2(tmp_path: Path, capsys):
    baseline = tmp_path / "base.eval"
    baseline.write_text("")
    rc = main(["diff", str(baseline), str(tmp_path / "missing.eval")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "candidate" in captured.err
    assert "not found" in captured.err


# ---------------------------------------------------------------------------
# main() dispatch — happy path against a real eval log
# ---------------------------------------------------------------------------


def _find_any_eval_log() -> Path | None:
    """Same helper pattern as test_report_bucket: skip if no log."""
    repo_root = Path(__file__).resolve().parents[4]
    logs = sorted((repo_root / "logs").glob("*.eval"))
    return logs[-1] if logs else None


def test_main_report_against_real_log_returns_0(capsys):
    log = _find_any_eval_log()
    if log is None:
        pytest.skip("no .eval logs available; run an eval first")
    rc = main(["report", str(log)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "bucket" in captured.out  # column header
    assert "TOTAL" in captured.out


def test_main_diff_self_against_real_log_returns_0(capsys):
    """Diffing a log against itself is the cheapest end-to-end smoke
    test for the diff path. Every delta should be 'no estimate' or
    'noise' depending on n_runs."""
    log = _find_any_eval_log()
    if log is None:
        pytest.skip("no .eval logs available; run an eval first")
    rc = main(["diff", str(log), str(log)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Baseline:" in captured.out
    assert "Candidate:" in captured.out
    assert "TOTAL" in captured.out
