"""Tests for caliper.scoring — pure scoring functions.

These test the Inspect-AI-independent scoring kernel:
- score_lazy: pure boolean logic, no I/O
- score_judge: mocked LLM call, tests prompt construction + verdict parsing
- score_verify: mocked run_cli, tests spec execution + pre-computed results
- taskstate_to_record: conversion from Inspect AI TaskState to CaliperRecord

The existing tests in test_json_verdict_parser.py cover the verdict
parser exhaustively. These tests cover the pure function wrappers and
the CaliperRecord data contract.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from caliper.record import CaliperRecord, JudgeResult, VerifyResult
from caliper.scoring import score_lazy, score_judge, score_verify, taskstate_to_record


# ---------------------------------------------------------------------------
# score_lazy (pure, no mocking needed)
# ---------------------------------------------------------------------------


def test_lazy_true_when_answer_without_observation():
    assert score_lazy("some answer", observed=False) is True


def test_lazy_false_when_answer_with_observation():
    assert score_lazy("some answer", observed=True) is False


def test_lazy_false_when_no_answer():
    """No answer = agent didn't finish. Not lazy, just broken."""
    assert score_lazy("", observed=False) is False
    assert score_lazy("", observed=True) is False


# ---------------------------------------------------------------------------
# score_judge (mocked LLM)
# ---------------------------------------------------------------------------


def _mock_judge_response(verdict: str, reason: str = "") -> MagicMock:
    """Build a mock model that returns a judge verdict."""
    response = MagicMock()
    if reason:
        response.completion = f'{{"verdict": "{verdict}", "reason": "{reason}"}}'
    else:
        response.completion = f'{{"verdict": "{verdict}"}}'

    model = MagicMock()
    model.generate = AsyncMock(return_value=response)
    return model


def test_judge_correct_verdict():
    model = _mock_judge_response("correct")
    with patch("inspect_ai.model.get_model", return_value=model):
        result = asyncio.run(
            score_judge(
                goal="Find X",
                agent_answer="X is 42",
                reference_answer="42",
            )
        )
    assert isinstance(result, JudgeResult)
    assert result.passed is True
    assert "correct" in result.reason


def test_judge_incorrect_verdict():
    model = _mock_judge_response("incorrect", "wrong number")
    with patch("inspect_ai.model.get_model", return_value=model):
        result = asyncio.run(
            score_judge(
                goal="Find X",
                agent_answer="X is 99",
                reference_answer="42",
            )
        )
    assert result.passed is False
    assert "wrong number" in result.reason


def test_judge_empty_answer_skips_llm():
    """Empty agent_answer should return False without calling the LLM."""
    result = asyncio.run(
        score_judge(
            goal="Find X",
            agent_answer="",
            reference_answer="42",
        )
    )
    assert result.passed is False
    assert "empty agent answer" in result.reason


def test_judge_empty_reference_raises():
    """score_judge requires a reference answer — otherwise use score_lazy."""
    import pytest

    with pytest.raises(ValueError, match="reference_answer"):
        asyncio.run(
            score_judge(
                goal="Find X",
                agent_answer="X is 42",
                reference_answer="",
            )
        )


def test_judge_custom_prompt():
    """Projects can pass a custom judge prompt template."""
    model = _mock_judge_response("correct")
    with patch("inspect_ai.model.get_model", return_value=model):
        result = asyncio.run(
            score_judge(
                goal="Find X",
                agent_answer="42",
                reference_answer="42",
                judge_prompt="Is '{agent_answer}' correct for '{goal}' (ref: {reference_answer})? {{\"verdict\": \"correct\"}}",
            )
        )
    assert result.passed is True
    # Verify the custom prompt was used (not the default).
    call_args = model.generate.call_args[0][0]
    # The user message should contain our custom prompt text.
    user_msg = call_args[1].content
    assert "Is '42' correct for 'Find X'" in user_msg


def test_judge_raw_response_captured():
    model = _mock_judge_response("correct", "looks right")
    with patch("inspect_ai.model.get_model", return_value=model):
        result = asyncio.run(
            score_judge(
                goal="g",
                agent_answer="a",
                reference_answer="r",
            )
        )
    assert result.raw_response  # non-empty


# ---------------------------------------------------------------------------
# score_verify (mocked run_cli for spec mode, pure for pre-computed mode)
# ---------------------------------------------------------------------------


def test_verify_precomputed_all_pass():
    """Pre-computed results: project already ran verification."""
    result = asyncio.run(
        score_verify(
            verify_results=[
                {"passed": True, "description": "check A"},
                {"passed": True, "description": "check B"},
            ],
        )
    )
    assert isinstance(result, VerifyResult)
    assert result.passed is True
    assert result.n_specs == 2
    assert not result.failures


