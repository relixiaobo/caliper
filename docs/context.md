# Operational Context

This document tells a new contributor (human or AI) **everything they
need to know about the world this project lives in** to start being
productive immediately. It complements the narrative docs (`why.md`,
`methodology.md`, `architecture.md`) by answering the question: "where
is everything, and what do I need installed?"

If you're picking up caliper for the first time, **read this first**,
then read `roadmap.md` to find the next milestone.

---

## Project state (as of initial commit)

- **Phase**: 0 — Documentation scaffolding complete. No Python code yet.
- **Next milestone**: M1.1 in `roadmap.md` (set up Inspect AI, port one
  task end-to-end).
- **Pre-existing code being migrated**: `~/Documents/Coding/browser-pilot/tests/agent/`
  (a 670-line Python runner that this project is replacing).

---

## Related repositories

Caliper is the framework. The things it tests / will test live in other
repositories on the same machine:

| Repo | Path | Language | Role | Status |
|---|---|---|---|---|
| **caliper** | `~/Documents/Coding/caliper/` | Python | This project — the framework | Phase 0 (current) |
| **browser-pilot** | `~/Documents/Coding/browser-pilot/` | TypeScript (CLI) + Python (tests) | First consumer; the source of all v0–v8 lessons | Active, has v8 baseline |
| **computer-pilot** | `~/Documents/Coding/computer-pilot/` | Rust | Future second consumer | Has its own `tests/agent/` to migrate |
| **eval-pilot** | `~/Documents/Coding/eval-pilot/` | Python | Pre-existing eval framework (different scope, not competing) | N/A — taken namespace, that's why our package is `caliper` not `eval-pilot` |

---

## Files in browser-pilot that you will need

Phase 1 of caliper is "migrate browser-pilot's existing eval to caliper".
These are the files you will read, port, or reference:

| File | What it contains | Why you care |
|---|---|---|
| `browser-pilot/tests/agent/run.py` | The 670-line agent benchmark runner — the thing being replaced | Source of judge prompt, lazy detection, parser, cost concepts |
| `browser-pilot/tests/agent/v7_baseline.py` | The 12-task bucketed runner | Source of the curated task list and baseline structure |
| `browser-pilot/tests/agent/data/WebVoyager_data.jsonl` | 643 WebVoyager tasks | Source dataset; load with `caliper.datasets.webvoyager_loader` |
| `browser-pilot/tests/agent/data/reference_answer.json` | Reference answers for WebVoyager | Used by the judge scorer |
| `browser-pilot/tests/agent/tasks/*.json` | 4 hand-written heroku tasks | Smoke tests independent of WebVoyager |
| `browser-pilot/plugin/skills/browser-pilot/SKILL.md` | The system prompt for the bp agent | Loaded as the system prompt for any caliper task that uses the `bp` text protocol solver |
| `browser-pilot/test-results/agent-*.json` | ~50 historical run results from v0 through v8 | Historical baselines for cross-checking caliper's port |
| `browser-pilot/.env` | API keys | `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are here; copy to `~/Documents/Coding/caliper/.env` |
| `browser-pilot/dist/cli.js` | The compiled `bp` CLI binary | Has to be on `$PATH` (via `npm install -g browser-pilot-cli` or `npm link` from the source) |

The verbatim contents of the most important port artifacts are in
`docs/reference/` so you don't have to re-derive them.

---

## Environment setup

### Required

- **Python 3.11+** (Inspect AI requires 3.10+; we standardize on 3.11)
- **uv** for Python package management
  ```bash
  brew install uv  # macOS
  ```
- **bp CLI** installed and on `$PATH`
  ```bash
  npm install -g browser-pilot-cli
  # or, for development against your local browser-pilot:
  cd ~/Documents/Coding/browser-pilot && npm link
  ```
- **Chrome with remote debugging enabled**
  - Open `chrome://inspect/#remote-debugging` and toggle ON
  - Run `bp connect` once per session (Chrome will show an "Allow" dialog)
