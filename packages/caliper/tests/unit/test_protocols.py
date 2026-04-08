"""Tests for the typed SolverState contract and metadata validation."""

from caliper.protocols import (
    OPTIONAL_METADATA_KEYS,
    REQUIRED_METADATA_KEYS,
    SolverState,
    validate_task_metadata,
)


def test_solver_state_defaults():
    # Construct without a store backing — uses model defaults.
    ss = SolverState()
    assert ss.agent_answer == ""
    assert ss.observed_page is False
    assert ss.commands_run == 0


def test_solver_state_assignment():
    ss = SolverState()
    ss.agent_answer = "the answer"
    ss.observed_page = True
    ss.commands_run = 3
    assert ss.agent_answer == "the answer"
    assert ss.observed_page is True
    assert ss.commands_run == 3


def test_validate_metadata_required_keys_present():
    errors = validate_task_metadata({"bucket": "lookup", "source": "WebVoyager"})
    assert errors == []


def test_validate_metadata_missing_required():
    errors = validate_task_metadata({"bucket": "lookup"})
    assert any("source" in e for e in errors)


def test_validate_metadata_with_optional_keys():
    md = {
        "bucket": "lookup",
        "source": "WebVoyager",
        "license": "academic",
        "is_time_sensitive": False,
        "last_validated": "2026-04-07",
        "start_url": "https://example.com",
    }
    errors = validate_task_metadata(md)
    assert errors == []


def test_validate_metadata_unknown_key_is_flagged_not_fatal():
    errors = validate_task_metadata(
        {"bucket": "lookup", "source": "WebVoyager", "frobnitz": 42}
    )
    # We expect a "soft" warning about the unknown key, not a hard
    # missing-required error. The flag itself is fine.
    assert any("frobnitz" in e for e in errors)
    # But the required keys are present, so no missing-required error.
    assert not any("missing required" in e for e in errors)


def test_required_and_optional_keys_disjoint():
    assert REQUIRED_METADATA_KEYS.isdisjoint(OPTIONAL_METADATA_KEYS)
