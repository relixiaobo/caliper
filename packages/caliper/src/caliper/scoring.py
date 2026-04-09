"""Pure scoring functions — caliper's measurement logic without Inspect AI.

These functions accept ``CaliperRecord`` objects (or their individual
fields) and return structured results. They are the **kernel** of
caliper's measurement layer. The Inspect AI scorers in
``caliper.scorers`` are thin wrappers that convert ``TaskState`` to
``CaliperRecord`` fields and call these functions.

External projects that don't use Inspect AI can call these directly
via ``CaliperEvaluator`` or import them individually.

## Design principle

Every function in this module is a **pure function** in the sense
that its inputs fully determine its outputs. The only side effects
are:

- ``score_judge``: makes an LLM API call (via Inspect AI's model
  layer internally, but the function signature doesn't expose any
  Inspect AI types).
- ``score_verify``: runs subprocess commands via ``run_cli`` when
  ``verify_specs`` are provided (but not when ``verify_results``
  are pre-computed).

``score_lazy`` is fully pure — no I/O at all.

## Relationship to caliper.scorers

caliper.scoring (this module):
    score_lazy(answer, observed) -> bool
    score_judge(goal, answer, ref, model) -> JudgeResult
    score_verify(specs_or_results) -> VerifyResult

caliper.scorers (Inspect AI wrappers):
    lazy_detection() -> Scorer      # calls score_lazy internally
    judge_stale_ref() -> Scorer     # calls score_judge internally
    verify_commands() -> Scorer     # calls score_verify internally

The split ensures one codebase for the logic, two entry points
for different integration modes.
"""

from __future__ import annotations

from typing import Any

from caliper.record import CaliperRecord, JudgeResult, VerifyResult

# NOTE: parse_judge_verdict is imported lazily inside score_judge()
# to avoid a circular import. The chain is:
#   caliper.scoring → caliper.scorers.json_verdict
#   → caliper.scorers.__init__ → caliper.scorers.judge_stale_ref
#   → caliper.scoring (cycle!)
# Lazy import breaks the cycle: at module load time scoring.py
# doesn't touch caliper.scorers; at call time everything is loaded.

# ---------------------------------------------------------------------------
# Judge prompt constants (shared by score_judge and judge_stale_ref scorer)
# ---------------------------------------------------------------------------
#
# These lived in caliper.scorers.judge_stale_ref until the CaliperRecord
# refactor, which created a circular import (scoring ↔ judge_stale_ref).
# They now live here — the canonical location for caliper's measurement
# logic — and judge_stale_ref.py imports them from here.

JUDGE_SYSTEM_PROMPT = (
    "You are an evaluator. Respond only with the JSON object requested."
)


def build_judge_prompt(goal: str, reference: str, agent_answer: str) -> str:
    """Format the v8 stale-reference-tolerant judge prompt.

    Verbatim port from ``docs/reference/inherited-artifacts.md`` §1. Any
    change to this string must re-run the judge self-evaluation suite
    (Phase 2 / M2.1).
    """
    return f"""You are grading whether a web agent correctly answered a question about a live website.

Task: {goal}
Reference answer (may be outdated — the benchmark was authored in 2023/2024): {reference}
Agent's answer: {agent_answer}

Grading rules:
- The agent visited the live site NOW. If the task asks for "latest", "current",
  "recent", or "most recent" data, the agent's answer reflects today's reality.
  The reference may be stale. Accept factually-plausible current answers even when
  the specific product version/name/date differs from the reference.
  Example: reference says "MacBook Air M2 $1099"; agent says "MacBook Air M5 $1099" —
  this is CORRECT (Apple moved to M5, prices held). Similarly iPhone 15 → iPhone 17.
- For non-time-sensitive tasks (pronunciations, math, historical facts, fixed
  documentation like "Enterprise has X GB more than Team"), the agent's answer must
  match the reference's substantive content.
- The agent's wording may differ but the substance must match.
- Partial answers covering the key information count as correct.
- An answer that describes how to do it without actually having done it is INCORRECT.
- An answer that fabricates details the agent couldn't have verified is INCORRECT.
- An empty or evasive answer is INCORRECT.

Respond with ONLY a JSON object on a single line:
{{"verdict": "correct"}} or {{"verdict": "incorrect", "reason": "<short reason>"}}"""


