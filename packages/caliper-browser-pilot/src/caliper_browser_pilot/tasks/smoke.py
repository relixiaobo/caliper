"""Layer 1 smoke tasks against ``the-internet.herokuapp.com``.

Four deterministic hand-written tasks intended to run on every commit
in CI. These are the "is anything on fire?" check — they don't
measure agent capability across a broad matrix, they catch regressions
in the solver/tool plumbing (bp parser, subprocess runner, prologue,
scorer wiring) that would make the v8 baseline silently broken.

## Why these 4 tasks

Ported verbatim from
``~/Documents/Coding/browser-pilot/tests/agent/tasks/heroku_*.json``,
the original v0 smoke set from before caliper existed. Each covers a
distinct interaction primitive:

- ``heroku-checkboxes``    — click + DOM state read (input[checked])
- ``heroku-dropdown``      — form option selection
- ``heroku-dynamic-loading`` — click + wait + delayed content read
- ``heroku-login``         — form fill + submit + navigation check

The target site is ``the-internet.herokuapp.com``, chosen because it
is explicitly designed for test automation, is stable across time
(no v8-style stale-reference drift), and is small/fast (<1 s per
page).

## Scoring

Unlike v8 baseline tasks, these use ``verify_commands`` for
deterministic post-hoc checking instead of ``judge_stale_ref``. The
pass condition for each task is a simple DOM query + expected
substring, so an LLM judge would only add variance, latency, and
cost. The smoke tier is supposed to be **fast and free** so it can
run on every commit without burning through the API budget.

## Layering relative to v8

This is Layer 1 per ``docs/test-sets.md``:

- **Layer 1 — smoke** (this file): deterministic post-hoc verification,
  runs on every commit, ~30s total, catches tool/solver breakage.
- **Layer 2 — curated baseline** (``v8_baseline.py``): LLM judge,
  runs on milestone boundaries, ~30-60 min, catches capability
  regressions.
- **Layer 3 — broad coverage** (Phase 2): full WebVoyager set, runs
  quarterly, measures statistical performance.

Smoke tasks intentionally do NOT overlap with the v8 set — if both
are broken, the smoke failure pinpoints the issue before the long
v8 run would have finished.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import Solver

from caliper.runtime import load_dotenv
from caliper.scorers import verify_commands

from caliper_browser_pilot.solver import bp_agent

# Keep API credentials available when the task constructs its solver,
# but these smoke tasks are scored without an LLM judge so they can
# also run with no API key at all if ``bp_agent`` is swapped out.
load_dotenv()


# ---------------------------------------------------------------------------
# The 4 heroku smoke samples
# ---------------------------------------------------------------------------
#
# These are literal ``Sample`` constructions rather than a JSONL file.
# With only 4 tasks, a JSONL + loader layer would be overhead for no
# benefit. The 4 records below are the single source of truth; there
# is no separate data file to keep in sync.


def _heroku_samples() -> list[Sample]:
    """Return the 4 hand-written smoke samples.

    Every sample carries:
        ``input``    — the agent-visible task description
        ``target``   — a human-readable pass condition (NOT used by
                       verify_commands, but surfaced in Inspect AI's
                       UI and in the bucket report)
        ``metadata.bucket``       — always ``"smoke"``
        ``metadata.source``       — ``"the-internet.herokuapp.com"``
        ``metadata.start_url``    — entry URL for ``bp open``
        ``metadata.verify``       — list of deterministic checks read
                                    by ``verify_commands``

    Kept as a factory function (not a module-level constant) so
    ``Sample`` construction runs at task-build time, not at import
    time. This matters because ``Sample`` may do validation of its
    arguments and we don't want import-time side effects in a file
    that gets discovered by ``inspect eval``.
    """
    return [
        Sample(
            id="heroku-checkboxes",
            input=(
                "Navigate to the checkboxes page and make sure both "
                "checkboxes are checked."
            ),
            target="Both checkboxes on the page are checked.",
            metadata={
                "bucket": "smoke",
                "source": "the-internet.herokuapp.com",
                "start_url": "https://the-internet.herokuapp.com/checkboxes",
                "verify": [
                    {
                        "description": "Both checkboxes are checked",
                        "command": [
                            "bp",
                            "eval",
                            "document.querySelectorAll('#checkboxes input:checked').length.toString()",
                        ],
                        "expect_contains": "2",
                    },
                ],
            },
        ),
        Sample(
            id="heroku-dropdown",
            input=(
                "Navigate to the dropdown page and select 'Option 2' "
                "from the dropdown menu."
            ),
            target="The dropdown has 'Option 2' selected (value='2').",
            metadata={
                "bucket": "smoke",
                "source": "the-internet.herokuapp.com",
                "start_url": "https://the-internet.herokuapp.com/dropdown",
                "verify": [
                    {
                        "description": "Option 2 is selected",
                        "command": [
                            "bp",
                            "eval",
                            "document.querySelector('#dropdown').value",
                        ],
                        "expect_contains": "2",
                    },
                ],
            },
        ),
        Sample(
            id="heroku-dynamic-loading",
            input=(
                "Navigate to the dynamic loading page (Example 1: "
                "hidden element), click the Start button, wait for "
                "the loading to finish, and read the text that appears."
            ),
            target="The hidden element shows 'Hello World!' after loading.",
            metadata={
                "bucket": "smoke",
                "source": "the-internet.herokuapp.com",
                "start_url": "https://the-internet.herokuapp.com/dynamic_loading/1",
                "verify": [
                    # The #finish h4 element exists in the DOM from the
                    # initial page load — only its parent #finish has
                    # display:none until the click+wait completes. A
                    # naive textContent check therefore passes on a
                    # no-op agent that never clicked Start (caught by
                    # Codex review of the M1.7a commit). Gate on
                    # visibility first, then return the text.
                    {
                        "description": "Hidden text is now visible",
                        "command": [
                            "bp",
                            "eval",
                            (
                                "window.getComputedStyle("
                                "document.querySelector('#finish')"
                                ").display === 'none' ? 'HIDDEN' : "
                                "document.querySelector('#finish h4')"
                                ".textContent.trim()"
                            ),
                        ],
                        "expect_contains": "Hello World!",
                    },
                ],
            },
        ),
        Sample(
            id="heroku-login",
            input=(
                "Navigate to the login page, enter username 'tomsmith' "
                "and password 'SuperSecretPassword!', then click the "
                "Login button."
            ),
            target="Logged in — success message shown and URL is /secure.",
            metadata={
                "bucket": "smoke",
                "source": "the-internet.herokuapp.com",
                "start_url": "https://the-internet.herokuapp.com/login",
                "verify": [
                    {
                        "description": "Success message is displayed",
                        "command": [
                            "bp",
                            "eval",
                            "document.querySelector('.flash.success')?.textContent?.trim()",
                        ],
                        "expect_contains": "You logged into a secure area!",
                    },
                    {
                        "description": "URL changed to /secure",
                        "command": [
                            "bp",
                            "eval",
                            "location.pathname",
                        ],
                        "expect_contains": "/secure",
                    },
                ],
            },
        ),
    ]


def heroku_smoke_dataset() -> MemoryDataset:
    """Build the smoke dataset. Exposed as a public helper so tests
    can import it without spinning up an Inspect AI ``Task``."""
    return MemoryDataset(
        samples=_heroku_samples(),
        name="heroku_smoke",
    )


# ---------------------------------------------------------------------------
# Public @task definition
# ---------------------------------------------------------------------------


@task
def heroku_smoke(
    max_turns: int = 10,
    solver: Solver | None = None,
) -> Task:
    """4 deterministic heroku smoke tasks, scored via verify_commands.

    **IMPORTANT — must be run with ``--max-samples 1``.** This task
    inherits ``bp_agent()``'s default session prologue, which is
    documented as serial-only (see
    ``caliper_browser_pilot.solver.BP_DEFAULT_SESSION_PROLOGUE``).
    More fundamentally, ``bp`` itself is a process-global singleton
    attached to the user's real Chrome — two concurrent bp samples
    would race on the "active tab" state even *without* the
    prologue. There is currently no parallel-safe bp story.

    Run:

    .. code-block:: shell

        inspect eval .../tasks/smoke.py@heroku_smoke \\
            --model anthropic/claude-sonnet-4-6 \\
            --max-samples 1

    Running without ``--max-samples 1`` will produce
    nondeterministic failures that look like random bp/Chrome bugs
    but are actually a parallelism-vs-bp mismatch. This is tracked
    as a known limitation in ``docs/lessons-learned.md``'s M1.6b
    section.

    Args:
        max_turns: Agent loop turn cap. Defaults to 10 — these tasks
            should all complete in 2-4 turns. 10 is a generous ceiling
            that still keeps a runaway agent from burning tokens.
        solver: Override the solver entirely. Useful for A/B
            comparisons across ``bp_agent`` configurations (e.g.
            different prologues, different system prompts). Defaults
            to ``bp_agent()`` with the standard per-sample session
            prologue. If you need a parallel-safe variant, pass
            ``bp_agent(session_prologue=[])`` — but note that
            without the prologue the CHROME_TAB_POLLUTION guard is
            gone and bp is still not concurrency-safe at the
            active-tab level.

    Judging: this task does NOT use an LLM judge. It uses
    ``verify_commands`` which runs the deterministic post-hoc checks
    listed in each sample's ``metadata["verify"]`` via ``run_cli``,
    and also asserts the agent produced a non-empty ``ANSWER:``
    block. That means the smoke tier can run on machines with no
    model API credentials — only a working bp + Chrome connection
    is required.
    """
    return Task(
        dataset=heroku_smoke_dataset(),
        solver=solver or bp_agent(max_turns=max_turns),
        scorer=verify_commands(),
    )
