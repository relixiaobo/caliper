"""Unit tests for the text-protocol parsers.

Two responsibilities:

1. ``extract_commands(text, cli_prefix)`` — pulls ``<prefix> ...``
   command invocations out of LLM free text and returns
   ``ParsedCommand`` instances carrying exec-ready argv lists.
2. ``extract_answer(text)`` — pulls the ``ANSWER:`` block out of the
   last assistant message.

The first one is security-critical: its output is passed **directly**
to ``execve(2)`` via ``caliper.runtime.subprocess.run_cli``. No shell
interpretation happens anywhere along the path, so command strings
must never leak past this module. This file locks that contract.

Regression history:

- ``test_extract_apostrophe_in_double_quotes_REGRESSION`` — Codex
  review of M1.1 caught an "odd quote count ⇒ multiline" heuristic
  that false-positived on ``bp type 7 "Don't"``.
- ``test_exec_ready_argv_defeats_shell_injection`` — Codex review of
  Phase R caught that the earlier ``list[str]`` return type was being
  re-parsed by the solver and still allowed the injected-semicolon
  path. The fix is the argv-first design: the parser owns the shlex
  split, and downstream code gets argv lists only.
"""

from caliper.parsers import extract_answer, extract_commands

# ---------------------------------------------------------------------------
# Cases from inherited-artifacts.md §4 — must keep passing.
# ---------------------------------------------------------------------------


def test_extract_simple():
    cmds = extract_commands("bp open https://example.com", "bp")
    assert len(cmds) == 1
    assert cmds[0].ok
    assert cmds[0].argv == ("bp", "open", "https://example.com")
    assert cmds[0].raw == "bp open https://example.com"


def test_extract_multiple_per_response():
    text = """Let me do this:
bp open https://example.com
bp read
"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 2
    assert cmds[0].argv == ("bp", "open", "https://example.com")
    assert cmds[1].argv == ("bp", "read")


def test_extract_multiline_eval_single_quotes():
    text = """bp eval 'function() {
  return 42;
}'"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert cmds[0].ok
    # The entire eval script is argv[2] — a single argument to bp,
    # because shlex.split consumed the quoted block as one token.
    assert cmds[0].argv[0] == "bp"
    assert cmds[0].argv[1] == "eval"
    assert "function" in cmds[0].argv[2]
    assert "return 42" in cmds[0].argv[2]


def test_extract_strips_backticks():
    text = "`bp open https://example.com`"
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert cmds[0].argv == ("bp", "open", "https://example.com")


# ---------------------------------------------------------------------------
# Codex M1.1 regression: apostrophe inside double quotes.
# ---------------------------------------------------------------------------


def test_extract_apostrophe_in_double_quotes_REGRESSION():
    """REGRESSION TEST for the Codex M1.1 finding.

    A line like ``bp type 7 "Don't"`` is a complete, valid shell
    command. The original parser counted single quotes, found 1 (odd),
    entered the multi-line path, and consumed every following command
    line into one merged command — silently dropping later commands.
    """
    text = """bp type 7 "Don't"
bp click 9
bp read"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 3, f"expected 3 separate commands, got {cmds!r}"
    assert cmds[0].argv == ("bp", "type", "7", "Don't")
    assert cmds[1].argv == ("bp", "click", "9")
    assert cmds[2].argv == ("bp", "read")


def test_extract_apostrophe_inside_double_quoted_url():
    """Same class of bug, slightly different shape."""
    text = """bp open "https://example.com/it's-fine"
bp read"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 2
    assert cmds[0].argv == ("bp", "open", "https://example.com/it's-fine")
    assert cmds[1].argv == ("bp", "read")


