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
from caliper.scoring import score_verify


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

    Internally delegates to ``caliper.scoring.score_verify`` — the
    pure function that implements the spec execution and substring
    checking logic. This wrapper bridges the Inspect AI ``Scorer``
    protocol with caliper's Inspect-AI-independent scoring kernel.

    Args:
        cli_timeout: Per-command subprocess timeout in seconds.
            Defaults to 30s — shorter than the solver's default 60s
            because verification commands are expected to be simple
            DOM reads that should return almost instantly.
        require_agent_answer: When True (default), the scorer also
            asserts that ``SolverState.agent_answer`` is non-empty.
            This catches solver-plumbing regressions that pure
            post-hoc DOM checks would miss.
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

        # Pull the solver's answer for the "did the agent finish"
        # check. Done before verify so both failure modes surface.
        agent_answer = ""
        if require_agent_answer:
            try:
                ss = state.store_as(SolverState)
                agent_answer = ss.agent_answer
            except Exception:
                agent_answer = ""

        # Delegate spec execution to the pure function.
        result = await score_verify(
            verify_specs=specs,
            cli_timeout=cli_timeout,
        )

        failures = list(result.failures)

        # Agent-answer check runs AFTER verify specs so both
        # failure modes appear in the same explanation string.
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
                f"all {result.n_specs} verify steps passed"
                + (
                    f" (agent_answer: {agent_answer[:80]!r})"
                    if require_agent_answer and agent_answer
                    else ""
                )
                if all_passed
                else "; ".join(failures)
            ),
            metadata={"n_specs": result.n_specs, "results": result.per_spec},
        )

    return score
