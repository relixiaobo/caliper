"""Regression tests for ``text_protocol_agent(session_prologue=...)``.

This is the M1.6b fix for the CHROME_TAB_POLLUTION failure class: bp
(and potentially any other CLI tool caliper wraps) can hold
persistent state between samples. The solver now accepts a
``session_prologue`` argv list that runs at the start of *every*
sample, before the ``start_url`` opening snapshot.

These tests pin three contract properties of that mechanism:

1. The prologue runs exactly once per sample, before ``bp open``
   (or whatever the adapter's initial snapshot command is).
2. The prologue runs *in order*.
3. When no prologue is passed, the behaviour is exactly what it was
   pre-M1.6b — no extra calls, no regressions against existing tasks.

Do NOT delete these tests without a migration note. They are the
operational form of the M1.6b post-mortem: if someone silently
removes the prologue, Huggingface/Allrecipes/Apple-style failures
will silently come back.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import TaskState

from caliper.solvers.text_protocol import text_protocol_agent


def _make_state(start_url: str | None = "https://example.com/") -> TaskState:
    """Build a minimal TaskState for solver invocation."""
    metadata: dict[str, object] = {}
    if start_url:
        metadata["start_url"] = start_url
    return TaskState(
        model="test/test",
        sample_id="t1",
        epoch=1,
        input=[ChatMessageUser(content="dummy task")],
        messages=[],
        metadata=metadata,
    )


def _run_solver_once(solver_fn, *, answer: str = "ANSWER: done"):
    """Drive one sample through the solver with a mocked model that
    immediately returns ``answer``, and with ``run_cli`` patched to
    record argvs without actually running subprocesses.

    Returns the list of recorded argvs in call order.
    """
    calls: list[list[str]] = []

    async def fake_run_cli(argv, timeout=60.0):
        calls.append(list(argv))
        return ""

    mock_model = type(
        "MockModel",
        (),
        {"generate": AsyncMock(return_value=type("R", (), {"completion": answer})())},
    )()

    state = _make_state()

    async def _drive():
        with (
            patch("caliper.solvers.text_protocol.run_cli", side_effect=fake_run_cli),
            patch("caliper.solvers.text_protocol.get_model", return_value=mock_model),
        ):
            await solver_fn(state, None)  # type: ignore[arg-type]

    asyncio.run(_drive())
    return calls


# ---------------------------------------------------------------------------
# Happy path: prologue runs before start_url open
# ---------------------------------------------------------------------------


def test_prologue_runs_before_start_url_open():
    """The M1.6b contract: every argv in session_prologue executes
    *before* the start_url open, in the order provided."""
    solver_fn = text_protocol_agent(
        cli_name="tt",
        observation_commands=["read"],
        system_prompt="test",
        session_prologue=[
            ["tt", "disconnect"],
            ["tt", "connect"],
        ],
    )

    calls = _run_solver_once(solver_fn)

    # First two calls must be the prologue, in order.
    assert calls[0] == ["tt", "disconnect"]
    assert calls[1] == ["tt", "connect"]
    # Third call is the start_url open.
    assert calls[2] == ["tt", "open", "https://example.com/"]


def test_prologue_runs_every_sample_not_just_once():
    """Each new invocation of the solver (which is how Inspect AI
    models one sample) must re-run the prologue. Otherwise sample N+1
    inherits sample N's CLI state — the very bug M1.6b is fixing."""
    solver_fn = text_protocol_agent(
        cli_name="tt",
        observation_commands=["read"],
        system_prompt="test",
        session_prologue=[["tt", "reset"]],
    )

    calls_a = _run_solver_once(solver_fn)
    calls_b = _run_solver_once(solver_fn)

    # Both invocations should have reset as their first call.
    assert calls_a[0] == ["tt", "reset"]
    assert calls_b[0] == ["tt", "reset"]


# ---------------------------------------------------------------------------
# Regression guards: no prologue = no extra calls
# ---------------------------------------------------------------------------


def test_no_prologue_means_no_extra_calls():
    """When ``session_prologue`` is not passed, the call sequence is
    exactly what it was before M1.6b: just the ``open start_url``
    followed by whatever the agent emits. This guards against
    accidentally adding prologue side-effects to solvers that don't
    need them (e.g. existing smoke tests)."""
    solver_fn = text_protocol_agent(
        cli_name="tt",
        observation_commands=["read"],
        system_prompt="test",
    )

    calls = _run_solver_once(solver_fn)

    # Only call should be the start_url open.
    assert calls == [["tt", "open", "https://example.com/"]]


def test_empty_prologue_is_equivalent_to_none():
    """Passing ``session_prologue=[]`` must behave identically to
    ``session_prologue=None`` — no calls, no crashes. This is the
    escape hatch adapters can use to disable the prologue for
    specific tests (e.g. single-sample smoke runs)."""
    solver_fn = text_protocol_agent(
        cli_name="tt",
        observation_commands=["read"],
        system_prompt="test",
        session_prologue=[],
    )

    calls = _run_solver_once(solver_fn)
    assert calls == [["tt", "open", "https://example.com/"]]


def test_prologue_list_is_copied_not_shared():
    """The solver must copy the caller's prologue list at build time
    rather than holding a reference. Otherwise a caller mutating the
    list after solver construction would silently change behaviour —
    the kind of shared-mutable-state bug that's easy to write and
    hard to debug."""
    shared: list[list[str]] = [["tt", "disconnect"], ["tt", "connect"]]
    solver_fn = text_protocol_agent(
        cli_name="tt",
        observation_commands=["read"],
        system_prompt="test",
        session_prologue=shared,
    )

    # Mutate the caller's list AFTER building the solver.
    shared.clear()
    shared.append(["tt", "pwned"])

    calls = _run_solver_once(solver_fn)

    # Solver should still run the ORIGINAL prologue, not the mutated one.
    assert calls[0] == ["tt", "disconnect"]
    assert calls[1] == ["tt", "connect"]
    assert ["tt", "pwned"] not in calls
