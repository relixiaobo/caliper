"""Generic text parsers used by solvers.

These are pure functions over strings. They have no agent-loop state,
no subprocess calls, no LLM calls. They are unit-testable in isolation
and the most heavily-tested code in caliper core (see
``packages/caliper/tests/unit/test_text_protocol_parsers.py`` and
``test_runtime_subprocess.py``).

The ``extract_commands`` parser returns ``ParsedCommand`` instances
carrying exec-ready argv lists — no "command string" representation
leaks past the parser boundary. This is the structural P1 fix for
shell injection: ``caliper.runtime.subprocess.run_cli`` accepts argv
lists only, and this module is the single place argv lists are
produced.

Verbatim sources for the algorithms: ``docs/reference/inherited-artifacts.md``
sections 4 (extract_commands) and 5 (extract_answer). The argv-first
redesign is a post-Phase-R correction driven by Codex review.
"""

from caliper.parsers.answer import extract_answer
from caliper.parsers.commands import ParsedCommand, extract_commands
from caliper.parsers.shell import is_unterminated_shell

__all__ = [
    "ParsedCommand",
    "extract_answer",
    "extract_commands",
    "is_unterminated_shell",
]
