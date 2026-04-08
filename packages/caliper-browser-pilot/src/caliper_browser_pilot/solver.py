"""bp_agent() — the canonical browser-pilot solver factory.

A thin wrapper over ``caliper.solvers.text_protocol_agent`` that bakes in:

- ``cli_name="bp"``
- ``observation_commands=BP_OBSERVATION_COMMANDS``
- ``output_formatter=bp_truncate_snapshot``
- ``system_prompt_file=bp_skill_path()`` (auto-resolved)

Consumers in this package's ``tasks/`` and in ``examples/cambridge_smoke.py``
should use this factory rather than calling the generic
``text_protocol_agent`` directly. That keeps "bp-ness" in one place.
"""

from __future__ import annotations

from inspect_ai.solver import Solver

from caliper.solvers import text_protocol_agent

from caliper_browser_pilot.tools import (
    BP_OBSERVATION_COMMANDS,
    bp_skill_path,
    bp_truncate_snapshot,
)


# Default prologue for bp_agent: reset bp's cross-sample state before
# every sample. bp attaches to the user's real Chrome via CDP and
# persists ``activeTargetId`` in ``~/.browser-pilot/state.json``, so
# sample N's tab state leaks into sample N+1 unless we tear down and
# reconnect. ``bp disconnect`` kills the daemon + clears the state
# file; ``bp connect`` starts a fresh daemon with a new pilot tab.
#
# This guards against the M1.6 CHROME_TAB_POLLUTION failure class
# (Huggingface--3 explicitly logged "tab mismatch"; Apple--0 ep 2 and
# Allrecipes--0 showed cross-sample content bleed). See
# ``docs/lessons-learned.md`` M1.6 section and the M1.6b roadmap entry.
#
# **IMPORTANT — parallelism**: bp is a *process-global singleton* that
# attaches to the user's real Chrome via CDP. It is NOT safe to run
# under parallel Inspect AI samples (``--max-samples > 1``): two
# workers racing to ``bp disconnect`` / ``bp connect`` would tear
# down each other's daemon mid-call. This default is for **serial
# evals only** (``inspect eval --max-samples 1``). If you need to
# run bp under a parallel scheduler, pass
# ``bp_agent(session_prologue=[])`` to disable the reset — but note
# that without the reset you are back to the M1.6 tab-pollution
# failure mode. There is no current parallel-safe bp story; that
# would require bp itself to support per-sample ephemeral profiles,
# which it does not (as of bp 0.1.6).
BP_DEFAULT_SESSION_PROLOGUE: list[list[str]] = [
    ["bp", "disconnect"],
    ["bp", "connect"],
]


def bp_agent(
    max_turns: int = 12,
    system_prompt_file: str | None = None,
    cli_timeout: float = 60.0,
    session_prologue: list[list[str]] | None = None,
) -> Solver:
    """Build a bp-flavoured text-protocol agent.

    Args:
        max_turns: Maximum LLM turns before forcing termination. v8
            baseline used 12 — keep that as the default.
        system_prompt_file: Override for SKILL.md path. If ``None``,
            ``caliper_browser_pilot.tools.bp_skill_path()`` resolves it.
        cli_timeout: Per-command subprocess timeout in seconds.
        session_prologue: Override for the per-sample bp reset
            sequence. Defaults to ``BP_DEFAULT_SESSION_PROLOGUE``
            (``disconnect`` + ``connect``).

            Pass ``[]`` to disable the reset entirely. This is the
            only safe choice when running under a parallel Inspect
            AI scheduler (``--max-samples > 1``) — see the
            ``BP_DEFAULT_SESSION_PROLOGUE`` module comment for why
            bp is not parallel-safe. It is also reasonable for
            single-sample smoke tests where hermetic per-sample
            state isn't required.

            Pass a custom list to substitute your own sequence
            (e.g. ``[["bp", "close", "--all"]]``) for
            experimentation, keeping in mind that
            ``text_protocol_agent`` enforces "last command must
            succeed" semantics — the final argv in the list is the
            one whose failure aborts the sample.
    """
    skill_path = system_prompt_file
    if skill_path is None:
        resolved = bp_skill_path()
        if resolved is not None:
            skill_path = str(resolved)

    prologue = (
        session_prologue
        if session_prologue is not None
        else BP_DEFAULT_SESSION_PROLOGUE
    )

    return text_protocol_agent(
        cli_name="bp",
        observation_commands=BP_OBSERVATION_COMMANDS,
        max_turns=max_turns,
        system_prompt_file=skill_path,
        cli_timeout=cli_timeout,
        output_formatter=bp_truncate_snapshot,
        session_prologue=prologue,
    )
