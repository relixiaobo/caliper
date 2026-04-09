"""Tests for the ``verify_commands`` post-hoc verification scorer.

The scorer is used by Layer 1 smoke tasks (e.g. caliper-browser-pilot's
``tasks/smoke.py``). Its contract:

1. Read ``state.metadata["verify"]`` — a list of dicts with
   ``command`` (argv), ``expect_contains`` (substring), optional
   ``description``.
2. Run each command via ``run_cli`` (mocked here).
3. CORRECT iff every spec's expected substring appears in the
   corresponding command's stdout. INCORRECT otherwise, with per-spec
   failure detail in the explanation.

These tests mock ``run_cli`` to avoid any real subprocess execution.
The integration "does it actually work end-to-end against bp" check
is the ``inspect eval .../tasks/smoke.py`` run from M1.7a itself,
not this file.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from caliper.scorers.verify_commands import verify_commands


class _FakeSolverState:
    """Stand-in for ``caliper.protocols.SolverState`` — the scorer
    reads ``.agent_answer`` off whatever ``state.store_as(SolverState)``
    returns."""

    def __init__(self, agent_answer: str):
        self.agent_answer = agent_answer


class _FakeState:
    """Tiny stand-in for an Inspect AI TaskState. The scorer touches:
      - ``state.metadata`` for the verify specs
      - ``state.store_as(SolverState).agent_answer`` when
        ``require_agent_answer=True``

    Default ``agent_answer`` is ``"done"`` (non-empty) so existing
    happy-path tests continue to pass the implicit M1.7a-post-review
    "did the agent actually finish" check. Pass ``agent_answer=""``
    to exercise the new fail path.
    """

    def __init__(self, metadata: dict | None, agent_answer: str = "done"):
        self.metadata = metadata
        self._agent_answer = agent_answer

    def store_as(self, _cls):  # noqa: ARG002 — we don't care about the type
        return _FakeSolverState(self._agent_answer)


class _FakeTarget:
    """The scorer doesn't read target, but Score's signature wants one."""

    text = ""


def _run_scorer(
    state: _FakeState,
    *,
    fake_outputs: dict | None = None,
    require_agent_answer: bool = True,
):
    """Invoke the scorer with a mocked run_cli. ``fake_outputs`` maps
    a tuple(argv) key to the string run_cli should return. Any command
    not in the map returns an empty string (which will usually fail
    verification — easy way to simulate "command ran but didn't output
    the expected substring")."""
    fake_outputs = fake_outputs or {}

    async def fake_run_cli(argv, timeout=30.0):
        key = tuple(argv)
        return fake_outputs.get(key, "")

    scorer_factory = verify_commands(require_agent_answer=require_agent_answer)
    with patch("caliper.runtime.run_cli", side_effect=fake_run_cli):
        return asyncio.run(scorer_factory(state, _FakeTarget()))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_single_passing_spec():
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "Both checkboxes checked",
                    "command": ["bp", "eval", "count"],
                    "expect_contains": "2",
                }
            ]
        }
    )
    score = _run_scorer(state, fake_outputs={("bp", "eval", "count"): "2\n"})
    assert score.value is True
    assert "1 verify steps passed" in score.explanation
    assert score.metadata["n_specs"] == 1


def test_multiple_specs_all_pass():
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "success msg",
                    "command": ["bp", "eval", "flash"],
                    "expect_contains": "You logged into a secure area!",
                },
                {
                    "description": "url changed",
                    "command": ["bp", "eval", "path"],
                    "expect_contains": "/secure",
                },
            ]
        }
    )
    score = _run_scorer(
        state,
        fake_outputs={
            ("bp", "eval", "flash"): "You logged into a secure area! Welcome.",
            ("bp", "eval", "path"): "/secure",
        },
    )
    assert score.value is True
    assert "2 verify steps passed" in score.explanation


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_missing_expected_substring_fails():
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "Both checkboxes checked",
                    "command": ["bp", "eval", "count"],
                    "expect_contains": "2",
                }
            ]
        }
    )
    score = _run_scorer(state, fake_outputs={("bp", "eval", "count"): "1\n"})
    assert score.value is False
    assert "Both checkboxes checked" in score.explanation
    assert "expected '2'" in score.explanation


def test_second_spec_failure_reported_per_spec():
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "success msg",
                    "command": ["bp", "eval", "flash"],
                    "expect_contains": "You logged into a secure area!",
                },
                {
                    "description": "url changed",
                    "command": ["bp", "eval", "path"],
                    "expect_contains": "/secure",
                },
            ]
        }
    )
    score = _run_scorer(
        state,
        fake_outputs={
            ("bp", "eval", "flash"): "You logged into a secure area! Welcome.",
            # path command returns /login — verification fails
            ("bp", "eval", "path"): "/login",
        },
    )
    assert score.value is False
    # Only the second spec failed; explanation should name it.
    assert "url changed" in score.explanation
    assert "/secure" in score.explanation
    # The first spec's success shouldn't appear in the explanation.
    assert "success msg" not in score.explanation
    # But both results should be present in metadata for post-hoc review.
    assert len(score.metadata["results"]) == 2
    assert score.metadata["results"][0]["passed"] is True
    assert score.metadata["results"][1]["passed"] is False


