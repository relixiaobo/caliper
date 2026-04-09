"""Construction-time tests for the M1.7a heroku smoke task.

These tests exercise the ``heroku_smoke`` task *without* running any
real model or bp subprocess. They verify:

1. The 4 samples exist and are well-formed.
2. Every sample's metadata has the keys the downstream machinery
   expects (``start_url``, ``bucket``, ``source``, ``verify``).
3. Every verify spec has the shape verify_commands expects
   (``command`` argv, ``expect_contains`` substring).
4. ``heroku_smoke()`` returns a usable Inspect AI ``Task`` object.

The "does it actually pass against the real herokuapp" integration
check is the ``inspect eval .../tasks/smoke.py`` run from M1.7a
validation, not this file. Regression tests that require the real
network or a real Chrome connection would make CI flaky and defeat
the whole point of Layer 1 being fast and free.
"""

from __future__ import annotations

from inspect_ai import Task

from caliper_browser_pilot.tasks.smoke import (
    heroku_smoke,
    heroku_smoke_dataset,
)


EXPECTED_SAMPLE_IDS = frozenset(
    {
        "heroku-checkboxes",
        "heroku-dropdown",
        "heroku-dynamic-loading",
        "heroku-login",
    }
)


def test_smoke_dataset_has_four_samples():
    ds = heroku_smoke_dataset()
    assert len(list(ds)) == 4


def test_smoke_dataset_sample_ids_match_expected():
    ds = heroku_smoke_dataset()
    ids = {s.id for s in ds}
    assert ids == EXPECTED_SAMPLE_IDS


def test_every_sample_has_required_metadata_keys():
    ds = heroku_smoke_dataset()
    for s in ds:
        md = s.metadata or {}
        assert md.get("bucket") == "smoke", f"{s.id}: bucket wrong"
        assert md.get("source") == "the-internet.herokuapp.com", f"{s.id}: source wrong"
        assert "start_url" in md and md["start_url"].startswith(
            "https://the-internet.herokuapp.com/"
        ), f"{s.id}: start_url missing or wrong"
        assert "verify" in md and isinstance(md["verify"], list), (
            f"{s.id}: verify missing or not a list"
        )


def test_every_verify_spec_has_command_and_expected():
    """verify_commands reads ``command`` (argv list) and
    ``expect_contains`` (substring) on every spec. Both must be
    non-empty for the spec to be meaningful."""
    ds = heroku_smoke_dataset()
    for s in ds:
        specs = (s.metadata or {}).get("verify") or []
        assert len(specs) >= 1, f"{s.id}: no verify specs"
        for i, spec in enumerate(specs):
            assert isinstance(spec, dict), f"{s.id} spec {i}: not a dict"
            cmd = spec.get("command") or []
            assert isinstance(cmd, list) and len(cmd) > 0, (
                f"{s.id} spec {i}: command missing or empty"
            )
            assert cmd[0] == "bp", (
                f"{s.id} spec {i}: verify command must start with 'bp'"
            )
            expected = spec.get("expect_contains")
            assert isinstance(expected, str) and expected, (
                f"{s.id} spec {i}: expect_contains missing or empty"
            )


def test_heroku_login_has_both_verify_steps():
    """The login task is the only one with more than 1 verify spec —
    the success message and the URL change. Pinning this so a
    refactor doesn't silently collapse the two checks into one."""
    ds = heroku_smoke_dataset()
    login = next(s for s in ds if s.id == "heroku-login")
    specs = (login.metadata or {}).get("verify") or []
    assert len(specs) == 2
    descriptions = [s.get("description") for s in specs]
    assert any("success" in d.lower() for d in descriptions)
    assert any("url" in d.lower() or "secure" in d.lower() for d in descriptions)


def test_heroku_smoke_task_builds():
    """``heroku_smoke()`` should return a real Inspect AI Task with
    a bp_agent solver and a verify_commands scorer. This is the
    happy-path construction test — if Inspect AI ever changes its
    Task API shape, this is where we find out."""
    t = heroku_smoke()
    assert isinstance(t, Task)
    # Can't assert much more about the internal shape without
    # over-coupling to Inspect AI's private attributes, but the
    # fact that Task() accepted our dataset + solver + scorer
    # trio is enough.
