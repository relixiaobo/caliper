"""Tests for the shell-aware multi-line detector used by extract_commands."""

from caliper.parsers.shell import is_unterminated_shell


def test_complete_simple_command():
    assert is_unterminated_shell("bp open https://example.com") == (False, None)


def test_complete_double_quoted_with_apostrophe():
    """The Codex M1.1 regression in shell-detection form: this MUST
    be detected as complete (not unterminated)."""
    unterminated, char = is_unterminated_shell('bp type 7 "Don\'t"')
    assert unterminated is False
    assert char is None


def test_unterminated_single_quote():
    unterminated, char = is_unterminated_shell("bp eval 'function() {")
    assert unterminated is True
    assert char == "'"


def test_unterminated_double_quote():
    unterminated, char = is_unterminated_shell('bp eval "function() {')
    assert unterminated is True
    assert char == '"'


def test_escaped_quote_does_not_open():
    """Backslash-escaped quotes don't open a quoted span."""
    # bp eval "hello \"world\"" — fully terminated
    unterminated, _ = is_unterminated_shell(r'bp eval "hello \"world\""')
    assert unterminated is False