def test_run_cli_error_counts_as_failure():
    """If the verification command itself errors out, the spec fails
    — even if the error string happens to contain the expected
    substring. This prevents the pathological case where ``ERROR:
    not found: 2`` would pass a ``expect_contains="2"`` check."""
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "count",
                    "command": ["bp", "eval", "broken"],
                    "expect_contains": "2",
                }
            ]
        }
    )
    score = _run_scorer(
        state,
        fake_outputs={
            ("bp", "eval", "broken"): "ERROR (exit 1): something broke with 2 things"
        },
    )
    assert score.value is False
    assert "command failed" in score.explanation


# ---------------------------------------------------------------------------
# Metadata edge cases
# ---------------------------------------------------------------------------


def test_no_verify_metadata_returns_incorrect():
    state = _FakeState({})
    score = _run_scorer(state)
    assert score.value is False
    assert "no verify commands" in score.explanation
    assert score.metadata["n_specs"] == 0


def test_empty_verify_list_returns_incorrect():
    state = _FakeState({"verify": []})
    score = _run_scorer(state)
    assert score.value is False
    assert "no verify commands" in score.explanation


def test_none_metadata_returns_incorrect():
    state = _FakeState(None)
    score = _run_scorer(state)
    assert score.value is False
    assert "no verify commands" in score.explanation


def test_spec_with_empty_command_fails():
    state = _FakeState(
        {"verify": [{"description": "bad", "command": [], "expect_contains": "x"}]}
    )
    score = _run_scorer(state)
    assert score.value is False
    assert "empty command" in score.explanation


# ---------------------------------------------------------------------------
# Agent-answer invariant (M1.7a Codex review P2a)
# ---------------------------------------------------------------------------


def test_verify_passes_but_empty_agent_answer_fails_by_default():
    """The P2a fix: a sample where the browser state matches the
    verify spec but the agent loop crashed / regressed / never
    produced ANSWER should NOT score as CORRECT. This catches
    solver-plumbing breakage that pure post-hoc DOM checks would
    miss."""
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "Both checkboxes checked",
                    "command": ["bp", "eval", "count"],
                    "expect_contains": "2",
                }
            ]
        },
        agent_answer="",  # simulate solver-loop failure
    )
    score = _run_scorer(state, fake_outputs={("bp", "eval", "count"): "2\n"})
    assert score.value is False
    assert "no ANSWER:" in score.explanation
    assert "SolverState.agent_answer is empty" in score.explanation


def test_verify_passes_with_non_empty_agent_answer():
    """Happy path: verify specs pass AND agent_answer is non-empty.
    The explanation should surface the answer so it's visible in
    the report."""
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "Both checkboxes checked",
                    "command": ["bp", "eval", "count"],
                    "expect_contains": "2",
                }
            ]
        },
        agent_answer="Done. Both boxes are now checked.",
    )
    score = _run_scorer(state, fake_outputs={("bp", "eval", "count"): "2\n"})
    assert score.value is True
    assert score.answer == "Done. Both boxes are now checked."
    # Happy-path explanation should note the agent answer.
    assert "agent_answer:" in score.explanation


def test_require_agent_answer_false_tolerates_empty_answer():
    """Opt-out: require_agent_answer=False lets verify-only tasks
    pass without any ANSWER block. Intended for tasks whose
    semantic is entirely "do X and leave the state visible" with
    no agent narration."""
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "Both checkboxes checked",
                    "command": ["bp", "eval", "count"],
                    "expect_contains": "2",
                }
            ]
        },
        agent_answer="",
    )
    score = _run_scorer(
        state,
        fake_outputs={("bp", "eval", "count"): "2\n"},
        require_agent_answer=False,
    )
    assert score.value is True
    # With the check disabled, explanation should NOT mention
    # agent_answer at all.
    assert "agent_answer" not in score.explanation
    assert "ANSWER" not in score.explanation


def test_empty_answer_and_verify_failure_both_reported():
    """Both failure modes should be surfaced in the same
    explanation — one should not mask the other. Helpful when
    debugging a regression that broke both the solver AND the
    verification target simultaneously."""
    state = _FakeState(
        {
            "verify": [
                {
                    "description": "Both checkboxes checked",
                    "command": ["bp", "eval", "count"],
                    "expect_contains": "2",
                }
            ]
        },
        agent_answer="",
    )
    score = _run_scorer(state, fake_outputs={("bp", "eval", "count"): "1\n"})
    assert score.value is False
    # Both the verify failure and the empty-answer failure should
    # appear in the explanation.
    assert "Both checkboxes checked" in score.explanation
    assert "expected '2'" in score.explanation
    assert "no ANSWER:" in score.explanation
