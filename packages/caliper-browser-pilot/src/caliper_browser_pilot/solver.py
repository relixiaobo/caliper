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


def bp_agent(
    max_turns: int = 12,
    system_prompt_file: str | None = None,
    cli_timeout: float = 60.0,
) -> Solver:
    """Build a bp-flavoured text-protocol agent.

    Args:
        max_turns: Maximum LLM turns before forcing termination. v8
            baseline used 12 — keep that as the default.
        system_prompt_file: Override for SKILL.md path. If ``None``,
            ``caliper_browser_pilot.tools.bp_skill_path()`` resolves it.
        cli_timeout: Per-command subprocess timeout in seconds.
    """
    skill_path = system_prompt_file
    if skill_path is None:
        resolved = bp_skill_path()
        if resolved is not None:
            skill_path = str(resolved)

    return text_protocol_agent(
        cli_name="bp",
        observation_commands=BP_OBSERVATION_COMMANDS,
        max_turns=max_turns,
        system_prompt_file=skill_path,
        cli_timeout=cli_timeout,
        output_formatter=bp_truncate_snapshot,
    )
