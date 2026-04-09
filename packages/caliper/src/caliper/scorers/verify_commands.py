"""Deterministic post-hoc verification scorer.

Reads a list of verification specs from ``state.metadata["verify"]``
and runs each one via ``run_cli`` after the agent loop finishes. Each
spec is a dict shaped like:

    {
        "command":         ["bp", "eval", "..."],
        "expect_contains": "<substring>",
        "description":     "Human-readable pass condition"  # optional
    }

If every spec's ``expect_contains`` appears in its command's stdout,
the score is CORRECT. Otherwise INCORRECT, with per-spec pass/fail
detail in the explanation.

## When to use this instead of ``judge_stale_ref``

This is the Layer 1 smoke scorer (per ``docs/test-sets.md``). Use it
for deterministic tasks whose pass condition can be expressed as a
DOM query or tool-output substring check — e.g. "both checkboxes are
checked", "URL is /secure", "the word 'Hello World!' is visible".

Advantages over an LLM judge for this task class:

- **Deterministic**. Same result on every run; no judge-variance.
- **Fast**. No judge model call. Scoring is a single subprocess round-
  trip per spec.
- **Free**. No API spend during CI.
- **Self-contained**. Doesn't need API credentials in the smoke CI
  environment.

Disadvantages:

- **Brittle**. Any CSS selector change in the target site breaks the
  verification. Only use for sites you control or test fixtures.
- **Not suitable for open-ended tasks**. There's no good
  ``expect_contains`` substring for "compare the prices of MacBook
  Air models" — use ``judge_stale_ref`` for those.

## The design anti-pattern this scorer avoids

Early browser-pilot iteration had this logic hardcoded inside a
task-specific ``TaskRunner.verify()`` method. That tied verification
to a single task-loader shape and made the verification step
invisible to caliper's scorer plumbing (no per-spec pass metric, no
A/B-diffable output). Extracting it as a proper scorer means:

- The verify step shows up in ``caliper report``'s bucket table.
- Failing specs are visible in the Inspect AI transcript.
- A/B diffs can compare verification results across solver changes.
- Same scorer works for any CLI tool (computer-pilot, chatbot
  adapters) without modification.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer

from caliper.protocols import SolverState
from caliper.runtime import run_cli


@scorer(metrics=[accuracy()])
def verify_commands(
    cli_timeout: float = 30.0,
    require_agent_answer: bool = True,
) -> Scorer:
    """Post-hoc verification scorer for deterministic tasks.

    Reads ``state.metadata["verify"]`` — a list of spec dicts, each
    with a ``command`` argv list and an ``expect_contains`` substring.
    Runs every command via ``run_cli`` and returns CORRECT iff all
    specs' expectations are met AND (by default) the solver produced
    a non-empty ``agent_answer``.

    Args:
        cli_timeout: Per-command subprocess timeout in seconds.
            Defaults to 30s — shorter than the solver's default 60s
            because verification commands are expected to be simple
            DOM reads that should return almost instantly. Raise it
            if a specific task needs heavier post-hoc work.
        require_agent_answer: When True (default), the scorer also
            asserts that ``SolverState.agent_answer`` is non-empty.
            This catches the "browser state happens to match but the
            solver loop broke / ANSWER extraction regressed / agent
            timed out" failure mode that pure post-hoc DOM checks
            would miss. Set to False only if your task intentionally
            doesn't expect the agent to write an ``ANSWER:`` block
            (rare — most Layer 1 smoke tasks do).

    The scorer is tool-agnostic. It only touches ``run_cli`` and the
    sample metadata. The ``cli_name`` is implied by ``spec["command"][0]``
    — each spec names its own executable. This means a single task
    could in principle mix verifications across tools (rare but
    supported).
    """

    async def score(state, target: Target) -> Score:
        metadata: dict[str, Any] = state.metadata or {}
        specs = metadata.get("verify") or []

        if not specs:
            return Score(
                value=False,
                answer="",
                explanation=(
                    "no verify commands in metadata['verify'] — this "
                    "scorer expects the task definition to specify the "
                    "deterministic post-hoc checks. Either provide a "
                    "'verify' list or use judge_stale_ref instead."
                ),
                metadata={"n_specs": 0},
            )

        # Pull the solver's answer if the caller wants the "agent
        # must have finished cleanly" invariant. Done BEFORE any
        # verify step so an answer miss is always surfaced, even
        # when the first verify step fails in some other way.
        agent_answer = ""
        if require_agent_answer:
            try:
                ss = state.store_as(SolverState)
                agent_answer = ss.agent_answer
            except Exception:
                # state.store_as may not be available in tests that
                # pass a _FakeState — treat as empty answer.
                agent_answer = ""

        results: list[dict[str, Any]] = []
        failures: list[str] = []

        for i, spec in enumerate(specs):
            if not isinstance(spec, dict):
                failures.append(f"spec {i}: not a dict (got {type(spec).__name__})")
                continue

            argv = spec.get("command") or []
            expected = spec.get("expect_contains", "")
            desc = spec.get("description") or f"verify step {i + 1}"

            if not argv:
                failures.append(f"{desc}: spec has empty 'command'")
                results.append(
                    {"description": desc, "passed": False, "reason": "empty command"}
                )
                continue

            raw = await run_cli(list(argv), timeout=cli_timeout)

            # run_cli returns an ERROR-prefixed string on any failure;
            # that case counts as verification failure even if the
            # error string happens to contain the expected substring.
            if raw.startswith("ERROR"):
                first_line = raw.splitlines()[0] if raw else "ERROR"
                failures.append(f"{desc}: command failed: {first_line}")
                results.append(
                    {
                        "description": desc,
                        "passed": False,
                        "reason": f"run_cli error: {first_line}",
                    }
                )
                continue

            if expected and expected in raw:
                results.append({"description": desc, "passed": True})
            else:
                failures.append(
                    f"{desc}: expected {expected!r} in output, got {raw[:200]!r}"
                )
                results.append(
                    {
                        "description": desc,
                        "passed": False,
                        "reason": f"expected {expected!r} not in output",
                    }
                )

        # Agent-answer check runs AFTER the verify specs so a broken
        # solver loop and a broken verify spec both surface in the
        # same explanation string instead of one short-circuiting
        # the other.
        if require_agent_answer and not agent_answer:
            failures.append(
                "agent produced no ANSWER: block (SolverState.agent_answer "
                "is empty) — the solver loop may have crashed, timed out, "
                "or regressed in answer extraction. Pass "
                "require_agent_answer=False to disable this check."
            )

        all_passed = not failures
        return Score(
            value=all_passed,
            answer=agent_answer,
            explanation=(
                f"all {len(specs)} verify steps passed"
                + (
                    f" (agent_answer: {agent_answer[:80]!r})"
                    if require_agent_answer and agent_answer
                    else ""
                )
                if all_passed
                else "; ".join(failures)
            ),
            metadata={"n_specs": len(specs), "results": results},
        )

    return score
