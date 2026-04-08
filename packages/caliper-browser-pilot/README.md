# caliper-browser-pilot

Caliper adapter for [browser-pilot](https://github.com/relixiaobo/browser-pilot)
— the `bp` CLI tool that drives a real Chrome browser via the text protocol.

This package provides the bp-specific bits that don't belong in caliper
core: the observation-command set, the snapshot text formatter (which
parses bp's specific JSON shape), the SKILL.md path resolver, and a
`bp_agent()` factory that wires everything together with sensible defaults.

The 12 v8 baseline tasks and the 4 heroku smoke tasks live in `tasks/`
and are populated in M1.3 / M1.7 of the roadmap.

## Quick use

```python
from caliper_browser_pilot import bp_agent
from caliper.scorers import judge_stale_ref, lazy_detection
from inspect_ai import Task, task
from inspect_ai.dataset import Sample

@task
def my_browser_task() -> Task:
    return Task(
        dataset=[Sample(input="...", target="...", metadata={"start_url": "..."})],
        solver=bp_agent(max_turns=12),
        scorer=[judge_stale_ref(), lazy_detection()],
    )
```

## What does NOT live here

Anything that isn't bp-specific. Generic parsers, the text-protocol agent
loop, the judge prompt — those live in `caliper` core.

**Hard rule:** `caliper-browser-pilot` never imports from `caliper-chatbot`
or `caliper-computer-pilot`. Adapters are siblings; they don't depend on
each other.
