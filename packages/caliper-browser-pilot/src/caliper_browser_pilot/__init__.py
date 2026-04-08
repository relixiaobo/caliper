"""caliper-browser-pilot — caliper adapter for the bp CLI.

The bp-specific bits that don't belong in caliper core: the observation
command set, the snapshot text formatter (which knows bp's JSON shape),
the SKILL.md path resolver, and a ``bp_agent()`` factory.

Public API:
    bp_agent              — solver factory with bp defaults baked in
    BP_OBSERVATION_COMMANDS — set of bp sub-commands that count as observation
    bp_truncate_snapshot   — bp-specific JSON snapshot → compact text
    bp_skill_path          — locate the SKILL.md system prompt file
"""

from caliper_browser_pilot.solver import bp_agent
from caliper_browser_pilot.tools import (
    BP_OBSERVATION_COMMANDS,
    bp_skill_path,
    bp_truncate_snapshot,
)

__all__ = [
    "bp_agent",
    "BP_OBSERVATION_COMMANDS",
    "bp_skill_path",
    "bp_truncate_snapshot",
]
