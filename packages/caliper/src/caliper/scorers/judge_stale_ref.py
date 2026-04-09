"""Stale-reference-tolerant LLM judge.

Ports the v8 judge prompt verbatim from
``docs/reference/inherited-artifacts.md`` §1. The prompt explicitly tells
the judge that reference answers may be outdated (the WebVoyager benchmark
was authored in 2023/2024 and the agent visits live sites today), and asks
for a structured JSON verdict so the parser in ``json_verdict.py`` can
reject the substring trap.

Reads the agent's final answer via the typed ``SolverState`` contract.
The solver is the only thing that writes ``agent_answer``; this scorer
is one of two that read it.

Do NOT use the agent's SKILL.md as the judge's system prompt — that was
the source of several bugs in browser-pilot v6. The judge gets a minimal
evaluator system prompt and ``temperature=0``.
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, accuracy, mean, scorer

from caliper.protocols import SolverState
from caliper.scoring import (
    JUDGE_SYSTEM_PROMPT,
    build_judge_prompt,
    score_judge,
)

# Re-export for backwards compatibility — external code that imported
# JUDGE_SYSTEM_PROMPT or build_judge_prompt from this module
# (e.g. baselines/build_v9.py, docs examples) continues to work.
# The canonical location is now caliper.scoring.
__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "build_judge_prompt",
    "judge_stale_ref",
]


@scorer(metrics=[accuracy(), mean()])
def judge_stale_ref(model: str = "anthropic/claude-sonnet-4-6") -> Scorer:
    """LLM-as-judge scorer with stale-reference tolerance.

    Reads the agent's answer from ``state.store_as(SolverState).agent_answer``
    (set by the solver), the goal from ``state.input_text``, and the
    reference from ``target.text``. Calls the configured judge model with
    ``temperature=0`` and the minimal evaluator system prompt.

    The judge model is **resolved lazily on the first call** to
    ``score()`` rather than at scorer-factory time. This is the
    Codex M1.3 P1 fix: calling ``get_model(...)`` at factory time
    initialises the provider client (which checks API keys) and
    raised ``PrerequisiteError`` whenever a Task was constructed in
    a credential-free environment, even if no eval was actually
    being run. Constructing a Task definition (in CI / unit tests
    / a bare machine) must NOT require API credentials. Inspect AI
    caches model instances, so the per-call lookup is effectively
    free after the first invocation.
    """

    async def score(state, target: Target) -> Score:
        ss = state.store_as(SolverState)
        agent_answer = ss.agent_answer

        # Delegate to the pure scoring function. It handles the
        # empty-answer case, prompt building, LLM call, and verdict
        # parsing — the same logic this scorer had inline before the
        # CaliperRecord refactor. This wrapper just bridges
        # TaskState → function arguments → Score.
        if not agent_answer:
            return Score(
                value=False,
                answer="",
                explanation="empty agent answer (no ANSWER: block extracted)",
            )

        result = await score_judge(
            goal=state.input_text,
            agent_answer=agent_answer,
            reference_answer=target.text,
            judge_model=model,
        )
        return Score(
            value=result.passed,
            answer=agent_answer,
            explanation=result.reason,
            metadata={"judge_raw": result.raw_response},
        )

    return score
