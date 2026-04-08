"""Tests for the argv-based subprocess runner.

The most important test in this file is
``test_rejects_shell_metacharacter_injection``. It is the regression test
for the P1 finding in Codex's review of the Phase R restructure:
``create_subprocess_shell`` would execute ``bp read; rm -rf ~`` as two
shell commands because the model-emitted line went through /bin/sh.

The fix is in runtime/subprocess.py: the runner now takes an explicit
``argv: list[str]`` and uses ``create_subprocess_exec``, which passes
the arguments directly to ``execve(2)`` without shell interpretation.

Any future change to ``run_cli`` MUST keep the regression test passing.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path


from caliper.runtime.subprocess import run_cli


# ---------------------------------------------------------------------------
# Happy path: normal argv execution
# ---------------------------------------------------------------------------


def test_runs_simple_argv():
    result = asyncio.run(run_cli(["echo", "hello world"]))
    assert result.strip() == "hello world"


def test_runs_argv_with_multiple_args():
    result = asyncio.run(run_cli(["echo", "-n", "foo", "bar"]))
    assert result == "foo bar"


def test_empty_argv_returns_error():
    result = asyncio.run(run_cli([]))
    assert "ERROR" in result


def test_nonzero_exit_returns_error():
    result = asyncio.run(run_cli(["false"]))
    assert "ERROR" in result
    assert "exit 1" in result


def test_missing_executable_returns_error():
    result = asyncio.run(
        run_cli(["this_executable_does_not_exist_abc123xyz"])
    )
    assert "ERROR" in result


# ---------------------------------------------------------------------------
# P1 REGRESSION: prompt-injection via shell metacharacters
# ---------------------------------------------------------------------------


def test_rejects_shell_metacharacter_injection(tmp_path: Path):
    """REGRESSION TEST for the Codex Phase R P1 finding.

    An LLM (or a prompt-injected web page whose content is being
    summarised) might emit a line like ``bp read; touch /tmp/owned``.
    If the runner uses ``create_subprocess_shell``, /bin/sh parses the
    semicolon and executes both commands — arbitrary host code
    execution.

    The fix is to use ``create_subprocess_exec`` with an explicit argv
    list, which goes straight to ``execve(2)`` with zero shell
    interpretation. The semicolon and everything after become a literal
    argument to the first command.

    This test simulates the attack: if the injection worked, the
    canary file would exist. If the fix holds, the canary file is
    never created — the extra tokens are just passed to ``echo``
    (which prints them) and the shell never sees them.
    """
    canary = tmp_path / "pwned"
    assert not canary.exists()

    # What `extract_commands` would produce from a malicious line:
    #     "bp read; touch /tmp/...; rm -rf ~"
    # shlex.split parses this into a token list where the semicolons
    # become part of the literal argument to bp (they are not operators
    # to shlex in posix mode). We simulate the full shelx pipeline:
    injected = f"echo hello; touch {canary}"
    argv = shlex.split(injected, posix=True)
    # shlex.split leaves the semicolon attached to "hello;"; it does
    # NOT split on shell operators. argv[0] is "echo" — safe.
    result = asyncio.run(run_cli(argv))

    # The echo succeeds; it prints the literal tokens including the
    # semicolon and the touch-command fragment. /bin/sh is never invoked.
    assert "hello;" in result or "hello" in result

    # CRITICAL ASSERTION: the canary file was NOT created, proving that
    # the injected "; touch ..." never reached a shell.
    assert not canary.exists(), (
        "shell-injection regression: run_cli executed a secondary "
        "command through /bin/sh. The fix must use create_subprocess_exec "
        "with an explicit argv list."
    )


def test_rejects_backtick_command_substitution(tmp_path: Path):
    """Defensive: backticks are command substitution in shell, but must
    be literal chars in exec mode."""
    canary = tmp_path / "pwned_backtick"
    assert not canary.exists()

    # A shell would execute the backtick contents and interpolate.
    # exec treats it as a literal argument.
    argv = ["echo", f"`touch {canary}`"]
    asyncio.run(run_cli(argv))

    assert not canary.exists()


def test_rejects_dollar_expansion(tmp_path: Path, monkeypatch):
    """Defensive: $HOME and friends must not expand in exec mode."""
    monkeypatch.setenv("CALIPER_CANARY", str(tmp_path / "should_not_appear"))
    result = asyncio.run(run_cli(["echo", "$CALIPER_CANARY"]))
    # If shell expansion happened, we'd see the tmp_path. With exec,
    # we see the literal string.
    assert "$CALIPER_CANARY" in result
    assert str(tmp_path) not in result


# ---------------------------------------------------------------------------
# Timeout behaviour
# ---------------------------------------------------------------------------


def test_timeout_kills_process():
    result = asyncio.run(run_cli(["sleep", "10"], timeout=0.5))
    assert "timed out" in result.lower()