def test_extract_legit_multiline_eval_still_works():
    text = """bp eval 'const x = {
  a: 1,
  b: 2
};
return x.a + x.b'
bp read"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 2
    assert "const x" in cmds[0].argv[2]
    assert "return x.a" in cmds[0].argv[2]
    assert cmds[1].argv == ("bp", "read")


def test_extract_multiline_double_quotes():
    text = '''bp eval "function() {
  return 'hello';
}"'''
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert "function" in cmds[0].argv[2]
    assert "return 'hello'" in cmds[0].argv[2]


# ---------------------------------------------------------------------------
# Codex Phase R P2 regression: escaped quote inside multi-line block.
# ---------------------------------------------------------------------------


def test_multiline_double_quoted_with_escaped_quotes_REGRESSION():
    """REGRESSION TEST for the Codex Phase R P2 finding.

    The original multi-line collector stopped as soon as it saw the
    opening quote character appear on any subsequent line, ignoring
    backslash-escaped occurrences. For a legitimate script like:

        bp eval "function() {
          console.log(\\"hello\\");
          return 42;
        }"

    the old collector stopped at the ``console.log(\\"hello\\");``
    line (because it contains ``"``), the assembled buffer was still
    unterminated, shlex.split failed, and the command was silently
    dropped. The agent never got the output back.

    Root fix: use ``shlex`` as the single source of truth for "is this
    command complete" — keep collecting until the assembled buffer
    parses cleanly. shlex already understands shell quoting rules
    correctly, including backslash escapes inside double quotes.
    """
    text = '''bp eval "function() {
  console.log(\\"hello\\");
  return 42;
}"'''
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1, f"expected exactly 1 command, got {len(cmds)}: {cmds!r}"
    assert cmds[0].ok, f"command must parse cleanly, got error: {cmds[0].parse_error}"
    assert cmds[0].argv[0] == "bp"
    assert cmds[0].argv[1] == "eval"
    script = cmds[0].argv[2]
    assert "console.log" in script
    assert '"hello"' in script, f"escaped quotes must be preserved, got: {script!r}"
    assert "return 42" in script


def test_multiline_with_several_escaped_quotes_still_resolves():
    text = r'''bp eval "const a = \"x\"; const b = \"y\";
console.log(a, b);
return a + b"'''
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert cmds[0].ok
    assert '"x"' in cmds[0].argv[2]
    assert '"y"' in cmds[0].argv[2]


def test_multiline_eval_followed_by_next_command():
    """Collector must stop at the right place — not swallow the next
    ``bp read`` into the eval script."""
    text = '''bp eval "function() {
  return 42;
}"
bp read'''
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 2
    assert cmds[0].ok and cmds[0].subcommand == "eval"
    assert cmds[1].ok and cmds[1].argv == ("bp", "read")


# ---------------------------------------------------------------------------
# Codex Phase R P1 regression: argv-first prevents shell injection
# structurally.
# ---------------------------------------------------------------------------


def test_exec_ready_argv_defeats_shell_injection():
    """REGRESSION TEST for the Codex Phase R P1 finding.

    An LLM emitting ``bp read; rm -rf ~`` must NOT produce an argv
    that lets the shell see a second command. shlex.split in posix
    mode does NOT split on ``;`` (it's a literal character inside
    words), so the semicolon becomes part of whatever word it was
    attached to. Combined with ``create_subprocess_exec``, this means
    the ``rm -rf ~`` fragment becomes a literal argument to ``bp``,
    which will fail gracefully because ``bp`` has no such subcommand.

    The guarantee we're locking in: argv[0] is always ``cli_prefix``,
    and no element of argv ever reaches a shell.
    """
    text = "bp read; rm -rf ~"
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert cmds[0].ok
    assert cmds[0].argv[0] == "bp"
    # The semicolon sticks to "read;" — the whole injection becomes
    # literal argv tokens to bp.
    assert "read;" in cmds[0].argv
    # No argv element is ever a shell-ready string — argv is a
    # structured list ready for execve(2).
    assert all(isinstance(x, str) for x in cmds[0].argv)


def test_argv0_is_always_cli_prefix():
    """Structural invariant: any ParsedCommand with ok==True has
    argv[0] == cli_prefix. Downstream code can rely on this without
    re-checking."""
    text = """bp open https://a
bp read
bp eval 'x + y'
"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 3
    for cmd in cmds:
        assert cmd.ok
        assert cmd.argv[0] == "bp"


def test_subcommand_property():
    cmds = extract_commands("bp open https://a\nbp read\nbp", "bp")
    # Three lines but the last one has no space after "bp" so it
    # doesn't match the prefix pattern.
    assert len(cmds) == 2
    assert cmds[0].subcommand == "open"
    assert cmds[1].subcommand == "read"


def test_parse_error_is_reported_not_raised():
    """An unterminated quoted argument that reaches end-of-input
    should produce a failed ParsedCommand, not raise."""
    text = "bp eval 'unclosed"
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert not cmds[0].ok
    assert cmds[0].parse_error is not None
    assert cmds[0].argv == ()


# ---------------------------------------------------------------------------
# extract_answer
# ---------------------------------------------------------------------------


def test_extract_answer_same_line():
    assert extract_answer("ANSWER: 42") == "42"


def test_extract_answer_block():
    text = """Some prose here.
ANSWER:
The answer is 42.
DONE"""
    assert extract_answer(text) == "The answer is 42."


def test_extract_answer_none():
    assert extract_answer("no answer keyword in this text") is None


def test_extract_answer_caps_at_2000_chars():
    text = "ANSWER: " + "x" * 3000
    out = extract_answer(text)
    assert out is not None
    assert len(out) == 2000
