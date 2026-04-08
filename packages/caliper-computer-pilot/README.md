# caliper-computer-pilot

Caliper adapter for [computer-pilot](https://github.com/relixiaobo/computer-pilot)
— the `cu` CLI tool for general macOS desktop automation.

**Status: Phase 3a skeleton.** This package is intentionally empty except
for module placeholders. Implementation lands in roadmap milestone M3a.

## Planned content

Mirrors `caliper-browser-pilot`'s structure with the cu-specific:

- `tools.py` — cu observation commands, snapshot formatter
- `solver.py` — `cu_agent()` factory wrapping the generic text-protocol solver
- `tasks/` — port computer-pilot's 3 existing agent test tasks

Same hard rule applies: never imports from any other `caliper-*` package.
