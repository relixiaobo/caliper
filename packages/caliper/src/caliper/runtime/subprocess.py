"""Async subprocess runner with timeout and stdout/stderr capture.

Used by every text-protocol solver to execute the CLI commands the agent
emits. The runner takes an **explicit argv list** and uses
``create_subprocess_exec``, which passes arguments straight to
``execve(2)`` with zero shell interpretation.

This is a security-critical choice. An earlier version used
``create_subprocess_shell`` with a command string, which meant an LLM
(or a prompt-injected web page whose content was being summarised)
could emit ``bp read; rm -rf ~`` and the shell would happily execute
both commands. Codex review of the Phase R restructure caught this as
a P1. The regression test is in
``packages/caliper/tests/unit/test_runtime_subprocess.py``.

**Never** reintroduce a shell-based path. If a caller has a command
string, they must ``shlex.split(..., posix=True)`` it first, validate
the resulting argv[0], and pass the list to this function.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence


async def run_cli(argv: Sequence[str], timeout: float = 60.0) -> str:
    """Run a command via ``execve(2)`` and return combined output.

    Args:
        argv: The argument list. ``argv[0]`` is the executable; the
            rest are literal arguments with zero shell interpretation.
            Shell metacharacters in the arguments (``;``, ``|``, ``&``,
            backticks, ``$VAR``, glob patterns, newlines) are passed
            through as literal bytes to the target process.
        timeout: Wall-clock timeout in seconds. On timeout the process
            is killed and an error string is returned.

    Returns:
        On success: raw stdout (uncapped — the caller decides whether
        and how to truncate).
        On non-zero exit: ``"ERROR (exit N): <stderr or stdout>"``
        (capped to 3000 chars).
        On timeout: ``"ERROR: command timed out after Ns"``.
        On empty argv / missing executable / other launch failure:
        ``"ERROR: ..."``.

    Never raises — all failure modes return an ``ERROR:`` string so the
    agent loop can feed the error back to the LLM and continue.
    """
    if not argv:
        return "ERROR: empty argv"

    argv_list = list(argv)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"ERROR: command timed out after {timeout}s: {argv_list!r}"
        out = (stdout or b"").decode("utf-8", errors="replace")
        err = (stderr or b"").decode("utf-8", errors="replace")
        if proc.returncode != 0:
            return f"ERROR (exit {proc.returncode}): {err.strip() or out.strip()}"[:3000]
        return out
    except FileNotFoundError:
        return f"ERROR: executable not found: {argv_list[0]!r}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: failed to launch command: {exc}"
