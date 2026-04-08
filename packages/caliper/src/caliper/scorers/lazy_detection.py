"""Lazy-behavior detection scorer.

An agent is "lazy" if it produced an ANSWER without ever calling a real
observation command — i.e., it ignored the page state and made up an
answer from training data. The text-protocol solver auto-opens
``start_url`` before the agent loop, so the LLM does see an initial
snapshot; lazy detection specifically catches the case where the agent
ignored that snapshot and never called any observation command in the
loop itself.

This scorer is intentionally tool-agnostic. It does NOT know what
"observation commands" mean for any specific CLI — that's the solver's
job, encoded as the set passed to ``text_protocol_agent(observation_commands=...)``
by an adapter package. This scorer just reads the resulting boolean
``observed_page`` flag from the typed ``SolverState`` contract.

Earlier versions of this scorer accepted an ``observation_commands``
parameter that was unused — a "two sources of truth" smell flagged in
the structural review. The parameter has been removed: the solver is
the only authoritative source for what counts as observation.
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer

from caliper.protocols import SolverState


@scorer(metrics=[mean()])
def lazy_detection() -> Scorer:
    """Flag samples where the agent answered without observing the page.

    The score is ``1.0`` for "lazy" (bad) and ``0.0`` for "not lazy" (good),
    so the aggregated mean is the lazy-failure rate.
    """

    async def score(state, target: Target) -> Score:
        ss = state.store_as(SolverState)
        is_lazy = bool(ss.agent_answer) and not ss.observed_page
        return Score(
            value=1.0 if is_lazy else 0.0,
            answer=ss.agent_answer,
            explanation=(
                "lazy: answered without observation"
                if is_lazy
                else ("not lazy" if ss.observed_page else "no answer given")
            ),
            metadata={"observed_page": ss.observed_page},
        )

    return score
