"""Smoke tests for caliper-browser-pilot tools.

These exercise the bp-specific helpers (snapshot formatter, observation
set, SKILL path resolver) without making any network calls or starting bp.
"""

from __future__ import annotations

import json
import os

from caliper_browser_pilot.tools import (
    BP_OBSERVATION_COMMANDS,
    bp_skill_path,
    bp_truncate_snapshot,
)


def test_observation_commands_contains_expected_set():
    expected = {"read", "snapshot", "eval", "screenshot", "tabs", "cookies", "locate"}
    assert BP_OBSERVATION_COMMANDS == frozenset(expected)


def test_truncate_snapshot_handles_read_result():
    raw = json.dumps(
        {"title": "Example", "url": "https://example.com", "text": "hello world"}
    )
    out = bp_truncate_snapshot(raw)
    assert "Example" in out
    assert "hello world" in out


def test_truncate_snapshot_handles_elements_result():
    raw = json.dumps(
        {
            "title": "Example",
            "url": "https://example.com",
            "elements": [
                {"ref": 1, "role": "link", "name": "Home"},
                {"ref": 2, "role": "button", "name": "Login"},
            ],
        }
    )
    out = bp_truncate_snapshot(raw)
    assert '[1] link "Home"' in out
    assert '[2] button "Login"' in out


def test_truncate_snapshot_falls_through_for_non_json():
    out = bp_truncate_snapshot("not json at all")
    assert out == "not json at all"


def test_truncate_snapshot_caps_long_strings():
    out = bp_truncate_snapshot("x" * 5000)
    assert len(out) == 3000


def test_skill_path_respects_env_var(tmp_path, monkeypatch):
    fake_skill = tmp_path / "FAKE_SKILL.md"
    fake_skill.write_text("# fake skill")
    monkeypatch.setenv("CALIPER_BP_SKILL_PATH", str(fake_skill))
    result = bp_skill_path()
    assert result == fake_skill


def test_skill_path_returns_none_when_unfindable(tmp_path, monkeypatch):
    monkeypatch.delenv("CALIPER_BP_SKILL_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    # tmp_path has no browser-pilot directory; resolver should return None
    # rather than raising.
    result = bp_skill_path()
    assert result is None