- **API keys** in `~/Documents/Coding/caliper/.env`
  ```bash
  cp ~/Documents/Coding/browser-pilot/.env ~/Documents/Coding/caliper/.env
  ```
  The file should contain at minimum:
  ```
  ANTHROPIC_API_KEY=sk-ant-...
  OPENAI_API_KEY=sk-proj-...
  ```

### Verifying the setup

```bash
# 1. bp CLI works and Chrome is reachable
bp tabs
# Expected: {"ok":true,"tabs":[...]}

# 2. Python and uv ready
python3 --version  # 3.11+
uv --version

# 3. API keys loaded
python3 -c "import os; from pathlib import Path; \
  [os.environ.setdefault(k.strip(), v.strip()) for line in Path('.env').read_text().splitlines() \
   if (line := line.strip()) and not line.startswith('#') and '=' in line \
   for k, _, v in [line.partition('=')]]; \
  print('anthropic key:', 'set' if os.environ.get('ANTHROPIC_API_KEY') else 'MISSING'); \
  print('openai key:', 'set' if os.environ.get('OPENAI_API_KEY') else 'MISSING')"
```

If all three pass, you're ready to start Phase 1.

---

## What you should NOT touch in browser-pilot

When migrating, **do not modify** browser-pilot's main source tree:

- ❌ `browser-pilot/src/` — the bp CLI implementation (TypeScript)
- ❌ `browser-pilot/dist/` — compiled output
- ❌ `browser-pilot/package.json`
- ❌ `browser-pilot/plugin/skills/browser-pilot/SKILL.md` — read it, don't edit it (unless you're testing a SKILL.md change as a deliberate experiment)

You **may** modify browser-pilot's eval directory:

- ✅ `browser-pilot/tests/agent/` — eventually this becomes a thin shim
  pointing at caliper-based tasks. During Phase 1 you can leave it alone
  and add caliper tasks alongside; in M1.7 you replace it.

---

## What you should NOT touch in caliper itself

- The `docs/` narrative files (`why`, `methodology`, `architecture`,
  `test-sets`, `self-evaluation`, `lessons-learned`, `chatbot-maxturns`)
  describe the design philosophy. Edit them only if you're updating the
  design itself, not when porting code.
- The `docs/reference/` files are verbatim port artifacts from
  browser-pilot — `inherited-artifacts.md` is especially load-bearing.
  Don't "improve" the prompts/parsers/sets in there without re-running
  the relevant self-eval suite.
- The `LICENSE` is MIT and shouldn't change.
- The root `pyproject.toml` is the uv workspace declaration. Add new
  workspace members under `[tool.uv.sources]`, don't move it around.
- The hard rule from `architecture.md`: `caliper` core never imports
  from any `caliper-*` adapter package, and adapters never import from
  each other. If you find yourself wanting to break this rule, the
  right move is usually to define a new abstraction in
  `caliper.protocols` or `caliper.{scorers,solvers}`.

---

## Workspace layout (post Phase R)

