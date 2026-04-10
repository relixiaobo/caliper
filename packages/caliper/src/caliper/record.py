"""CaliperRecord — the universal data contract for agent evaluation.

This dataclass is the interface between any agent system and caliper's
measurement layer. Any project that can produce a ``CaliperRecord`` per
sample can use caliper's full scoring, aggregation, and comparison
capabilities — without depending on Inspect AI's ``TaskState`` or
running inside an Inspect AI eval loop.

## Two integration paths, one data contract

Path A (Inspect AI full mode — existing):
    bp_agent → TaskState → taskstate_to_record() → CaliperRecord → scoring

Path B (standalone — new):
    any agent → CaliperRecord → CaliperEvaluator.evaluate() → Report

Both paths converge at CaliperRecord. The scoring functions in
``caliper.scoring`` accept CaliperRecords directly. The Inspect AI
scorers in ``caliper.scorers`` are thin wrappers that convert
TaskState → CaliperRecord first.

## What the project decides vs what caliper enforces

Project decides:
    - What tasks to evaluate (``goal``, ``reference_answer``)
    - What "correct" means (custom ``judge_prompt``, or use caliper's default)
    - How to group tasks (``bucket``)
    - What model to test

caliper enforces (via required fields):
    - ``observed`` is mandatory → lazy detection always runs
    - ``agent_answer`` is explicit → empty answer = explicit failure, not silent skip
    - ``bucket`` is mandatory → per-group aggregation is the default, not an opt-in
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaliperRecord:
    """One sample's agent output, ready for caliper scoring.

    Required fields have no default — they MUST be provided by the
    agent project. This is intentional: the methodology principles
    are enforced at the type level, not via runtime checks that
    someone might skip.
    """

    # ── Identity ──────────────────────────────────────────────────
    sample_id: str
    """Unique identifier for this sample (e.g. ``"heroku-login"``,
    ``"Apple--0"``). Used for per-sample failure attribution."""

    bucket: str
    """Task category for aggregated reporting (e.g. ``"lookup"``,
    ``"smoke"``). The project defines its own taxonomy; caliper
    groups by this label without interpreting it."""

    # ── Task ──────────────────────────────────────────────────────
    goal: str
    """The task description the agent received. Passed to the LLM
    judge verbatim as the "Task:" field in the judge prompt."""

    # ── Agent output ──────────────────────────────────────────────
    agent_answer: str
    """The agent's final answer. Empty string means the agent never
    produced an answer (timeout, crash, etc.) — caliper treats this
    as an explicit failure."""

    observed: bool
    """Whether the agent actually observed the target environment
    (read a page, ran a tool, checked state) before answering.
    ``False`` means the agent answered from training data without
    looking — ``score_lazy()`` uses this to flag lazy behaviour.
    This field is mandatory because lazy detection is a non-negotiable
    part of caliper's measurement methodology."""

    # ── Optional: reference for LLM judge ─────────────────────────
    reference_answer: str = ""
    """Reference answer for the LLM judge. If empty, ``score_judge``
    is skipped (there's nothing to judge against). If non-empty,
    ``score_judge`` calls the configured judge model with the
    stale-ref-tolerant prompt (or the project's custom prompt)."""

    # ── Optional: deterministic verification ──────────────────────
    verify_specs: list[dict] | None = None
    """Post-hoc verification specs for ``score_verify``. Each dict
    has ``command`` (argv list), ``expect_contains`` (substring),
    optional ``description``. If provided, caliper runs these via
    ``run_cli`` and checks the expected substrings. If ``None``,
    verify scoring is skipped."""

    verify_results: list[dict] | None = None
    """Pre-computed verification results. If the project already ran
    the verification commands itself, it can pass the results here
    to skip the ``run_cli`` step. Each dict has ``passed`` (bool)
    and ``description`` (str). Takes precedence over
    ``verify_specs`` when both are provided."""

    # ── Optional: token usage ─────────────────────────────────────
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    has_cache_info: bool = False
    """Set to ``True`` if the token fields above are real
    provider-reported values (even if zero). ``False`` means the
    project didn't track tokens and caliper should mark the usage
    data as "unknown" rather than "zero"."""

    # ── Optional: agent metadata ──────────────────────────────────
    commands_run: int = 0
    """Number of tool/CLI commands the agent executed. Debug aid;
    not used by any scorer but surfaced in reports."""

    epoch: int = 1
    """Epoch number for multi-run variance measurement. Projects
    running N≥2 epochs per sample set this to 1, 2, ... N."""

    # ── Optional: provenance ──────────────────────────────────────
    project: str = ""
    """Identifier for the project that produced this record (e.g.
    ``"browser-pilot"``, ``"my-chatbot"``, ``"internal-rag-agent"``).
    Used by ``caliper.store`` (Phase 4) for cross-project aggregation
    and drift detection. Not used by any scorer — purely provenance.

    When multiple projects submit eval data to the same caliper
    log store, this field is what distinguishes "project A's judge
    accuracy is 96% and project B's is 82%" from "the overall
    average is 89%". Without it, cross-project analysis can't
    attribute findings to specific projects."""

    model: str = ""
    """Identifier for the agent model (e.g.
    ``"anthropic/claude-sonnet-4-6"``, ``"openai/gpt-5.4"``).
    Surfaced in ``BucketReport.model_name`` and in the
    ``caliper diagnose`` output. Not used by any scorer."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary project-specific metadata. caliper passes it
    through to reports without interpreting it."""


@dataclass
class JudgeResult:
    """Result of an LLM judge evaluation on one sample."""

    passed: bool
    reason: str
    raw_response: str = ""


@dataclass
class VerifyResult:
    """Result of deterministic post-hoc verification on one sample."""

    passed: bool
    n_specs: int
    failures: list[str] = field(default_factory=list)
    per_spec: list[dict] = field(default_factory=list)
