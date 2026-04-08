"""Text-protocol agent loop for CLI tools.

Wraps any subprocess-based CLI by extracting CLI command invocations
out of LLM free-text output. The agent doesn't use native function
calling — it just emits ``<cli> <subcommand> ...`` lines that this
loop extracts and executes via ``execve(2)`` directly (no shell).

This is the v0–v8 browser-pilot pattern, generalised. browser-pilot's
SKILL.md is built around the text protocol; we preserve it so SKILL.md
works unchanged. computer-pilot uses the same pattern with a different
``cli_name``. Any future CLI tool that follows the protocol works
without writing a new solver — only an adapter package providing
defaults and tool-specific output formatting.

Why a custom solver and not Inspect AI's ``basic_agent`` (which assumes
native tool calling): see ``docs/lessons-learned.md``.

State contract: this solver writes ``SolverState`` (see
``caliper.protocols``). Scorers read it. The contract is enforced by
type, not by string keys.

Security: command execution goes
``LLM text → extract_commands → ParsedCommand.argv → run_cli → execve(2)``.
Command strings never escape the parser module, so there is no path
from LLM output to a shell. See ``caliper.parsers.commands`` and
``caliper.runtime.subprocess`` for the other two pieces of this
guarantee.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageUser,
    get_model,
)
from inspect_ai.solver import Generate, Solver, TaskState, solver

from caliper.parsers import extract_answer, extract_commands
from caliper.protocols import SolverState
from caliper.runtime import run_cli


def _default_output_formatter(output: str, max_chars: int = 3000) -> str:
    """Generic output formatter — just caps length.

    Adapter packages override this with tool-specific formatters
    (e.g. ``caliper_browser_pilot.tools.bp_truncate_snapshot`` parses
    bp's JSON snapshot shape into compact text).
    """
    return output[:max_chars]


@solver
def text_protocol_agent(
    cli_name: str,
    observation_commands: Iterable[str],
    max_turns: int = 12,
    system_prompt_file: str | None = None,
    system_prompt: str | None = None,
    cli_timeout: float = 60.0,
    output_formatter: Callable[[str], str] | None = None,
) -> Solver:
    """Build a text-protocol agent loop solver.

    Args:
        cli_name: The CLI command name (e.g. ``"bp"``, ``"cu"``).
            Required — adapter packages provide their own factories
            with the right name baked in (e.g. ``bp_agent()``).
        observation_commands: Sub-command verbs that count as
            "observing the page" for lazy detection. Required — also
            no sensible default. Adapters bake in their tool-specific
            set.
        max_turns: Maximum LLM turns before forcing termination.
        system_prompt_file: Path to a SKILL.md / system-prompt file.
            Loaded once at solver build time.
        system_prompt: Inline system prompt (overrides
            ``system_prompt_file``).
        cli_timeout: Per-command subprocess timeout in seconds.
        output_formatter: Function applied to each subprocess output
            before it's added to the conversation. Defaults to a
            3000-char cap. Adapters pass tool-specific formatters here
            (e.g. JSON snapshot compactors).
    """
    obs_set = frozenset(observation_commands)
    fmt = output_formatter or _default_output_formatter

    if system_prompt is None and system_prompt_file is not None:
        system_prompt = Path(system_prompt_file).read_text()
    if system_prompt is None:
        system_prompt = (
            f"You are an agent that controls a CLI tool called `{cli_name}`. "
            "Emit one command per line prefixed with the tool name. "
            "When you have the final answer, write a line beginning with `ANSWER:`."
        )

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Typed state contract — single source of truth for solver↔scorer.
        ss = state.store_as(SolverState)
        ss.agent_answer = ""
        ss.observed_page = False
        ss.commands_run = 0

        # Auto-open start_url so the agent always sees an initial page.
        # No shell quoting needed — run_cli takes an argv list and
        # hands it straight to execve(2), so the URL is a literal
        # argument regardless of what metacharacters it contains.
        start_url = (state.metadata or {}).get("start_url")
        opening_observation = ""
        if start_url:
            raw = await run_cli(
                [cli_name, "open", start_url], timeout=cli_timeout
            )
            opening_observation = fmt(raw)

        # Reset the conversation: caliper's text-protocol loop owns it.
        state.messages = [ChatMessageSystem(content=system_prompt)]
        user_intro = f"Task: {state.input_text}"
        if opening_observation:
            user_intro += f"\n\nInitial page state:\n{opening_observation}"
        state.messages.append(ChatMessageUser(content=user_intro))

        model = get_model()

        for _turn in range(max_turns):
            result = await model.generate(state.messages)
            assistant_text = result.completion or ""
            state.messages.append(ChatMessageAssistant(content=assistant_text))
            state.output = result

            # Order matters: commands FIRST, answer SECOND.
            #
            # If the agent emitted both CLI commands and an ANSWER: line
            # in the same turn, the answer is based on hallucinated tool
            # output (the agent invented what the commands would
            # return). Executing the commands and feeding the real
            # output back forces the agent to revise its answer next
            # turn. This is what catches the M1.1 Cambridge smoke
            # regression.
            commands = extract_commands(assistant_text, cli_name)

            if commands:
                outputs: list[str] = []
                for cmd in commands:
                    if not cmd.ok:
                        outputs.append(f"$ {cmd.raw}\nERROR: {cmd.parse_error}")
                        continue
                    if cmd.subcommand in obs_set:
                        ss.observed_page = True
                    raw = await run_cli(list(cmd.argv), timeout=cli_timeout)
                    outputs.append(f"$ {cmd.raw}\n{fmt(raw)}")
                    ss.commands_run += 1
                state.messages.append(ChatMessageUser(content="\n\n".join(outputs)))
                continue

            # No commands this turn — accept ANSWER: as terminal.
            answer = extract_answer(assistant_text)
            if answer is not None:
                ss.agent_answer = answer
                state.completed = True
                return state

            # No answer, no commands — nudge once and continue.
            state.messages.append(
                ChatMessageUser(
                    content=(
                        f"You did not emit a `{cli_name} ...` command or an "
                        "`ANSWER:` line. Either run a command or write "
                        "`ANSWER: ...`."
                    )
                )
            )

        # Hit the turn limit without an answer.
        return state

    return solve
