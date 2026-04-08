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

from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageUser,
    GenerateConfig,
    get_model,
)
from inspect_ai.scorer import Score, Scorer, Target, accuracy, mean, scorer

from caliper.protocols import SolverState
from caliper.scorers.json_verdict import parse_judge_verdict

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


@scorer(metrics=[accuracy(), mean()])
def judge_stale_ref(model: str = "anthropic/claude-sonnet-4-6") -> Scorer:
    """LLM-as-judge scorer with stale-reference tolerance.

    Reads the agent's answer from ``state.store_as(SolverState).agent_answer``
    (set by the solver), the goal from ``state.input_text``, and the
    reference from ``target.text``. Calls the configured judge model with
    ``temperature=0`` and the minimal evaluator system prompt.
    """
    judge_model = get_model(model, config=GenerateConfig(temperature=0))

    async def score(state, target: Target) -> Score:
        ss = state.store_as(SolverState)
        agent_answer = ss.agent_answer
        if not agent_answer:
            return Score(
                value=False,
                answer="",
                explanation="empty agent answer (no ANSWER: block extracted)",
            )

        prompt = build_judge_prompt(
            goal=state.input_text,
            reference=target.text,
            agent_answer=agent_answer,
        )
        result = await judge_model.generate(
            [
                ChatMessageSystem(content=JUDGE_SYSTEM_PROMPT),
                ChatMessageUser(content=prompt),
            ]
        )
        passed, reason = parse_judge_verdict(result.completion)
        return Score(
            value=passed,
            answer=agent_answer,
            explanation=reason,
            metadata={"judge_raw": result.completion[:500]},
        )

    return score
