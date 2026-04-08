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
            (``disconnect`` + ``connect``). Pass ``[]`` to disable
            the reset entirely — only do that if you're sure sample
            independence isn't required (e.g. single-sample smoke
            tests). Pass a custom list to substitute your own
            sequence (e.g. ``[["bp", "close", "--all"]]``) for
            experimentation.
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
