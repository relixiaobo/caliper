"""Typed contracts shared by every solver, scorer, and adapter.

This module is the **single source of truth** for what state flows between
a Solver and the Scorers that read its output. Any solver in caliper core
or in any adapter package MUST populate ``SolverState`` via
``state.store_as(SolverState)``. Any scorer MUST read it the same way.

Without this contract, solvers and scorers communicate through an untyped
``state.store`` dict — and a typo or rename in one place silently breaks
the other. methodology.md principle 1 ("measurement comes before
optimization") demands that this kind of slippage be impossible.

The class names here are also the *only* place where field names appear,
so renaming a field is a single-file change.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from inspect_ai.util import StoreModel
from pydantic import Field


class SolverState(StoreModel):
    """The state contract between solvers and scorers.

    A solver writes these fields as it runs the agent loop. Scorers read
    them after the loop terminates. Both sides access the fields via
    ``state.store_as(SolverState)`` for type safety.

    Fields:
        agent_answer: The agent's final answer text. Empty string if the
            agent never produced an ``ANSWER:`` block (or equivalent).
        observed_page: ``True`` if the agent ran at least one observation
            command (e.g. ``bp read``, ``bp snapshot``) during the loop.
            Used by ``lazy_detection`` scorer to catch agents that
            answered from training data without looking at the page.
        commands_run: Number of CLI commands the solver executed on the
            agent's behalf. Debug aid; not currently used by any scorer.
    """

    agent_answer: str = Field(default="")
    observed_page: bool = Field(default=False)
    commands_run: int = Field(default=0)


@runtime_checkable
class Strategy(Protocol):
    """A first-class hook protocol for agent-loop meta-policies.

    A Strategy decides what happens at specific points in the agent loop
    that are NOT about "what tool to call" — that's the agent's job.
    Strategies decide things like:

    - What to do when the turn budget is exhausted (HardCut, ForceFinalize,
      PauseTurn, etc. in the chatbot maxTurns scenario)
    - When to inject a "wrapping up" warning
    - Whether to extend the budget on apparent progress
    - How to handle a tool failure that the agent can't recover from

    Strategies are explicitly *not* a parameter on Solver. They are an
    independent axis of the experimental matrix. The chatbot maxTurns
    scenario is the canonical first user; see
    ``docs/chatbot-maxturns.md`` for the full design.

    The protocol is intentionally minimal. Concrete strategies live in
    adapter/scenario packages, not in caliper core. caliper core never
    ships specific strategies — it only defines the protocol so multiple
    scenarios can interoperate.
    """

    name: str

    def before_turn(
        self, turn_idx: int, max_turns: int, state: Any
    ) -> None:
        """Called before each agent turn. Default: noop."""
        ...

    def on_limit_reached(self, state: Any, llm_call: Any) -> Any:
        """Called when the agent loop hits its budget. Returns Termination."""
        ...


# ---------------------------------------------------------------------------
# Task metadata schema (test-sets.md principles 2, 4, 5)
# ---------------------------------------------------------------------------


REQUIRED_METADATA_KEYS = frozenset({"bucket", "source"})

OPTIONAL_METADATA_KEYS = frozenset(
    {
        "start_url",          # entry point for browser/web tasks
        "license",            # source license (test-sets.md principle 5)
        "is_time_sensitive",  # whether reference answer expires
        "last_validated",     # ISO date the reference was confirmed correct
        "decay_rate",         # estimated freshness decay (low/med/high)
        "stability_score",    # CV across N runs (test-sets.md principle 3)
        "reference_type",     # "golden" | "possible"
    }
)


def validate_task_metadata(metadata: dict[str, Any]) -> list[str]:
    """Return a list of validation errors for a Sample's metadata dict.

    Empty list = valid. This is intentionally a function, not a model:
    Inspect AI's ``Sample.metadata`` is a plain dict and we don't want to
    force consumers to subclass anything. Loaders should call this on
    each sample they construct and either raise or warn.

    See test-sets.md principle 2 for the rationale.
    """
    errors: list[str] = []
    for key in REQUIRED_METADATA_KEYS:
        if key not in metadata:
            errors.append(f"missing required metadata key: {key!r}")
    unknown = set(metadata.keys()) - REQUIRED_METADATA_KEYS - OPTIONAL_METADATA_KEYS
    # Unknown keys are allowed (loaders may pass through source-specific
    # fields), but flag them in case of typos. Caller decides whether to
    # warn or pass.
    if unknown:
        errors.append(f"unknown metadata keys (likely fine, but check): {sorted(unknown)!r}")
    return errors
