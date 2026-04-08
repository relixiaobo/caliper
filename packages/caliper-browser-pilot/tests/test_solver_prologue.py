"""Contract tests for ``bp_agent``'s default session prologue.

The M1.6b post-mortem identified CHROME_TAB_POLLUTION as the
dominant Sonnet failure class in the v9 baseline: bp attaches to the
user's real Chrome via CDP and its ``activeTargetId`` state persists
in ``~/.browser-pilot/state.json`` across invocations, so sample N's
tab leaks into sample N+1.

``bp_agent`` now defaults to running ``bp disconnect`` + ``bp connect``
at the start of every sample to guarantee a fresh pilot tab. These
tests pin that default so it can't be silently removed.

If a future change legitimately needs to weaken or change the default,
update both the default *and* these tests in the same commit, with a
note on what failure class the new default guards against.
"""

from __future__ import annotations

from caliper_browser_pilot.solver import BP_DEFAULT_SESSION_PROLOGUE


def test_default_prologue_is_disconnect_then_connect():
    """The known-good reset sequence is disconnect followed by
    connect. disconnect alone leaves the daemon dead; connect alone
    doesn't clear prior state. Both, in order, are required."""
    assert BP_DEFAULT_SESSION_PROLOGUE == [
        ["bp", "disconnect"],
        ["bp", "connect"],
    ]


def test_default_prologue_is_nonempty():
    """Guardrail: if this ever becomes an empty list, the
    CHROME_TAB_POLLUTION failure class comes back silently."""
    assert len(BP_DEFAULT_SESSION_PROLOGUE) > 0
    assert all(
        isinstance(cmd, list) and cmd and cmd[0] == "bp"
        for cmd in BP_DEFAULT_SESSION_PROLOGUE
    )
