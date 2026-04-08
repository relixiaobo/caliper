"""The 4 bucket-specific subsets of the v8 baseline.

Each ``@task`` runs only one bucket's tasks (3 samples × epochs=2 = 6
runs at default). Use these for fast debug iteration when you want to
focus on a single failure mode without paying for the full baseline.

Lives in its own file (separate from ``v8_baseline.py``) because
Inspect AI discovers every ``@task`` in a file passed to
``inspect eval``. Keeping the four bucket helpers here means the
documented baseline invocation
``inspect eval .../v8_baseline.py`` runs exactly the 12-task baseline
and not 12+3+3+3+3 = 24 samples doubled by epochs.

Inspect AI invocations:

    inspect eval .../v8_buckets.py@v8_compare       # only the compare bucket
    inspect eval .../v8_buckets.py                  # all 4 buckets, structurally
                                                    # equivalent to v8_baseline
                                                    # (no overlap, same 12 samples)
"""

from __future__ import annotations

from inspect_ai import Task, task

from caliper.datasets import filter_by_bucket
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
def v8_lookup(
    epochs: int = 2,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> Task:
    """Lookup bucket: Cambridge Dictionary--3, Wolfram Alpha--0, Wolfram Alpha--2."""
    return build_task(
        filter_by_bucket(full_dataset(), "lookup"),
        epochs=epochs,
        judge_model=judge_model,
        max_turns=max_turns,
    )


@task
def v8_search(
    epochs: int = 2,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> Task:
    """Search bucket: Allrecipes--3, Coursera--0, Huggingface--3."""
    return build_task(
        filter_by_bucket(full_dataset(), "search"),
        epochs=epochs,
        judge_model=judge_model,
        max_turns=max_turns,
    )


@task
def v8_compare(
    epochs: int = 2,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> Task:
    """Compare bucket: Apple--0, Apple--3, Allrecipes--0.

    Apple--3 is the one persistent Sonnet v8 failure (run 2 hits the
    12-step limit with an empty answer). Caliper's port should
    reproduce this — if your bucket-level result is 6/6 instead of
    5/6, you've inadvertently relaxed max_turns or fixed something
    upstream.
    """
    return build_task(
        filter_by_bucket(full_dataset(), "compare"),
        epochs=epochs,
        judge_model=judge_model,
        max_turns=max_turns,
    )


@task
def v8_navigate(
    epochs: int = 2,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> Task:
    """Navigate bucket: GitHub--3, BBC News--5, ArXiv--2."""
    return build_task(
        filter_by_bucket(full_dataset(), "navigate"),
        epochs=epochs,
        judge_model=judge_model,
        max_turns=max_turns,
    )
