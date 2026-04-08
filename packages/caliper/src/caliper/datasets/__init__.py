"""Dataset loaders for public benchmarks.

caliper core provides loaders only — never task data. Bundled task
data creates license/attribution issues (test-sets.md principle 5)
and forces caliper to track upstream changes. Loaders read whatever
JSONL/JSON the benchmark publishes and produce Inspect AI ``Sample``
objects with caliper-standard metadata (validated against
``caliper.protocols.validate_task_metadata``).

Currently exports the WebVoyager loader. AssistantBench / GAIA /
Mind2Web loaders land in later phases as needed.
"""

from caliper.datasets.webvoyager import filter_by_bucket, load_webvoyager_jsonl

__all__ = ["load_webvoyager_jsonl", "filter_by_bucket"]
