"""Shared internals for the v8 baseline ports.

Module-private (`_` prefix) by convention. Holds the data path,
default parameters, and the ``_build_task`` factory used by both
``v8_baseline.py`` (the full 12-task baseline) and ``v8_buckets.py``
(the four bucket-specific helpers).

Why this file exists at all: Inspect AI's task discovery picks up
every ``@task`` in a Python file passed to ``inspect eval``. To
make ``inspect eval .../v8_baseline.py`` actually run only the
baseline (and not also pull in the bucket helpers), the bucket
helpers have to live in a different file. This common module hosts
the shared scaffolding so neither of the public files duplicates
data-loading or scorer-wiring logic.
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task
from inspect_ai.dataset import Dataset

from caliper.datasets import load_webvoyager_jsonl
from caliper.scorers import judge_stale_ref, lazy_detection

from caliper_browser_pilot import bp_agent

# v8 baseline parameters — keep in sync with
# docs/reference/baseline-v8.md.
DEFAULT_MAX_TURNS = 12
DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-4-6"

# The data file lives inside the package (caliper_browser_pilot/data/)
# so it's resolved relative to this Python file rather than relative
# to cwd. ``inspect eval`` works from any working directory.
#
# It's also declared in [tool.setuptools.package-data] in this
# package's pyproject.toml so the JSONL file is included in built
# wheels and sdists, not just editable installs.
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "v8_curated.jsonl"


def full_dataset() -> Dataset:
    """Load all 12 v8 curated tasks from the bundled JSONL file."""
    return load_webvoyager_jsonl(DATA_PATH, name="v8_curated")


def build_task(
    dataset: Dataset,
    *,
    epochs: int,
    judge_model: str,
    max_turns: int,
) -> Task:
    """Wire ``dataset`` into a Task with the standard bp solver and
    judge + lazy detection scorers."""
    return Task(
        dataset=dataset,
        solver=bp_agent(max_turns=max_turns),
        scorer=[
            judge_stale_ref(model=judge_model),
            lazy_detection(),
        ],
        epochs=epochs,
    )
