"""Multi-dimensional scorer base — placeholder for Phase 3.

The chatbot maxTurns scenario needs a scorer that returns 5 dimensions
(completeness, usefulness, honesty, no_fabrication, no_error_surface)
rather than a single binary verdict. This module provides the base class
those scorers will inherit from. RAG quality, chain-of-thought quality,
and other multi-dim scoring tasks will reuse it.

**Status: skeleton only.** Implementation lands when the chatbot
scenario starts in Phase 3. See ``docs/chatbot-maxturns.md`` §4.3 for
the design.
"""

from __future__ import annotations

# TODO Phase 3: implement MultiDimScorer base class.
# Sketch:
#
# from inspect_ai.scorer import Score, Scorer, Target, scorer
#
# def multi_dim_scorer(
#     dimensions: list[str],
#     judge_prompt_template: str,
#     judge_model: str = "anthropic/claude-sonnet-4-6",
# ) -> Scorer:
#     """A judge that returns N dimensions instead of one binary value.
#
#     The Score.value is the normalised average across dimensions; the
#     per-dimension breakdown lives in Score.metadata.
#     """
#     ...