# ---------------------------------------------------------------------------
# Lazy detection (pure, no I/O)
# ---------------------------------------------------------------------------


def score_lazy(agent_answer: str, observed: bool) -> bool:
    """Return ``True`` if the agent is "lazy" — answered without observing.

    An agent is lazy when it produced a non-empty answer but never
    called any observation command. This means it answered from
    training data rather than from the actual target environment.

    This is the same logic as ``caliper.scorers.lazy_detection``,
    extracted as a pure function so it can be called without
    constructing an Inspect AI ``TaskState``.
    """
    return bool(agent_answer) and not observed


# ---------------------------------------------------------------------------
# LLM judge (async — makes an API call)
# ---------------------------------------------------------------------------


async def score_judge(
    goal: str,
    agent_answer: str,
    reference_answer: str,
    judge_model: str = "anthropic/claude-sonnet-4-6",
    judge_prompt: str | None = None,
) -> JudgeResult:
    """Run an LLM judge on one sample and return a structured result.

    Args:
        goal: The task description the agent received.
        agent_answer: The agent's final answer. If empty, returns
            ``JudgeResult(passed=False)`` without calling the LLM.
        reference_answer: The reference answer to judge against.
            If empty, raises ``ValueError`` — use ``score_lazy``
            for tasks without reference answers.
        judge_model: Model identifier for the judge (e.g.
            ``"anthropic/claude-sonnet-4-6"``). Resolved via
            Inspect AI's model registry.
        judge_prompt: Custom judge prompt template. If ``None``,
            uses caliper's built-in stale-ref-tolerant prompt
            (``build_judge_prompt``). The custom prompt receives
            ``goal``, ``reference_answer``, and ``agent_answer``
            as ``.format()`` keyword arguments.

    Returns:
        ``JudgeResult`` with ``passed``, ``reason``, and the raw
        judge response for debugging.
    """
    if not agent_answer:
        return JudgeResult(
            passed=False,
            reason="empty agent answer (no ANSWER: block extracted)",
        )

    if not reference_answer:
        raise ValueError(
            "score_judge requires a non-empty reference_answer. "
            "For tasks without references, use score_lazy only."
        )

    # Build the prompt.
    if judge_prompt is not None:
        prompt = judge_prompt.format(
            goal=goal,
            reference_answer=reference_answer,
            agent_answer=agent_answer,
        )
    else:
        prompt = build_judge_prompt(
            goal=goal,
            reference=reference_answer,
            agent_answer=agent_answer,
        )

    # Call the judge model via Inspect AI's model layer.
    # This is an internal dependency — the function signature
    # exposes only strings, not Inspect AI types.
    from inspect_ai.model import (
        ChatMessageSystem,
        ChatMessageUser,
        GenerateConfig,
        get_model,
    )

    model = get_model(judge_model, config=GenerateConfig(temperature=0))
    result = await model.generate(
        [
            ChatMessageSystem(content=JUDGE_SYSTEM_PROMPT),
            ChatMessageUser(content=prompt),
        ]
    )

    # Lazy import — see module-level comment about the circular chain.
    from caliper.scorers.json_verdict import parse_judge_verdict

    passed, reason = parse_judge_verdict(result.completion)
    return JudgeResult(
        passed=passed,
        reason=reason,
        raw_response=result.completion[:500],
    )


# ---------------------------------------------------------------------------
# Deterministic verification (async — may run subprocesses)
# ---------------------------------------------------------------------------


