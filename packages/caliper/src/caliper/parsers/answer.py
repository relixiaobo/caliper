"""Extract the agent's final ``ANSWER:`` block from LLM free text.

The agent indicates termination by writing a line beginning with
``ANSWER:``. The block can be on a single line or span multiple lines
until a terminator (``DONE`` / ``FAIL``) or a 3-blank-line gap.

Verbatim port from ``docs/reference/inherited-artifacts.md`` §5. Went
through 3 iterations during browser-pilot v3-v6; do not "improve" without
re-running the self-evaluation suite.
"""

from __future__ import annotations


def extract_answer(text: str) -> str | None:
    """Extract the agent's ``ANSWER:`` block.

    Returns the answer text (joined to a single line, capped at 2000
    chars), or ``None`` if no ``ANSWER:`` line is found.
    """
    lines = text.split("\n")
    answer_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("ANSWER:"):
            answer_idx = i
            break
    if answer_idx is None:
        return None

    parts: list[str] = []
    first_rest = lines[answer_idx].strip()[7:].strip()
    if first_rest:
        parts.append(first_rest)

    blank_run = 0
    for j in range(answer_idx + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped in ("DONE", "FAIL"):
            break
        if stripped.startswith("```"):
            continue
        if not stripped:
            blank_run += 1
            if blank_run >= 3 and parts:
                break
            continue
        blank_run = 0
        parts.append(stripped)

    if not parts:
        return None
    answer = " ".join(parts)
    if len(answer) > 2000:
        answer = answer[:2000]
    return answer
