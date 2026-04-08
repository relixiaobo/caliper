"""Caliper M1.1 end-to-end smoke test.

Runs the canonical lookup task ("Cambridge Dictionary--3" — define
*zeitgeist*) through the bp text-protocol agent, the v8 stale-ref
tolerant judge, and the lazy-detection scorer. The point is to prove
that the Phase 1 abstractions work end-to-end on one task before scaling
to the full 12-task v8 baseline in M1.3.

Run:

    uv run inspect eval examples/cambridge_smoke.py --model anthropic/claude-sonnet-4-6

Then:

    uv run inspect view

Task definition is sourced from ``docs/reference/curated-tasks.md``
(lookup bucket).
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from caliper.runtime import load_dotenv
from caliper.scorers import judge_stale_ref, lazy_detection
from caliper_browser_pilot import bp_agent

# Populate ANTHROPIC_API_KEY / OPENAI_API_KEY from a .env walked up from
# cwd. No-op if a .env file isn't found or the keys are already set.
load_dotenv()


CAMBRIDGE_ZEITGEIST = Sample(
    id="Cambridge Dictionary--3",
    input="Look up the definition, pronunciation, and examples of the word 'zeitgeist.'",
    target=(
        "UK: /ˈtsaɪt.ɡaɪst/ or /ˈzaɪt.ɡaɪst/, "
        "US: /ˈtsaɪt.ɡaɪst/ or /ˈzaɪt.ɡaɪst/; "
        "the general set of ideas, beliefs, feelings, etc."
    ),
    metadata={
        "bucket": "lookup",
        "source": "WebVoyager",
        "license": "academic",
        "is_time_sensitive": False,
        "last_validated": "2026-04-07",
        "reference_type": "possible",
        "start_url": "https://dictionary.cambridge.org/",
    },
)


@task
def cambridge_smoke() -> Task:
    """One-sample smoke test for the M1.1 caliper port."""
    return Task(
        dataset=[CAMBRIDGE_ZEITGEIST],
        solver=bp_agent(max_turns=12),
        scorer=[
            judge_stale_ref(model="anthropic/claude-sonnet-4-6"),
            lazy_detection(),
        ],
    )
