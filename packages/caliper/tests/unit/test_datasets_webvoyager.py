"""Tests for caliper.datasets.webvoyager loader.

Covers the contract that downstream report code (M1.4) and task
modules (caliper-browser-pilot) depend on:

- The 12 v8 curated tasks load with correct bucket distribution (3-3-3-3)
- Required metadata keys (``bucket``, ``source``) are enforced
- Unknown metadata keys are accepted with a warning, not an error
- ``filter_by_bucket`` returns a clean subset
- Malformed JSON / missing fields raise ``ValueError`` with line context
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from caliper.datasets import filter_by_bucket, load_webvoyager_jsonl

# The bp adapter ships the canonical 12-task v8 curated subset.
# We resolve the path relative to the workspace root, not the test file,
# so the test passes regardless of where pytest is invoked from.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_V8_PATH = (
    _REPO_ROOT
    / "packages"
    / "caliper-browser-pilot"
    / "src"
    / "caliper_browser_pilot"
    / "data"
    / "v8_curated.jsonl"
)


# ---------------------------------------------------------------------------
# Real-data integration: the v8 curated 12 tasks
# ---------------------------------------------------------------------------


def test_v8_curated_loads_twelve_samples():
    ds = load_webvoyager_jsonl(_V8_PATH)
    assert len(ds) == 12


def test_v8_curated_bucket_distribution():
    """The v8 curated set is 4 buckets × 3 tasks. This is the contract
    that ``baseline-v8.md`` anchors are computed against."""
    ds = load_webvoyager_jsonl(_V8_PATH)
    counts: dict[str, int] = {}
    for s in ds:
        b = (s.metadata or {}).get("bucket")
        counts[b] = counts.get(b, 0) + 1
    assert counts == {"lookup": 3, "search": 3, "compare": 3, "navigate": 3}


def test_v8_curated_has_expected_ids():
    ds = load_webvoyager_jsonl(_V8_PATH)
    ids = {s.id for s in ds}
    expected = {
        "Cambridge Dictionary--3",
        "Wolfram Alpha--0",
        "Wolfram Alpha--2",
        "Allrecipes--3",
        "Coursera--0",
        "Huggingface--3",
        "Apple--0",
        "Apple--3",
        "Allrecipes--0",
        "GitHub--3",
        "BBC News--5",
        "ArXiv--2",
    }
    assert ids == expected


def test_v8_curated_metadata_complete():
    ds = load_webvoyager_jsonl(_V8_PATH)
    for s in ds:
        md = s.metadata or {}
        # Required by caliper.protocols
        assert "bucket" in md
        assert "source" in md
        # Optional but expected for v8 curated tasks
        assert "license" in md
        assert "is_time_sensitive" in md
        assert "last_validated" in md
        assert "reference_type" in md
        assert "start_url" in md


def test_filter_by_bucket_returns_correct_subsets():
    ds = load_webvoyager_jsonl(_V8_PATH)
    lookup = filter_by_bucket(ds, "lookup")
    assert len(lookup) == 3
    assert {s.id for s in lookup} == {
        "Cambridge Dictionary--3",
        "Wolfram Alpha--0",
        "Wolfram Alpha--2",
    }


def test_filter_by_bucket_unknown_returns_empty():
    ds = load_webvoyager_jsonl(_V8_PATH)
    none = filter_by_bucket(ds, "nonexistent_bucket")
    assert len(none) == 0


# ---------------------------------------------------------------------------
# Validation policy: required keys enforced, unknown keys soft-warned
# ---------------------------------------------------------------------------


def test_missing_required_metadata_raises(tmp_path: Path):
    bad = tmp_path / "bad.jsonl"
    # Missing 'source' (required) — must raise.
    bad.write_text(
        json.dumps(
            {
                "id": "x",
                "input": "y",
                "target": "z",
                "metadata": {"bucket": "lookup"},
            }
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="missing required"):
        load_webvoyager_jsonl(bad)


def test_unknown_metadata_key_warns_but_loads(tmp_path: Path):
    ok = tmp_path / "ok_with_unknown.jsonl"
    ok.write_text(
        json.dumps(
            {
                "id": "x",
                "input": "y",
                "target": "z",
                "metadata": {
                    "bucket": "lookup",
                    "source": "WebVoyager",
                    "frobnitz": 42,  # unknown — should warn, not error
                },
            }
        )
        + "\n"
    )
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        ds = load_webvoyager_jsonl(ok)
    assert len(ds) == 1
    assert any("frobnitz" in str(w.message) for w in captured)


def test_missing_top_level_field_raises(tmp_path: Path):
    bad = tmp_path / "missing_target.jsonl"
    bad.write_text(json.dumps({"id": "x", "input": "y"}) + "\n")
    with pytest.raises(ValueError, match="target"):
        load_webvoyager_jsonl(bad)


def test_invalid_json_raises_with_line_number(tmp_path: Path):
    bad = tmp_path / "bad_json.jsonl"
    bad.write_text("{not valid json\n")
    with pytest.raises(ValueError, match=":1:"):
        load_webvoyager_jsonl(bad)


def test_blank_lines_are_skipped(tmp_path: Path):
    ok = tmp_path / "with_blanks.jsonl"
    record = json.dumps(
        {
            "id": "a",
            "input": "b",
            "target": "c",
            "metadata": {"bucket": "lookup", "source": "WebVoyager"},
        }
    )
    ok.write_text(f"\n{record}\n\n{record}\n\n")
    ds = load_webvoyager_jsonl(ok)
    assert len(ds) == 2


def test_missing_file_raises_FileNotFoundError(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_webvoyager_jsonl(tmp_path / "nope.jsonl")


def test_dataset_name_defaults_to_file_stem(tmp_path: Path):
    ok = tmp_path / "my_subset.jsonl"
    ok.write_text(
        json.dumps(
            {
                "id": "x",
                "input": "y",
                "target": "z",
                "metadata": {"bucket": "lookup", "source": "WebVoyager"},
            }
        )
        + "\n"
    )
    ds = load_webvoyager_jsonl(ok)
    assert ds.name == "my_subset"


def test_dataset_name_explicit_override(tmp_path: Path):
    ok = tmp_path / "x.jsonl"
    ok.write_text(
        json.dumps(
            {
                "id": "a",
                "input": "b",
                "target": "c",
                "metadata": {"bucket": "lookup", "source": "WebVoyager"},
            }
        )
        + "\n"
    )
    ds = load_webvoyager_jsonl(ok, name="custom-name")
    assert ds.name == "custom-name"
