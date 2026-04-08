"""Caliper quickstart — 30 seconds to your first eval run.

If you can read Python, you can read this file. It is the entire
"hello world" of caliper:

    1. Define one Sample (the task)
    2. Build a solver (which CLI agent to use)
    3. Pick scorers (judge + lazy detection)
    4. Wire them into a Task with @task
    5. `inspect eval examples/quickstart.py --model anthropic/claude-sonnet-4-6`

That's it. Everything else in caliper is variations on this shape.

Prerequisites:
- `bp` CLI on your $PATH (or any other CLI agent — change `bp_agent` to
  your adapter's factory)
- A `.env` at the project root containing `ANTHROPIC_API_KEY=...`
- Chrome with remote debugging enabled (only required for the bp example)
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from caliper.runtime import load_dotenv
from caliper.scorers import judge_stale_ref, lazy_detection
from caliper_browser_pilot import bp_agent

load_dotenv()


@task
def quickstart() -> Task:
    return Task(
        dataset=[
            Sample(
                id="bbc-climate",
                input=(
                    "Find the article 'What is climate change? A really simple guide' "
                    "and use it to answer what is causing recent climate change."
                ),
                target=(
                    "This recent climate change has been caused by human activity, "
                    "mainly the widespread use of fossil fuels - coal, oil and gas"
                ),
                metadata={
                    "bucket": "navigate",
                    "source": "WebVoyager",
                    "license": "academic",
                    "is_time_sensitive": False,
                    "last_validated": "2026-04-07",
                    "start_url": "https://www.bbc.com/news",
                },
            ),
        ],
        solver=bp_agent(max_turns=12),
        scorer=[
            judge_stale_ref(),
            lazy_detection(),
        ],
    )
