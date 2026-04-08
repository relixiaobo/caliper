"""JSON-only judge verdict parser.

This is the single most load-bearing line of code in caliper. It is
the only way a judge result becomes a PASS, and the only kind of
response it will accept is a parseable JSON object whose ``verdict``
field is exactly ``"correct"`` or ``"incorrect"`` (case-insensitive,
whitespace-trimmed).

**There is no natural-language fallback.** Any response that doesn't
produce a recognised JSON verdict — including bare prose like
``"CORRECT"`` — is treated as a format violation and returns
``False`` with an explicit reason.

## Why no fallback

An earlier version of this parser fell back to substring matching
("INCORRECT first, then CORRECT") for responses that didn't contain
JSON. That fallback appeared to be safe because it checked INCORRECT
before CORRECT, avoiding the original v0-v4 substring trap. Codex's
Phase R review proved the fallback was still unsafe, because common
negation phrasings look like this:

- ``"not correct"``              → contains CORRECT, not INCORRECT → PASS (WRONG)
- ``"this is not CORRECT"``      → same → PASS (WRONG)
- ``{"verdict": "not correct"}`` → JSON parses but value is unknown,
  falls through to fallback → PASS (WRONG)

Patching the fallback to handle ``"not correct"`` is whack-a-mole —
every negation phrasing (``"isn't correct"``, ``"couldn't be called
correct"``, ``"not entirely correct"``, ``"far from correct"``...)
would need its own rule. The root fix is to not do substring matching
on natural language at all.

Safety bias: fail-closed. methodology.md principle 1 demands that
inflation of pass rate never happen silently. Deflation (marking a
legitimately-correct prose response as format_violation) is visible
in logs and triggers investigation. Inflation is catastrophic because
it produces false confidence in phantom improvements — the entire
v0-v4 story.

## Consequences

- A judge model that emits JSON reliably works fine. Sonnet / Opus /
  GPT-5 at ``temperature=0`` with the caliper JUDGE_SYSTEM_PROMPT all
  do this reliably.
- A judge model that emits prose instead of JSON will produce a
  systematic "format violation" stream visible in the explanation
  field of every Score. The right response is to fix the prompt or
  switch models, not to soften the parser.

See ``docs/reference/inherited-artifacts.md`` §2 for the historical
context, and ``packages/caliper/tests/unit/test_json_verdict_parser.py``
for the full behavioural contract.
"""

from __future__ import annotations

import json
import re

_UNPARSEABLE_REASON = "judge_format_violation: no valid JSON verdict found"


def parse_judge_verdict(response: str) -> tuple[bool, str]:
    """Parse ``{"verdict": "correct|incorrect", "reason": "..."}`` from
    a judge response.

    Returns ``(passed, reason)``.

    A response produces ``passed=True`` if and only if the response
    contains a balanced JSON object whose ``verdict`` field, when
    lowercased and trimmed, is exactly ``"correct"``. Any other shape
    (unparseable JSON, missing verdict field, unrecognised verdict
    value, prose without JSON, empty string) produces ``passed=False``
    with an explicit format-violation reason.
    """
    text = response.strip()

    # Strip markdown code fences so the first { is reachable.
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Find the first balanced {...} and try to parse it as JSON.
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    verdict = str(obj.get("verdict", "")).lower().strip()
                    reason = str(obj.get("reason", "")).strip()
                    if verdict == "correct":
                        return True, reason or "correct"
                    if verdict == "incorrect":
                        return False, reason or "incorrect"
                    # JSON parsed, but verdict was missing or unknown —
                    # fall through to the format-violation path below.
                    break

    # No recognised JSON verdict. Fail closed.
    snippet = response[:60].replace("\n", " ")
    return False, f"{_UNPARSEABLE_REASON}: {snippet!r}"
