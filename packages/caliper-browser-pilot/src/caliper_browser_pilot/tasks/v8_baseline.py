"""The full 12-task v8 baseline.

Exposes exactly **one** ``@task`` so that

    inspect eval packages/caliper-browser-pilot/.../tasks/v8_baseline.py \\
        --model anthropic/claude-sonnet-4-6

discovers and runs ``v8_baseline`` only — 12 samples × epochs=2 = 24
runs total. Bucket-specific helpers live in ``v8_buckets.py`` so they
don't get pulled into this file's discovery scope (Codex M1.3 P2).

The v8 baseline anchors the M1.6 cost-aware run; pass rate must
match ``docs/reference/baseline-v8.md`` within ±1 sample:

  bucket    Sonnet pass rate
  lookup    6/6
  search    6/6
  compare   5/6  (Apple--3 run 2 hits the 12-step limit; the one
                  persistent v8 failure caliper must reproduce)
  navigate  6/6
  TOTAL     23/24
"""

from __future__ import annotations

from inspect_ai import Task, task

from caliper.runtime import load_dotenv

from caliper_browser_pilot.tasks._v8_common import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_MAX_TURNS,
    build_task,
    full_dataset,
)

# Populate ANTHROPIC_API_KEY / OPENAI_API_KEY from a .env walked up
# from cwd. No-op if .env is missing or keys are already set.
load_dotenv()


@task
def v8_baseline(
    epochs: int = 2,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> Task:
    """All 12 v8 curated tasks. The full Phase 1 baseline.

    Args:
        epochs: N for variance measurement. Default 2 (methodology
            principle 2: N≥2 is the floor).
        judge_model: Model used for the stale-ref-tolerant judge.
            Independent of the solver model.
        max_turns: Solver agent loop turn limit. Default 12 matches
            the v8 baseline. Do NOT relax this without re-validating
            against the v8 anchors — the Apple--3 canary failure is
            sensitive to it.
    """
    return build_task(
        full_dataset(),
        epochs=epochs,
        judge_model=judge_model,
        max_turns=max_turns,
    )