async def score_verify(
    verify_specs: list[dict[str, Any]] | None = None,
    verify_results: list[dict[str, Any]] | None = None,
    cli_timeout: float = 30.0,
) -> VerifyResult:
    """Run deterministic post-hoc verification on one sample.

    Two modes:

    1. **Pre-computed results** (``verify_results`` provided): the
       project already ran the verification commands and passes the
       outcomes. caliper just checks them. No subprocesses.

    2. **Specs to run** (``verify_specs`` provided, no
       ``verify_results``): caliper runs each spec's ``command``
       via ``run_cli`` and checks ``expect_contains``.

    If neither is provided, returns a passing result with 0 specs
    (no verification requested).

    Args:
        verify_specs: List of ``{command, expect_contains, description}``
            dicts. Each ``command`` is an argv list run via ``run_cli``.
        verify_results: List of ``{passed, description}`` dicts. Takes
            precedence over ``verify_specs``.
        cli_timeout: Per-command timeout in seconds (only used when
            running specs, not for pre-computed results).
    """
    # Mode 1: pre-computed results.
    if verify_results is not None:
        failures = [
            r.get("description", f"spec {i}")
            for i, r in enumerate(verify_results)
            if not r.get("passed", False)
        ]
        return VerifyResult(
            passed=not failures,
            n_specs=len(verify_results),
            failures=failures,
            per_spec=list(verify_results),
        )

    # Mode 2: run specs via run_cli.
    if not verify_specs:
        return VerifyResult(passed=True, n_specs=0)

    from caliper.runtime import run_cli

    failures: list[str] = []
    per_spec: list[dict[str, Any]] = []

    for i, spec in enumerate(verify_specs):
        argv = spec.get("command") or []
        expected = spec.get("expect_contains", "")
        desc = spec.get("description") or f"verify step {i + 1}"

        if not argv:
            failures.append(f"{desc}: empty command")
            per_spec.append(
                {"description": desc, "passed": False, "reason": "empty command"}
            )
            continue

        raw = await run_cli(list(argv), timeout=cli_timeout)

        if raw.startswith("ERROR"):
            first_line = raw.splitlines()[0] if raw else "ERROR"
            failures.append(f"{desc}: command failed: {first_line}")
            per_spec.append(
                {
                    "description": desc,
                    "passed": False,
                    "reason": f"run_cli error: {first_line}",
                }
            )
            continue

        if expected and expected in raw:
            per_spec.append({"description": desc, "passed": True})
        else:
            failures.append(
                f"{desc}: expected {expected!r} in output, got {raw[:200]!r}"
            )
            per_spec.append(
                {
                    "description": desc,
                    "passed": False,
                    "reason": f"expected {expected!r} not in output",
                }
            )

    return VerifyResult(
        passed=not failures,
        n_specs=len(verify_specs),
        failures=failures,
        per_spec=per_spec,
    )


# ---------------------------------------------------------------------------
# TaskState → CaliperRecord converter (Inspect AI bridge)
# ---------------------------------------------------------------------------


def taskstate_to_record(state: Any, target: Any) -> CaliperRecord:
    """Convert an Inspect AI ``TaskState`` + ``Target`` to a ``CaliperRecord``.

    This is the bridge between Inspect AI's eval loop (which produces
    ``TaskState`` objects) and caliper's pure scoring functions (which
    accept ``CaliperRecord``). Used internally by the refactored
    ``caliper.scorers`` wrappers.

    Args:
        state: An Inspect AI ``TaskState`` with a ``SolverState`` in
            its store.
        target: An Inspect AI ``Target`` whose ``.text`` is the
            reference answer.

    The function imports ``SolverState`` lazily to avoid circular
    imports (``caliper.protocols`` → ``caliper.scoring`` would be
    circular if done at module level).
    """
    from caliper.protocols import SolverState

    ss = state.store_as(SolverState)
    metadata = state.metadata or {}

    return CaliperRecord(
        sample_id=str(getattr(state, "sample_id", "") or metadata.get("id", "")),
        bucket=metadata.get("bucket", "unknown"),
        goal=state.input_text,
        agent_answer=ss.agent_answer,
        observed=ss.observed_page,
        reference_answer=target.text if target and hasattr(target, "text") else "",
        verify_specs=metadata.get("verify"),
        input_tokens=0,  # filled by Inspect AI's usage tracking, not here
        output_tokens=0,
        commands_run=ss.commands_run,
        epoch=getattr(state, "epoch", 1),
        metadata=metadata,
    )
