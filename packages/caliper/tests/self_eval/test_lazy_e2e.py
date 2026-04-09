"""M2.2 extension: end-to-end lazy detection through the solver pipeline.

The original M2.2 tests feed hand-authored (agent_answer, observed)
pairs into score_lazy, verifying only the boolean formula. Codex
adversarial review correctly identified that the REAL risk is in
how ``observed_page`` gets set by the solver — command classification,
failed observation commands, edge cases where the agent emits an
observation verb but doesn't actually see the target.

These tests exercise the full pipeline:
    text_protocol_agent → command extraction → observation tracking
    → SolverState.observed_page → score_lazy

Using mocked run_cli and mocked LLM, so no real subprocess or
API calls. Runs in <1 second.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import TaskState

from caliper.protocols import SolverState
from caliper.solvers.text_protocol import text_protocol_agent


def _make_state() -> TaskState:
    return TaskState(
        model="test/test",
        sample_id="e2e-lazy",
        epoch=1,
        input=[ChatMessageUser(content="Test task")],
        messages=[],
        metadata={"start_url": "https://example.com/"},
    )


def _run_with_agent_responses(
    responses: list[str],
    observation_commands: frozenset[str] = frozenset({"read", "snapshot", "eval"}),
) -> SolverState:
    """Drive the solver with a sequence of mocked LLM responses.
    Returns the final SolverState so we can check observed_page."""

    call_idx = {"n": 0}

    async def fake_run_cli(argv, timeout=60.0):
        return f"ok: {' '.join(argv)}"

    class MockModel:
        def __init__(self, replies):
            self._replies = replies
            self._idx = 0

        async def generate(self, messages):
            if self._idx < len(self._replies):
                text = self._replies[self._idx]
                self._idx += 1
            else:
                text = "ANSWER: done"
            return type("R", (), {"completion": text})()

    model = MockModel(responses)
    state = _make_state()

    solver_fn = text_protocol_agent(
        cli_name="bp",
        observation_commands=observation_commands,
        system_prompt="test",
        session_prologue=[],  # skip bp disconnect/connect in tests
    )

    async def _drive():
        with (
            patch("caliper.solvers.text_protocol.run_cli", side_effect=fake_run_cli),
            patch("caliper.solvers.text_protocol.get_model", return_value=model),
        ):
            await solver_fn(state, None)  # type: ignore[arg-type]

    asyncio.run(_drive())
    return state.store_as(SolverState)


# ---------------------------------------------------------------------------
# Observation command correctly sets observed_page
# ---------------------------------------------------------------------------


def test_observation_command_sets_observed_true():
    """Agent emits a 'bp read' (observation command) then answers.
    observed_page must be True."""
    ss = _run_with_agent_responses(
        [
            "Let me read the page.\nbp read",
            "ANSWER: The page says hello",
        ]
    )
    assert ss.observed_page is True
    assert ss.agent_answer == "The page says hello"


def test_snapshot_command_sets_observed_true():
    """'bp snapshot' is also an observation command."""
    ss = _run_with_agent_responses(
        [
            "bp snapshot --limit 30",
            "ANSWER: I see a login form",
        ]
    )
    assert ss.observed_page is True


def test_eval_command_sets_observed_true():
    """'bp eval' is an observation command."""
    ss = _run_with_agent_responses(
        [
            'bp eval "document.title"',
            "ANSWER: The title is Example",
        ]
    )
    assert ss.observed_page is True


# ---------------------------------------------------------------------------
# Non-observation commands do NOT set observed_page
# ---------------------------------------------------------------------------


def test_open_alone_does_not_set_observed():
    """'bp open' is navigation, not observation. An agent that only
    navigates and then answers from the initial snapshot (fed by the
    solver's auto-open) is lazy."""
    ss = _run_with_agent_responses(
        [
            "bp open https://example.com/other",
            "ANSWER: The site is about examples",
        ]
    )
    assert ss.observed_page is False
    assert ss.agent_answer == "The site is about examples"


def test_click_alone_does_not_set_observed():
    """'bp click 5' is interaction, not observation."""
    ss = _run_with_agent_responses(
        [
            "bp click 5",
            "ANSWER: I clicked the button",
        ]
    )
    assert ss.observed_page is False


def test_type_alone_does_not_set_observed():
    """'bp type 3 hello' is input, not observation."""
    ss = _run_with_agent_responses(
        [
            'bp type 3 "hello world"',
            "ANSWER: I typed hello",
        ]
    )
    assert ss.observed_page is False


# ---------------------------------------------------------------------------
# Mixed commands: observation + non-observation
# ---------------------------------------------------------------------------


def test_observation_after_navigation_sets_observed():
    """Agent navigates then reads — observed_page must be True
    because the read command ran."""
    ss = _run_with_agent_responses(
        [
            "bp open https://example.com/page\nbp read",
            "ANSWER: The page content is X",
        ]
    )
    assert ss.observed_page is True


def test_observation_before_answer_in_same_turn():
    """Agent reads and answers in the same turn — per the M1.1
    ordering fix, commands run FIRST and the ANSWER is DISCARDED
    (the agent gets real tool output and revises next turn). The
    key property: observed_page must be True because the read
    command ran, even though the answer was based on hallucinated
    output."""
    ss = _run_with_agent_responses(
        [
            "bp read\nANSWER: The content is Y",
            # Solver discards the answer above, feeds tool output back.
            # MockModel's fallback returns "ANSWER: done" on the next turn.
        ]
    )
    assert ss.observed_page is True
    # The agent_answer is "done" (from the fallback), NOT "The content
    # is Y" — that answer was correctly discarded by the M1.1 fix.
    assert ss.agent_answer == "done"


# ---------------------------------------------------------------------------
# Agent never emits any commands → not observed
# ---------------------------------------------------------------------------


def test_immediate_answer_is_not_observed():
    """Agent answers on the first turn with no commands.
    This is the pure lazy pattern."""
    ss = _run_with_agent_responses(
        [
            "ANSWER: I know this from training data",
        ]
    )
    assert ss.observed_page is False
    assert ss.agent_answer == "I know this from training data"


def test_no_answer_no_commands_is_not_observed():
    """Agent produces text with no commands and no answer for
    multiple turns, then the loop nudges and it answers.
    Still not observed because no observation command ran."""
    ss = _run_with_agent_responses(
        [
            "I'm thinking about this...",
            "Let me consider the options...",
            "ANSWER: I think the answer is 42",
        ]
    )
    assert ss.observed_page is False


# ---------------------------------------------------------------------------
# Commands run count
# ---------------------------------------------------------------------------


def test_commands_run_tracks_total():
    """commands_run should count every bp command that ran."""
    ss = _run_with_agent_responses(
        [
            "bp open https://example.com\nbp read\nbp click 1",
            "bp snapshot",
            "ANSWER: done",
        ]
    )
    assert ss.commands_run == 4  # open + read + click + snapshot
    assert ss.observed_page is True  # read + snapshot are observation
