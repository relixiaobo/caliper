"""Dataset loaders for public benchmarks — placeholder for M1.3.

caliper core provides loaders only — never task data. Bundled task data
creates license/attribution issues (test-sets.md principle 5) and forces
caliper to track upstream changes. Loaders read whatever JSONL/JSON the
benchmark publishes and produce Inspect AI ``Sample`` objects with
caliper-standard metadata (validated against
``caliper.protocols.validate_task_metadata``).

Planned modules (M1.3 and later):
    webvoyager.py     — load WebVoyager_data.jsonl
    assistantbench.py — load AssistantBench
    gaia.py           — load GAIA
    mind2web.py       — Online-Mind2Web

The actual data files live in adapter packages (e.g. browser-pilot's
v8 curated subset of WebVoyager lives in
``caliper-browser-pilot/data/v8_curated.jsonl``).
"""
