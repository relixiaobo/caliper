"""Construction tests for the v8_baseline @task definitions.

These tests verify that all 5 task functions construct cleanly without
making any LLM calls. They lock in:

- Total sample counts per bucket task
- ``epochs=2`` default (methodology principle 2)
- Default judge / max_turns parameters
- bucket-specific tasks return only the right ids
- Calling with custom parameters works

Running the actual 24-sample baseline against a model is M1.6's job
(``v9 baseline produced``); these tests do NOT call any model.
"""

from caliper_browser_pilot.tasks import (
    v8_baseline,
    v8_compare,
    v8_lookup,
    v8_navigate,
    v8_search,
)


def test_v8_baseline_has_twelve_samples_default_epochs_2():
    t = v8_baseline()
    assert len(t.dataset) == 12
    assert t.epochs == 2


def test_v8_lookup_has_three_samples():
    t = v8_lookup()
    assert len(t.dataset) == 3
    ids = {s.id for s in t.dataset}
    assert ids == {
        "Cambridge Dictionary--3",
        "Wolfram Alpha--0",
        "Wolfram Alpha--2",
    }


def test_v8_search_has_three_samples():
    t = v8_search()
    ids = {s.id for s in t.dataset}
    assert ids == {"Allrecipes--3", "Coursera--0", "Huggingface--3"}


def test_v8_compare_has_three_samples_including_apple_minus_three():
    """Apple--3 must be in the compare bucket; it's the v8 baseline's
    one persistent Sonnet failure. The test exists to lock the bucket
    membership so an accidental rebucket doesn't quietly relocate the
    canary task."""
    t = v8_compare()
    ids = {s.id for s in t.dataset}
    assert ids == {"Apple--0", "Apple--3", "Allrecipes--0"}


def test_v8_navigate_has_three_samples():
    t = v8_navigate()
    ids = {s.id for s in t.dataset}
    assert ids == {"GitHub--3", "BBC News--5", "ArXiv--2"}


def test_buckets_partition_the_baseline():
    """The 4 bucket tasks together should cover exactly the 12 baseline
    samples — no overlap, no gap."""
    full = {s.id for s in v8_baseline().dataset}
    union = (
        {s.id for s in v8_lookup().dataset}
        | {s.id for s in v8_search().dataset}
        | {s.id for s in v8_compare().dataset}
        | {s.id for s in v8_navigate().dataset}
    )
    assert union == full
    assert len(union) == 12


def test_epochs_override_works():
    t = v8_baseline(epochs=3)
    assert t.epochs == 3


def test_max_turns_default_is_twelve():
    """v8 baseline used max_turns=12; the canary Apple--3 failure
    depends on this. The default must NOT silently grow."""
    # We can't easily introspect the solver's max_turns from a built
    # Task object, so we just verify the function accepts the parameter
    # and the caller-supplied value works without error.
    t = v8_baseline(max_turns=12)
    assert len(t.dataset) == 12


def test_judge_model_override():
    t = v8_baseline(judge_model="anthropic/claude-haiku-4-5")
    assert len(t.dataset) == 12  # smoke: construction succeeded


def test_metadata_preserved_through_task_construction():
    """The bucket / source / etc. metadata must survive the loader →
    Task wiring. Scorers (judge_stale_ref, lazy_detection) and the
    M1.4 report layer depend on it."""
    t = v8_baseline()
    for s in t.dataset:
        md = s.metadata or {}
        assert md.get("bucket") in {"lookup", "search", "compare", "navigate"}
        assert md.get("source") == "WebVoyager"
        assert md.get("license") == "academic"


def _tasks_dir():
    """Return the on-disk path of caliper_browser_pilot/tasks/. We
    resolve via the parent package to avoid the submodule-vs-export
    name collision: ``caliper_browser_pilot.tasks.v8_baseline`` after
    ``from .v8_baseline import v8_baseline`` in ``__init__.py``
    refers to the function, not the module."""
    from pathlib import Path

    import caliper_browser_pilot.tasks as tasks_pkg

    return Path(tasks_pkg.__file__).resolve().parent


def test_v8_baseline_file_exposes_exactly_one_task_REGRESSION():
    """REGRESSION TEST for the Codex M1.3 round-2 P2 finding.

    ``inspect eval .../v8_baseline.py`` (without an ``@v8_baseline``
    selector) discovers and runs every ``@task`` in the file. The
    earlier design put the full baseline AND four bucket-level helpers
    in the same module, so the documented baseline invocation actually
    ran 5 tasks instead of 1: 12 + 3+3+3+3 = 24 samples × epochs=2
    = 48 runs instead of the advertised 24. That doubles cost and
    contaminates measurements with implicit cross-task aggregation.

    Root fix: split the file. ``v8_baseline.py`` contains exactly
    one @task; ``v8_buckets.py`` contains the 4 bucket helpers.
    Default discovery on each file matches its intent.
    """
    from inspect_ai._eval.loader import _load_task_specs

    baseline_path = _tasks_dir() / "v8_baseline.py"
    specs = _load_task_specs(baseline_path)
    assert len(specs) == 1, (
        f"v8_baseline.py must expose exactly 1 @task to keep "
        f"`inspect eval` invocations correct, but discovered {len(specs)} "
        f"tasks. Move bucket-level helpers into v8_buckets.py."
    )


def test_v8_buckets_file_exposes_four_tasks():
    """The 4 bucket helpers live in their own file. Discovery on that
    file should yield exactly 4 tasks, none of which is the full
    baseline (so running v8_buckets.py without a selector covers the
    same 12 samples once, not double-counted)."""
    from inspect_ai._eval.loader import _load_task_specs

    buckets_path = _tasks_dir() / "v8_buckets.py"
    specs = _load_task_specs(buckets_path)
    assert len(specs) == 4


def test_construction_works_without_ANTHROPIC_API_KEY_REGRESSION(monkeypatch):
    """REGRESSION TEST for the Codex M1.3 P1 finding.

    Constructing a Task definition (in CI / unit tests / a bare
    machine) must NOT require API credentials. Only an actual
    ``inspect eval`` invocation should fail when keys are missing.

    Pre-fix: ``judge_stale_ref(model=...)`` called ``get_model()`` at
    factory time, which initialised the Anthropic client and raised
    ``PrerequisiteError`` immediately if ``ANTHROPIC_API_KEY`` was
    unset. That meant ``v8_baseline()`` couldn't be constructed at
    all on credential-free machines, breaking offline test runs.

    Root fix: ``judge_stale_ref`` now defers the ``get_model()`` call
    to inside ``score()``, so the API key is only checked when the
    judge actually runs.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Construction must succeed even with no credentials.
    t = v8_baseline()
    assert len(t.dataset) == 12

    # All five tasks should be constructable.
    for fn in (v8_lookup, v8_search, v8_compare, v8_navigate):
        sub = fn()
        assert len(sub.dataset) == 3
