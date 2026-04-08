"""Shell-aware helper for multi-line command detection.

``is_unterminated_shell(line)`` uses ``shlex`` to detect a line that
is not a complete shell command — specifically, one with an unterminated
quoted argument that legitimately spans multiple lines, as in
``bp eval 'function() {``. ``extract_commands`` uses it to decide
whether to keep collecting continuation lines.

The shlex-based detection replaces an earlier "count quotes, odd ⇒
multiline" heuristic that produced false positives on commands like
``bp type 7 "Don't"`` (apostrophe inside double quotes). See
docs/reference/inherited-artifacts.md §4 for the original algorithm and
``packages/caliper/tests/unit/test_text_protocol_parsers.py`` for the
regression test that locks the fix in.
"""

from __future__ import annotations

import shlex


def is_unterminated_shell(line: str) -> tuple[bool, str | None]:
    """Return ``(unterminated, opening_quote_char)``.

    If the line parses cleanly as a posix shell command, returns
    ``(False, None)``. If it raises a "No closing quotation" error,
    walks the line manually to determine which quote (``'`` or ``"``)
    is open and returns ``(True, that_char)``.
    """
    try:
        shlex.split(line, posix=True)
        return False, None
    except ValueError:
        in_single = False
        in_double = False
        escape = False
        for ch in line:
            if escape:
                escape = False
                continue
            if ch == "\\" and not in_single:
                escape = True
                continue
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
        if in_single:
            return True, "'"
        if in_double:
            return True, '"'
        return True, None