def test_verify_precomputed_with_failure():
    result = asyncio.run(
        score_verify(
            verify_results=[
                {"passed": True, "description": "check A"},
                {"passed": False, "description": "check B"},
            ],
        )
    )
    assert result.passed is False
    assert "check B" in result.failures[0]


def test_verify_no_specs_passes():
    """No verification requested → vacuous pass."""
    result = asyncio.run(score_verify())
    assert result.passed is True
    assert result.n_specs == 0


def test_verify_specs_with_mocked_run_cli():
    """Spec mode: caliper runs the commands via run_cli."""

    async def fake_run_cli(argv, timeout=30.0):
        if "count" in argv:
            return "2\n"
        return ""

    with patch("caliper.runtime.run_cli", side_effect=fake_run_cli):
        result = asyncio.run(
            score_verify(
                verify_specs=[
                    {
                        "command": ["bp", "eval", "count"],
                        "expect_contains": "2",
                        "description": "both checked",
                    }
                ],
            )
        )
    assert result.passed is True
    assert result.n_specs == 1


def test_verify_specs_failure():
    async def fake_run_cli(argv, timeout=30.0):
        return "1\n"  # wrong output

    with patch("caliper.runtime.run_cli", side_effect=fake_run_cli):
        result = asyncio.run(
            score_verify(
                verify_specs=[
                    {
                        "command": ["bp", "eval", "count"],
                        "expect_contains": "2",
                        "description": "both checked",
                    }
                ],
            )
        )
    assert result.passed is False
    assert "both checked" in result.failures[0]


def test_verify_precomputed_takes_precedence_over_specs():
    """If both verify_results AND verify_specs are provided, results win."""
    result = asyncio.run(
        score_verify(
            verify_specs=[
                {
                    "command": ["bp", "eval", "should-not-run"],
                    "expect_contains": "x",
                }
            ],
            verify_results=[{"passed": True, "description": "pre-computed"}],
        )
    )
    assert result.passed is True
    assert result.n_specs == 1


# ---------------------------------------------------------------------------
# CaliperRecord construction
# ---------------------------------------------------------------------------


def test_caliper_record_required_fields():
    """CaliperRecord's required fields must be provided."""
    r = CaliperRecord(
        sample_id="t1",
        bucket="smoke",
        goal="do something",
        agent_answer="done",
        observed=True,
    )
    assert r.sample_id == "t1"
    assert r.bucket == "smoke"
    assert r.agent_answer == "done"
    assert r.observed is True
    # Optional fields have defaults
    assert r.reference_answer == ""
    assert r.input_tokens == 0
    assert r.has_cache_info is False
    assert r.epoch == 1


def test_caliper_record_with_all_fields():
    r = CaliperRecord(
        sample_id="t1",
        bucket="lookup",
        goal="find X",
        agent_answer="X is 42",
        observed=True,
        reference_answer="42",
        verify_specs=[{"command": ["bp", "eval", "x"], "expect_contains": "42"}],
        input_tokens=50000,
        output_tokens=3000,
        cache_read_tokens=10000,
        has_cache_info=True,
        commands_run=5,
        epoch=2,
        metadata={"source": "my-benchmark"},
    )
    assert r.reference_answer == "42"
    assert r.input_tokens == 50000
    assert r.has_cache_info is True
    assert r.epoch == 2


# ---------------------------------------------------------------------------
# taskstate_to_record (Inspect AI bridge)
# ---------------------------------------------------------------------------


def test_taskstate_to_record():
    """The converter should extract the right fields from TaskState."""
    from inspect_ai.model import ChatMessageUser
    from inspect_ai.solver import TaskState
    from caliper.protocols import SolverState

    state = TaskState(
        model="test/test",
        sample_id="apple-0",
        epoch=2,
        input=[ChatMessageUser(content="Compare MacBook Air prices")],
        messages=[],
        metadata={
            "bucket": "compare",
            "source": "apple.com",
            "start_url": "https://apple.com/",
            "verify": [{"command": ["bp", "eval", "x"], "expect_contains": "y"}],
        },
    )
    ss = state.store_as(SolverState)
    ss.agent_answer = "13-inch $1099, 15-inch $1299"
    ss.observed_page = True
    ss.commands_run = 5

    target = MagicMock()
    target.text = "MacBook Air M2 from $1099"

    record = taskstate_to_record(state, target)

    assert isinstance(record, CaliperRecord)
    assert record.sample_id == "apple-0"
    assert record.bucket == "compare"
    assert record.goal == "Compare MacBook Air prices"
    assert record.agent_answer == "13-inch $1099, 15-inch $1299"
    assert record.observed is True
    assert record.reference_answer == "MacBook Air M2 from $1099"
    assert record.commands_run == 5
    assert record.epoch == 2
    assert record.verify_specs is not None
    assert len(record.verify_specs) == 1
