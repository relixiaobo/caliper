"""Extract CLI command invocations from LLM free-text output.

Returns ``ParsedCommand`` instances — structures that carry both the
**exec-ready argv list** and the original raw text (for display in the
conversation echo). Crucially, the argv list is produced by this
module via ``shlex.split`` and passed directly to
``caliper.runtime.subprocess.run_cli``, which uses
``create_subprocess_exec`` to go straight to ``execve(2)``. No shell
interpretation happens anywhere along the path.

This is the argv-first design. An earlier version returned ``list[str]``
and the solver re-parsed the strings before execution. That meant
"command strings" existed as an intermediate representation past the
parser boundary, and Codex's review of the Phase R restructure flagged
the result as a P1: a model emitting ``bp read; rm -rf ~`` would have
its string passed to ``/bin/sh`` for parsing. The fix is structural —
strings never leave this module, only argv lists do, and argv lists
are always fed to ``execve`` directly.

See also ``packages/caliper/tests/unit/test_runtime_subprocess.py`` for
the P1 regression test on the execution side.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from caliper.parsers.shell import is_unterminated_shell


@dataclass(frozen=True)
class ParsedCommand:
    """A CLI command extracted from LLM text, ready to execute.

    Either ``argv`` is non-empty with ``argv[0] == cli_prefix`` (in
    which case ``parse_error is None``), or ``argv`` is empty and
    ``parse_error`` describes why the command couldn't be parsed. The
    solver displays ``raw`` in the conversation echo regardless.
    """

    argv: tuple[str, ...]
    raw: str
    parse_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.parse_error is None

    @property
    def subcommand(self) -> str:
        """The sub-command word, e.g. ``"open"`` for ``"bp open ..."``.

        Empty string if the command has no sub-command (``bp`` alone)
        or failed to parse.
        """
        return self.argv[1] if len(self.argv) >= 2 else ""


def extract_commands(text: str, cli_prefix: str) -> list[ParsedCommand]:
    """Extract ``<cli_prefix> ...`` invocations from LLM free text.

    Walks the text line by line. A line is a candidate command iff,
    after stripping whitespace and surrounding backticks, it starts
    with ``cli_prefix + " "``. If the candidate line is an unterminated
    quoted string (e.g. a multi-line ``bp eval '...'`` script), this
    function greedily consumes subsequent lines until the matching
    quote closes, then ``shlex.split``s the assembled text.

    The returned list preserves the source order of commands and
    includes both successful parses and failures — see ``ParsedCommand.ok``.
    """
    prefix_with_space = cli_prefix + " "
    commands: list[ParsedCommand] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip().strip("`")
        if line.startswith(prefix_with_space):
            raw = _collect_raw(lines, i, line)
            # Advance i past any consumed continuation lines.
            i += 1 + _continuation_count(raw, line)
            commands.append(_parse_one(raw, cli_prefix))
            continue
        i += 1
    return commands


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _collect_raw(lines: list[str], i: int, first_line: str) -> str:
    """Assemble the full raw text of a command, greedily extending
    across continuation lines until the assembled buffer parses as a
    complete shell command.

    The stopping condition is delegated to ``is_unterminated_shell``,
    which uses ``shlex`` under the hood. This is the single source of
    truth for "is this command complete": shlex already understands
    posix shell quoting rules — backslash escapes inside double
    quotes, literal apostrophes inside double quotes, escaped
    newlines, etc. An earlier version of this function did its own
    naive ``if quote_char in next_line: break`` check, which
    mis-handled escaped quotes (Codex Phase R P2 finding).

    If the assembled buffer is still unterminated at end-of-input
    (because the agent emitted a malformed unterminated argument),
    we return what we've collected and let ``_parse_one`` surface the
    ``shlex.split`` failure as a ``ParsedCommand.parse_error``.
    """
    if not is_unterminated_shell(first_line)[0]:
        return first_line

    buf = [first_line]
    j = i + 1
    while j < len(lines):
        next_line = lines[j].rstrip()
        if next_line.strip().startswith("`"):
            next_line = next_line.strip().strip("`")
        buf.append(next_line)
        j += 1
        if not is_unterminated_shell("\n".join(buf))[0]:
            break
    return "\n".join(buf)


def _continuation_count(raw: str, first_line: str) -> int:
    """How many extra lines were consumed after ``first_line``."""
    if raw == first_line:
        return 0
    # raw = first_line + "\n" + line2 + "\n" + ... + lineN. The number
    # of "\n" separators equals the number of continuation lines.
    return raw.count("\n")


def _parse_one(raw: str, cli_prefix: str) -> ParsedCommand:
    """Shlex-parse an assembled command string into a ParsedCommand.

    The caller has already verified ``raw`` starts with
    ``cli_prefix + " "`` after stripping backticks/whitespace on the
    first line, so under normal input the first element of the
    parsed argv is exactly ``cli_prefix``. We still defend against
    pathological inputs (e.g. an agent that closes a quoted argument
    one line too late, producing text the shlex would read as
    splitting the prefix itself).
    """
    try:
        argv = tuple(shlex.split(raw, posix=True))
    except ValueError as exc:
        return ParsedCommand(argv=(), raw=raw, parse_error=f"shlex: {exc}")
    if not argv:
        return ParsedCommand(argv=(), raw=raw, parse_error="empty after parsing")
    if argv[0] != cli_prefix:
        # Should be unreachable under normal input, but we refuse to
        # execute anything whose argv[0] doesn't match the expected CLI.
        return ParsedCommand(
            argv=(),
            raw=raw,
            parse_error=f"refusing non-{cli_prefix!r} command: argv[0]={argv[0]!r}",
        )
    return ParsedCommand(argv=argv, raw=raw, parse_error=None)