Caliper is a uv workspace with four sibling Python packages. Full
contract is in [`architecture.md`](architecture.md#workspace-layout--single-git-repo-multiple-python-packages);
this section is the file pointers a contributor needs day-to-day.

```
caliper/                              # git repo, single venv
├── pyproject.toml                    # uv workspace declaration
├── packages/
│   ├── caliper/                      # ★ core (~600 lines, ceiling 800)
│   │   └── src/caliper/
│   │       ├── protocols.py          # SolverState, Strategy, validate_task_metadata
│   │       ├── parsers/{shell,commands,answer}.py
│   │       ├── runtime/{subprocess,env}.py
│   │       ├── solvers/text_protocol.py    # generic CLI text-protocol agent
│   │       ├── scorers/{json_verdict,judge_stale_ref,lazy_detection,multi_dim}.py
│   │       ├── strategies/__init__.py     # Strategy Protocol class only
│   │       ├── mocks/                     # framework infra (Phase 3)
│   │       ├── metrics/                   # cost + pricing (M1.2)
│   │       ├── report/                    # bucket + ab (M1.4 / M1.5)
│   │       └── datasets/                  # generic loaders (M1.3)
│   │   └── tests/unit/                    # 42 tests, all green
│   │
│   ├── caliper-browser-pilot/        # bp adapter
│   │   └── src/caliper_browser_pilot/
│   │       ├── tools.py              # BP_OBSERVATION_COMMANDS, bp_truncate_snapshot, bp_skill_path
│   │       ├── solver.py             # bp_agent() factory
│   │       └── tasks/                # 12 v8 tasks (M1.3) + 4 heroku (M1.7)
│   │
│   ├── caliper-computer-pilot/       # cu adapter (Phase 3a skeleton)
│   └── caliper-chatbot/              # chatbot scenario (Phase 3b skeleton)
│
├── examples/
│   ├── quickstart.py                 # 30-second on-ramp
│   └── cambridge_smoke.py            # M1.1 example, lives here permanently
│
├── baselines/                        # v9.json lands in M1.6
└── docs/                             # all narrative + reference docs
```

`logs/` and `.venv/` are auto-created and gitignored.

### Where to put a new task

1. **Same shape as bp / cu** → drop a `Sample(...)` in
   `packages/caliper-<adapter>/src/caliper_<adapter>/tasks/`
2. **New shape (different agent loop)** → new sibling package under
   `packages/`, mirroring `caliper-browser-pilot`'s structure
3. **Generic to all adapters (judge, parser, etc.)** → only after the
   rule of three; see `architecture.md` "promotion to core"

---

## How to run Inspect AI (cheat sheet)

Once `uv add inspect-ai` is done in M1.1:

```bash
# Run a task definition
inspect eval examples/cambridge_smoke.py --model anthropic/claude-sonnet-4-6

# Run with N=2 (matches caliper's enforced default)
inspect eval examples/cambridge_smoke.py --model anthropic/claude-sonnet-4-6 --epochs 2

# Open the web viewer for traces (auto-detects ./logs/)
inspect view

# Run multiple tasks
inspect eval examples/browser_pilot_v8/tasks.py --epochs 2

# Filter to specific task in a file
inspect eval examples/browser_pilot_v8/tasks.py@browser_pilot_v9 --epochs 2
```

Inspect AI's full docs: https://inspect.aisi.org.uk/

---

## How to verify your Phase 1 port works

The goal is "match v8 baseline within 95% CI". The v8 numbers you should
hit (when running on Sonnet, N=2 → 24 samples per task):

| Bucket | Pass rate target |
|---|---|
| lookup | 6/6 |
| search | 6/6 |
| compare | 5/6 (one Sonnet failure on Apple--3 is expected) |
| navigate | 6/6 |
| **Total** | **23/24 (96%)** |

Full baseline numbers (per task) are in `docs/reference/baseline-v8.md`.

If your caliper port matches these within 1 sample, the port is
validated. If it deviates by more than 1 sample, debug the difference
against the saved logs in `browser-pilot/test-results/`.

---

## Open questions left for whoever picks this up

- Should `caliper` be the PyPI package name (it might be taken)? Phase
  4 decision.
- Should the chatbot maxTurns scenario be Phase 3 or a separate
  Phase 3.5? Depends on whether computer-pilot port comes first.
- How aggressive should the Inspect AI version pin be? Suggest
  `inspect-ai>=0.3,<0.4` until we hit a real version constraint.

---

## Who has touched this repository

The initial commit was a single docs-only commit by the original author
(see `git log`). Phase 1+ contributors should add themselves here when
they make significant contributions, so future contributors know who to
ask about specific decisions.
