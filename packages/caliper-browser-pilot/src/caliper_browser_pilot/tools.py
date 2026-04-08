"""bp-specific configuration and helpers.

Three things live here:

1. ``BP_OBSERVATION_COMMANDS`` — the set of bp sub-commands that count
   as "observing the page" for lazy detection. This is bp-specific
   knowledge: ``read``/``snapshot``/``eval``/``screenshot``/``tabs``/
   ``cookies``/``locate`` are the commands that return data the agent
   can reason about. Other bp sub-commands (``open``/``click``/``type``)
   are navigation or actions, not observation.

2. ``bp_truncate_snapshot`` — bp's snapshot output is a specific JSON
   shape ``{"elements": [...], "title": ..., "url": ...}``. The compact
   text formatter (``[ref] role "name"`` per element) is bp-specific
   and lives here, NOT in caliper core. caliper core's solver takes a
   generic ``output_formatter`` callable; this function is what
   ``bp_agent()`` passes in.

3. ``bp_skill_path`` — locate browser-pilot's SKILL.md (the agent's
   system prompt). Honors the ``CALIPER_BP_SKILL_PATH`` env var first,
   then falls back to a few well-known locations relative to
   ``$HOME/Documents/Coding/browser-pilot``. This replaces the
   hardcoded path that the M1.1 cambridge_smoke originally had.

See ``docs/reference/inherited-artifacts.md`` §3 (observation commands)
and §6 (truncate_snapshot) for the verbatim sources.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Observation command set
# ---------------------------------------------------------------------------

BP_OBSERVATION_COMMANDS = frozenset(
    {
        "read",       # bp read       — page text content
        "snapshot",   # bp snapshot   — interactive elements list
        "eval",       # bp eval       — JS execution result
        "screenshot", # bp screenshot — visual state
        "tabs",       # bp tabs       — open tab list
        "cookies",    # bp cookies    — cookie state
        "locate",     # bp locate     — element search
    }
)


# ---------------------------------------------------------------------------
# Snapshot output formatter (bp-specific JSON shape)
# ---------------------------------------------------------------------------

def bp_truncate_snapshot(output: str, max_elements: int = 30) -> str:
    """Reformat a bp snapshot/read JSON output into compact text.

    Verbatim port from inherited-artifacts.md §6. Compresses verbose JSON
    elements into ``[ref] role "name"`` lines (~60% smaller per element).
    Caps non-snapshot output at 3000 chars. Cuts total token cost
    meaningfully because snapshots persist in conversation history for
    every subsequent turn.

    Falls through to a 3000-char cap for any output that isn't recognised
    bp JSON (errors, eval results, etc.).
    """
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return output[:3000]
    if not isinstance(data, dict):
        return output[:3000]

    # bp read result — keep title/url/text but cap text length
    if "text" in data and "elements" not in data:
        text = data.get("text", "")
        if len(text) > 3000:
            text = text[:3000] + "... [truncated]"
        return f'page: {data.get("title", "")}\nurl: {data.get("url", "")}\n---\n{text}'

    # bp snapshot result
    if "elements" in data:
        elements = data["elements"]
        total = len(elements)
        shown = elements[:max_elements]
        out_lines: list[str] = []
        title = data.get("title", "")
        url = data.get("url", "")
        if title or url:
            out_lines.append(f"page: {title} | {url}")
        for el in shown:
            ref = el.get("ref")
            role = el.get("role", "")
            name = el.get("name", "")
            line = f'[{ref}] {role} "{name}"'
            if "value" in el and el["value"]:
                line += f' value="{el["value"]}"'
            if el.get("checked"):
                line += " checked"
            out_lines.append(line)
        if total > max_elements:
            out_lines.append(f"... ({total - max_elements} more elements)")
        return "\n".join(out_lines)

    return output[:3000]


# ---------------------------------------------------------------------------
# SKILL.md location resolver
# ---------------------------------------------------------------------------

_SKILL_ENV_VAR = "CALIPER_BP_SKILL_PATH"

# Common locations to try when the env var isn't set, in priority order.
# These are search hints, not hardcoded production paths — anyone running
# caliper-browser-pilot on a machine where bp lives somewhere unusual
# should set CALIPER_BP_SKILL_PATH explicitly.
_SKILL_SEARCH_HINTS = (
    "browser-pilot/plugin/skills/browser-pilot/SKILL.md",
    "../browser-pilot/plugin/skills/browser-pilot/SKILL.md",
    "../../browser-pilot/plugin/skills/browser-pilot/SKILL.md",
)


def bp_skill_path() -> Path | None:
    """Locate browser-pilot's SKILL.md system prompt file.

    Resolution order:
    1. ``$CALIPER_BP_SKILL_PATH`` if set and the file exists
    2. Walk up from cwd looking for any of the search hints
    3. ``$HOME/Documents/Coding/browser-pilot/plugin/skills/browser-pilot/SKILL.md``
       (the canonical dev-machine layout from docs/context.md)
    4. Return ``None`` — caller falls back to a generic prompt

    Returns the resolved Path or None. Never raises.
    """
    env_value = os.environ.get(_SKILL_ENV_VAR)
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.exists():
            return candidate

    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        for hint in _SKILL_SEARCH_HINTS:
            candidate = parent / hint
            if candidate.exists():
                return candidate.resolve()

    home = Path.home() / "Documents/Coding/browser-pilot/plugin/skills/browser-pilot/SKILL.md"
    if home.exists():
        return home

    return None
