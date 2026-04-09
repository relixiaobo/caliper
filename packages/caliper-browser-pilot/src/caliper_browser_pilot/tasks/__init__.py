"""Browser-pilot task definitions.

The 12 v8 curated WebVoyager tasks land in two files:

- ``v8_baseline.py`` — exactly one ``@task``: the full 12-task baseline.
- ``v8_buckets.py``  — four ``@task``: one per bucket (lookup / search /
  compare / navigate). Use these for fast debug iteration on a single
  failure mode.

The split exists so ``inspect eval .../v8_baseline.py`` (without an
``@`` selector) runs exactly the baseline and not also the bucket
helpers, which would double-count samples. See the Codex M1.3 P2
fix for the rationale.

The 4 heroku smoke tasks land in ``smoke.py`` (M1.7a, Layer 1).
"""

from caliper_browser_pilot.tasks.smoke import heroku_smoke
from caliper_browser_pilot.tasks.v8_baseline import v8_baseline
from caliper_browser_pilot.tasks.v8_buckets import (
    v8_compare,
    v8_lookup,
    v8_navigate,
    v8_search,
)

__all__ = [
    "heroku_smoke",
    "v8_baseline",
    "v8_lookup",
    "v8_search",
    "v8_compare",
    "v8_navigate",
]
