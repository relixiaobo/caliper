"""Unit tests for the judge verdict parser.

This file is the single most load-bearing test file in caliper. The
parser it tests is on the critical path for every judge verdict, and
the history of browser-pilot v0–v4 shows what happens when this code
is wrong: a parser that checked ``"CORRECT" in response`` silently
flipped 38% of INCORRECT verdicts to CORRECT, inflating all the
historical numbers.

Phase R + Codex P2 tightening: the earlier "keyword fallback" path
has been **removed entirely**. The fallback existed to handle judges
that ignored the JSON format and wrote prose like ``CORRECT``, but it
was unsafe against natural-language negation:

- ``"not correct"``              → old fallback returned True (WRONG)
- ``"this is not CORRECT"``      → old fallback returned True (WRONG)
- ``{"verdict": "not correct"}`` → old fallback returned True (WRONG)

Patching the fallback to recognise ``"NOT CORRECT"`` is a whack-a-mole
approach — every negation phrasing (``"isn't correct"``,
``"couldn't be called correct"``, ``"not entirely correct"``...) would
need its own rule. The root fix is to **not do substring matching on
natural language at all**. Any judge response that doesn't contain a
parseable JSON object with ``verdict ∈ {correct, incorrect}`` is
treated as a format violation and returns ``False`` with an explicit
reason.

Safety bias: fail-closed. methodology.md principle 1 ("measurement
comes before optimization") demands that inflation of pass rate never
happen silently. Deflation is acceptable because it's visible — a low
pass rate prompts investigation. Inflation is catastrophic because it
produces false confidence in phantom improvements.

If your judge model ever emits prose instead of JSON, the right fix
is to improve the prompt or switch models, not to soften the parser.
"""

from caliper.scorers.json_verdict import parse_judge_verdict


# ---------------------------------------------------------------------------
# JSON path — the only path that can return True.
# ---------------------------------------------------------------------------


def test_json_correct():
    verdict, _ = parse_judge_verdict('{"verdict":"correct"}')
    assert verdict is True


def test_json_incorrect():
    verdict, _ = parse_judge_verdict('{"verdict":"incorrect","reason":"empty"}')
    assert verdict is False


def test_json_with_markdown_fences():
    verdict, _ = parse_judge_verdict('```json\n{"verdict":"correct"}\n```')
    assert verdict is True


def test_json_with_surrounding_prose():
    verdict, _ = parse_judge_verdict(
        'Here is my verdict: {"verdict":"correct","reason":"matches"} done.'
    )
    assert verdict is True


def test_json_uppercase_verdict_is_normalized():
    verdict, _ = parse_judge_verdict('{"verdict":"CORRECT"}')
    assert verdict is True


# ---------------------------------------------------------------------------
# Substring-bug family regression tests. All of these must return False.
# ---------------------------------------------------------------------------


def test_keyword_incorrect_fallback_NOT_substring_bug():
    """The original v0-v4 regression.

    A parser that checks ``"CORRECT" in response`` returns True for
    ``"INCORRECT"``. This test has been part of caliper since M1.1
    and its name must never change — it is the historical marker for
    the class of bugs.
    """
    verdict, _ = parse_judge_verdict("INCORRECT")
    assert verdict is False, (
        "INCORRECT must NOT be parsed as correct (substring trap)"
    )


def test_keyword_incorrect_in_sentence():
    verdict, _ = parse_judge_verdict("This answer is INCORRECT because of X.")
    assert verdict is False


def test_bare_CORRECT_prose_is_format_violation():
    """Post-Phase-R tightening: CORRECT prose alone is a format
    violation, not a pass. See the module docstring for why we
    removed the prose fallback."""
    verdict, reason = parse_judge_verdict("CORRECT")
    assert verdict is False
    assert "json" in reason.lower() or "parse" in reason.lower() or "unparseable" in reason.lower()


def test_negation_not_correct_is_NOT_a_pass_REGRESSION():
    """REGRESSION TEST for the Codex Phase R P2 finding.

    An earlier keyword-fallback parser checked ``"INCORRECT" in upper``
    then ``"CORRECT" in upper``. The judge response ``"not correct"``
    contains CORRECT but not INCORRECT, so it was classified as a
    PASS. Same bug family as v0-v4.
    """
    verdict, _ = parse_judge_verdict("not correct")
    assert verdict is False, "'not correct' must NOT be parsed as a pass"


def test_negation_mid_sentence_is_NOT_a_pass():
    verdict, _ = parse_judge_verdict("This is definitely not CORRECT, I'm afraid.")
    assert verdict is False


def test_json_verdict_not_correct_string_is_NOT_a_pass():
    """Even when JSON parses, a non-recognised verdict value must
    fall through to the format-violation path, not to the keyword
    fallback."""
    verdict, _ = parse_judge_verdict('{"verdict": "not correct"}')
    assert verdict is False


def test_json_verdict_unknown_value_is_NOT_a_pass():
    verdict, _ = parse_judge_verdict('{"verdict": "maybe"}')
    assert verdict is False


def test_json_verdict_unknown_value_plus_surrounding_CORRECT_is_NOT_a_pass():
    """Ensure the old 'fall through to keyword after JSON parse' path
    is well and truly dead."""
    verdict, _ = parse_judge_verdict('The answer is CORRECT: {"verdict": "maybe"}')
    assert verdict is False


def test_garbage_input_is_format_violation():
    verdict, _ = parse_judge_verdict("foo bar baz")
    assert verdict is False


def test_empty_input_is_format_violation():
    verdict, _ = parse_judge_verdict("")
    assert verdict is False


# ---------------------------------------------------------------------------
# Reason field must be informative on the failure path.
# ---------------------------------------------------------------------------


def test_failure_reason_mentions_parse_issue():
    """When the parser fails to get a valid JSON verdict, the reason
    must make that visible in the log so operators can spot judge
    misbehaviour."""
    _, reason = parse_judge_verdict("this is just prose with no json")
    assert reason  # non-empty
    # The reason should hint at the format violation.
    lowered = reason.lower()
    assert any(
        hint in lowered for hint in ("json", "parse", "unparseable", "verdict")
    ), f"reason must explain the format violation, got: {reason!r}"
