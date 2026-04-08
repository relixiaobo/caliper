"""Build ``baselines/v9.json`` from the M1.6 Sonnet + GPT-5.4 runs.

This is a one-off script, not a reusable library. It exists to:

1. Record the structured anchor numbers for caliper's first
   token+cache-aware baseline.
2. Document the deviations from browser-pilot v8 alongside their
   root causes, so future readers don't mistake environmental
   drift for a caliper regression.

Run:

    uv run python baselines/build_v9.py

Output: ``baselines/v9.json`` (pretty-printed, committed to git).

The input .eval logs are NOT committed — they're large and
reproducible from this script + the same workspace commit. v9.json
records the log filenames + SHA of the caliper commit they were
generated under so future runs can be compared fairly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Repo-relative paths. Run from the repo root via
# ``uv run python baselines/build_v9.py``.
_REPO = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_REPO / "packages" / "caliper" / "src"))

from inspect_ai.log import read_eval_log  # noqa: E402

from caliper.report import load_bucket_report  # noqa: E402


# ---------------------------------------------------------------------------
# Input: the .eval log files produced during M1.6
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunInput:
    model: str
    log_filename: str
    notes: str


# Edit these two paths to point at the actual .eval logs produced
# during M1.6. See the top of the module for context.
_RUNS: list[RunInput] = [
    RunInput(
        model="anthropic/claude-sonnet-4-6",
        log_filename="2026-04-08T07-30-35-00-00_v8-baseline_YWg5jV8KaRhWnFvipnBMPa.eval",
        notes=(
            "Sonnet full v8 baseline (12 tasks × 2 epochs = 24 runs). "
            "Wall time 46:21. 5 samples hit max_turns=12 (tool_limit "
            "failure mode). Trace review (post-mortem v2, after the "
            "first-draft 'environmental drift' narrative was "
            "corrected and again after Apple was mis-attributed as "
            "SITE_RENDER) split them into 3 classes with a clear "
            "dominant cause: SITE_RENDER x1 (Wolfram Alpha--0 — "
            "agent finds '11.2' only inside SVG path coordinates and "
            "concludes 'the result is rendered as an image'); "
            "REF_STALE x1 (BBC News--5 — bp open on the reference "
            "URL returns 'BBC - 500: Internal Server Error'); "
            "CHROME_TAB_POLLUTION x3 (Huggingface--3 contains the "
            "explicit agent observation 'tab mismatch', Allrecipes--0 "
            "has 26 BBC mentions bleeding into the task, Apple--0 "
            "ep 2 initially loaded the MacBook Air page with "
            "$1099/$1299 prices but later tool output switches to "
            "Allrecipes content). The Wolfram trace also shows "
            "session-state contamination signals (final bp net lists "
            "an allrecipes.com GET as the only request, mid-trace "
            "Merriam-Webster navigation), so the CHROME_TAB_POLLUTION "
            "story may be even stronger than 3/5. See "
            "docs/lessons-learned.md M1.6 section for the full "
            "attribution and the meta-lesson."
        ),
    ),
    # Filled in post-run by main(); placeholder for GPT-5.4
]


# ---------------------------------------------------------------------------
# v8 anchor numbers (from docs/reference/baseline-v8.md)
# ---------------------------------------------------------------------------


_V8_ANCHORS: dict[str, Any] = {
    "anthropic/claude-sonnet-4-6": {
        "overall_pass": "23/24",
        "overall_pass_rate": 23 / 24,
        "per_bucket": {
            "lookup": "6/6",
            "search": "6/6",
            "compare": "5/6",
            "navigate": "6/6",
        },
        "canary_failure_expected": "Apple--3 epoch 2 hits 12-step limit",
        "measured_on": "2026-04-07",
        "source": "docs/reference/baseline-v8.md",
    },
    "openai/gpt-5.4": {
        "overall_pass": "17/24",
        "overall_pass_rate": 17 / 24,
        "per_bucket": {
            "lookup": "4/6",
            "search": "3/6",
            "compare": "6/6",
            "navigate": "4/6",
        },
        "measured_on": "2026-04-07",
        "source": "docs/reference/baseline-v8.md",
    },
}


# ---------------------------------------------------------------------------
# M1.6b validation round: re-running the 5 failed v9 Sonnet samples with
# the new bp session prologue fix to test the post-mortem diagnosis.
# ---------------------------------------------------------------------------


_M1_6B_VALIDATION: dict[str, Any] = {
    "description": (
        "Validation re-run of the 5 v9 Sonnet TOOL_LIMIT failures "
        "with the M1.6b bp session prologue fix applied. The fix "
        "defaults text_protocol_agent's session_prologue to "
        "['bp disconnect', 'bp connect'] before each sample, which "
        "clears bp's ~/.browser-pilot/state.json and creates a fresh "
        "pilot tab. Purpose: test the CHROME_TAB_POLLUTION diagnosis "
        "from the v9 post-mortem v2 (see methodology_notes above) "
        "against real trace evidence."
    ),
    "log_filename": (
        "2026-04-08T13-35-07-00-00_v8-baseline_RpcBAmsX8pYqmNt3VuZow7.eval"
    ),
    "run_date": "2026-04-08",
    "runtime_minutes": 30,
    "caliper_commit_at_run": "c32ad10 + WIP M1.6b fix (uncommitted at run time)",
    "spec": {
        "sample_ids": [
            "Wolfram Alpha--0",
            "BBC News--5",
            "Huggingface--3",
            "Allrecipes--0",
            "Apple--0",
        ],
        "epochs": 2,
        "total_runs": 10,
        "max_turns": 12,
        "model": "anthropic/claude-sonnet-4-6",
    },
    "headline": {
        "pass_count": 8,
        "pass_rate": 0.80,
        "lazy_count": 1,
        "total_tokens": 792947,
        "total_uncached_input_tokens": 709427,
        "v9_subset_pass_count": 0,
        "v9_subset_pass_rate": 0.00,
        "lift_pct_points": 80,
    },
    "per_sample": {
        "Wolfram Alpha--0": {
            "epoch_1": {
                "judge": True,
                "lazy": False,
                "commands_run": 2,
                "msgs": 5,
                "tokens": 8282,
            },
            "epoch_2": {
                "judge": True,
                "lazy": False,
                "commands_run": 10,
                "msgs": 9,
                "tokens": 26729,
            },
            "v9_classification_post_mortem_v2": "SITE_RENDER",
            "m1_6b_outcome": "PASS x2",
            "revised_diagnosis": (
                "The v9 post-mortem v2 labelled this SITE_RENDER because "
                "the v9 trace showed the agent finding '11.2' only in SVG "
                "path coordinates and writing 'the result is rendered as "
                "an image'. In M1.6b with a clean bp session, the agent "
                "answered in 2 commands (epoch 1) and 10 commands (epoch "
                "2) without hitting any SVG wall. The SITE_RENDER label "
                "was wrong — the real cause was also CHROME_TAB_POLLUTION. "
                "The SVG path coordinates the v9 agent tripped over were "
                "a symptom of the polluted DOM/navigation state, not a "
                "stable property of Wolfram Alpha's rendering."
            ),
        },
        "BBC News--5": {
            "epoch_1": {
                "judge": True,
                "lazy": False,
                "commands_run": 10,
                "msgs": 5,
                "tokens": 14314,
            },
            "epoch_2": {
                "judge": True,
                "lazy": False,
                "commands_run": 2,
                "msgs": 5,
                "tokens": 8953,
            },
            "v9_classification_post_mortem_v2": "REF_STALE",
            "m1_6b_outcome": "PASS x2",
            "revised_diagnosis": (
                "The v9 post-mortem v2 labelled this REF_STALE because "
                "the v9 trace showed the first bp open returning 'BBC - "
                "500: Internal Server Error' as the literal page title. "
                "In M1.6b with a clean bp session, BOTH epochs reached "
                "the article and answered correctly. The REF_STALE label "
                "was wrong — actual cause was CHROME_TAB_POLLUTION (or a "
                "genuine transient BBC outage that coincidentally "
                "resolved, which cannot be fully ruled out without more "
                "data points). The prior-pattern match with Wolfram's "
                "same-day reversal makes 'session pollution presenting "
                "as a fake 500' far more likely than 'BBC had a real 12-"
                "hour outage that happened to span the v9 run'."
            ),
        },
        "Huggingface--3": {
            "epoch_1": {
                "judge": True,
                "lazy": False,
                "commands_run": 2,
                "msgs": 5,
                "tokens": 13362,
            },
            "epoch_2": {
                "judge": True,
                "lazy": False,
                "commands_run": 8,
                "msgs": 5,
                "tokens": 12368,
            },
            "v9_classification_post_mortem_v2": "CHROME_TAB_POLLUTION",
            "m1_6b_outcome": "PASS x2",
            "revised_diagnosis": (
                "Classification confirmed. The v9 trace's explicit 'tab "
                "mismatch' log was the strongest evidence for this class, "
                "and the M1.6b clean-session run passes in 2-8 commands."
            ),
        },
        "Allrecipes--0": {
            "epoch_1": {
                "judge": True,
                "lazy": True,
                "commands_run": 0,
                "msgs": 3,
                "tokens": 8846,
            },
            "epoch_2": {
                "judge": True,
                "lazy": False,
                "commands_run": 19,
                "msgs": 13,
                "tokens": 136397,
            },
            "v9_classification_post_mortem_v2": "CHROME_TAB_POLLUTION",
            "m1_6b_outcome": "PASS x2 (1 lazy)",
            "revised_diagnosis": (
                "CHROME_TAB_POLLUTION classification confirmed for both "
                "epochs. SIDE FINDING: epoch 1 scored lazy=True "
                "(commands_run=0, message_count=3) — Sonnet produced a "
                "single-turn training-data answer that happened to be "
                "correct. v9's full Sonnet baseline showed 0 lazy across "
                "24 runs. 1/10 lazy here could be noise or a real "
                "low-rate Sonnet behaviour; a single data point is not "
                "enough to generalise."
            ),
        },
        "Apple--0": {
            "epoch_1": {
                "judge": False,
                "lazy": False,
                "commands_run": 73,
                "msgs": 26,
                "tokens": 311826,
            },
            "epoch_2": {
                "judge": False,
                "lazy": False,
                "commands_run": 169,
                "msgs": 26,
                "tokens": 251870,
            },
            "v9_classification_post_mortem_v2": "CHROME_TAB_POLLUTION",
            "m1_6b_outcome": "FAIL x2 (max_turns=12, both epochs)",
            "revised_diagnosis": (
                "CLASSIFICATION DISPROVEN. With a clean bp session, the "
                "agent's first 'bp read --limit 8000' at message 7 "
                "returns the full MacBook Air pricing: '13-inch From "
                "$1099 or $91.58 per month', '15-inch From $1299 or "
                "$108.25 per month'. That IS the answer to 'compare the "
                "prices of the latest MacBook Air models'. But instead "
                "of writing ANSWER, the agent keeps going — clicking "
                "non-existent configurator selectors, running JS regexes "
                "against document.body.innerHTML — for 73 / 169 commands "
                "before running out of turns. This is a NEW failure "
                "class: AGENT_BEHAVIOR (over-exploration / refusal to "
                "commit to a plausible partial answer). Not a bp problem, "
                "not a site problem — an agent-prompt / termination-"
                "criteria problem. Needs its own follow-up; tracked as "
                "a roadmap item, not fixed in M1.6b."
            ),
        },
    },
    "diagnosis_verdict": {
        "CHROME_TAB_POLLUTION_validated_for": [
            "Wolfram Alpha--0",
            "BBC News--5",
            "Huggingface--3",
            "Allrecipes--0",
        ],
        "CHROME_TAB_POLLUTION_disproven_for": ["Apple--0"],
        "v9_failures_attributable_to_ctp": "4 of 5",
        "ctp_net_lift_projected_on_full_baseline": (
            "19/24 -> approximately 23/24 if the subset lift "
            "generalises, matching the v8 anchor. This is a projection, "
            "not a measured full re-run."
        ),
        "new_failure_class_found": (
            "Apple--0: AGENT_BEHAVIOR / over-exploration — agent has "
            "sufficient answer data at turn 3 but refuses to commit, "
            "burns 73-169 commands searching for more detail before "
            "hitting max_turns. Needs separate fix (prompt / "
            "termination logic)."
        ),
    },
    "what_this_means_for_the_post_mortem": (
        "Post-mortem v2 (which this v9.json recorded before M1.6b ran) "
        "was STILL wrong on 2 of 5 samples. The 1/1/3 split of "
        "SITE_RENDER/REF_STALE/CHROME_TAB_POLLUTION is superseded by the "
        "M1.6b verdict: 4/1 CHROME_TAB_POLLUTION / AGENT_BEHAVIOR. This "
        "is the THIRD round of corrections to the M1.6 post-mortem. The "
        "earlier rounds are preserved in methodology_notes above and in "
        "docs/lessons-learned.md's 'what does not hold' lists. The "
        "running meta-lesson: even trace-backed post-mortems can be "
        "wrong, and the only way to close the loop on a diagnosis is to "
        "actually apply the fix and re-run. Classification from static "
        "trace reading is hypothesis; pass/fail after the fix is data."
    ),
}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _bucket_to_dict(bucket) -> dict[str, Any]:
    """Serialise BucketStats to a plain dict."""
    u = bucket.total_usage
    return {
        "n_runs": bucket.n_runs,
        "n_unique_samples": bucket.n_unique_samples,
        "pass_count": bucket.pass_count,
        "pass_rate": round(bucket.pass_rate, 4),
        "lazy_count": bucket.lazy_count,
        "lazy_rate": round(bucket.lazy_rate, 4),
        "mean_total_tokens": round(bucket.mean_total_tokens, 1),
        "mean_uncached_input_tokens": round(bucket.mean_uncached_input_tokens, 1),
        "cache_hit_rate": (
            round(bucket.cache_hit_rate, 4)
            if bucket.cache_hit_rate is not None
            else None
        ),
        "total_tokens": u.total_tokens,
        "total_uncached_input_tokens": u.uncached_input_tokens,
        "has_cache_info": u.has_cache_info,
    }


def _failed_samples(log_path: Path) -> list[dict[str, Any]]:
    """Extract failed samples with their failure-attribution tags.

    Reads the raw EvalLog so we can inspect per-sample message
    counts and store state — information that doesn't survive the
    BucketReport abstraction. Failure-tag vocabulary comes from
    methodology.md principle 4.
    """
    log = read_eval_log(str(log_path))
    failures: list[dict[str, Any]] = []
    if not log.samples:
        return failures

    for s in log.samples:
        judge = (s.scores or {}).get("judge_stale_ref")
        if judge is None or bool(judge.value):
            continue

        n_messages = len(s.messages) if s.messages else 0
        # A solver with max_turns=12 produces at most
        #   1 system + 1 user + 12 × (assistant + user tool result) = 26
        # so 26 messages almost always means the agent hit the limit.
        commands_run = 0
        if s.store:
            commands_run = int(s.store.get("SolverState:commands_run", 0) or 0)

        if n_messages >= 25 or commands_run >= 12:
            tag = "TOOL_LIMIT"
        elif commands_run == 0:
            tag = "LLM_BEHAVIOR"  # agent produced an answer without observation
        else:
            tag = "UNKNOWN"

        total_tokens = sum(
            u.input_tokens
            + u.output_tokens
            + (u.input_tokens_cache_read or 0)
            + (u.input_tokens_cache_write or 0)
            for u in (s.model_usage or {}).values()
        )

        failures.append(
            {
                "sample_id": str(s.id),
                "epoch": s.epoch,
                "bucket": (s.metadata or {}).get("bucket", "ungrouped"),
                "failure_tag": tag,
                "commands_run": commands_run,
                "message_count": n_messages,
                "total_tokens": total_tokens,
                "judge_reason": (judge.explanation or "")[:120],
            }
        )
    return failures


def _model_section(run: RunInput) -> dict[str, Any]:
    """Build the per-model block of v9.json."""
    log_path = _REPO / "logs" / run.log_filename
    report = load_bucket_report(log_path)

    overall = _bucket_to_dict(report.overall)
    buckets = {b.bucket: _bucket_to_dict(b) for b in report.buckets}
    failures = _failed_samples(log_path)

    v8 = _V8_ANCHORS.get(run.model, {})
    sonnet_target_range = (22, 24)  # ±1 of 23
    gpt54_target_range = (16, 18)  # ±1 of 17
    target_range = (
        sonnet_target_range
        if run.model == "anthropic/claude-sonnet-4-6"
        else gpt54_target_range
    )
    pass_in_range = target_range[0] <= report.overall.pass_count <= target_range[1]

    return {
        "model": run.model,
        "log_filename": run.log_filename,
        "log_note": run.notes,
        "task": report.task_name,
        "overall": overall,
        "buckets": buckets,
        "failed_samples": failures,
        "v8_anchor": v8,
        "v8_comparison": {
            "pass_target_range": f"{target_range[0]}-{target_range[1]}/24",
            "pass_actual": f"{report.overall.pass_count}/{report.overall.n_runs}",
            "pass_in_range": pass_in_range,
            "pass_delta_vs_v8_midpoint": report.overall.pass_count
            - (target_range[0] + target_range[1]) / 2,
        },
    }


# SHA of the caliper HEAD commit under which the v9 .eval logs were
# actually recorded. This is PINNED, not read from git, so that
# rebuilding v9.json from the same logs after subsequent commits
# (e.g. narrative corrections) still records the measurement
# commit for provenance. Do NOT change this unless the logs are
# re-generated.
_MEASUREMENT_COMMIT = "152e66893c59"


def _caliper_commit() -> str:
    """Pinned SHA of the commit under which v9 logs were recorded."""
    return _MEASUREMENT_COMMIT


def _git_head_short() -> str:
    """Short SHA of the current caliper HEAD — used for narrative
    provenance, separate from the measurement commit above."""
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def _inspect_ai_version() -> str:
    try:
        import inspect_ai

        return getattr(inspect_ai, "__version__", "unknown")
    except ImportError:
        return "unknown"


_MEASUREMENT_DATE = "2026-04-08"


def build_v9(runs: list[RunInput]) -> dict[str, Any]:
    """Assemble the full v9.json structure."""
    return {
        "schema_version": "1.0",
        "baseline_name": "v9",
        "description": (
            "First caliper-produced baseline (token + cache "
            "observability layer). Re-measurement of the 12 v8 "
            "curated tasks using caliper-browser-pilot's v8_baseline "
            "@task, M1.6 of the Phase 1 port."
        ),
        # test_date and caliper_commit are pinned to the measurement run.
        # analysis_commit tracks the commit under which build_v9.py was
        # LAST executed to produce this file (narrative/attribution
        # updates). generated_at is the UTC timestamp of that run.
        "test_date": _MEASUREMENT_DATE,
        "caliper_commit": _caliper_commit(),
        "analysis_commit": _git_head_short(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inspect_ai_version": _inspect_ai_version(),
        "task_spec": {
            "task_name": "v8_baseline",
            "source_data": (
                "packages/caliper-browser-pilot/src/caliper_browser_pilot/"
                "data/v8_curated.jsonl"
            ),
            "n_tasks": 12,
            "epochs": 2,
            "max_turns": 12,
            "judge_scorer": "judge_stale_ref",
            "judge_model": "anthropic/claude-sonnet-4-6",
            "lazy_scorer": "lazy_detection",
        },
        "models": {run.model: _model_section(run) for run in runs},
        "m1_6b_validation": _M1_6B_VALIDATION,
        "methodology_notes": {
            "post_mortem_status": (
                "FOURTH-pass analysis. The first three passes were "
                "static trace reads; the fourth is a live fix + "
                "re-run. History: Pass 1 (commit 1536416) wrote "
                "'environmental drift' from 1 Sonnet trace — wrong. "
                "Pass 2 read all 5 Sonnet traces and produced a "
                "2/1/2 SITE_RENDER/REF_STALE/CHROME_TAB_POLLUTION "
                "split — wrong about Apple. Pass 3 (commit c32ad10, "
                "post-Codex) verified Apple--0 ep 2's first bp open "
                "returned prices (not an empty shell), reclassified "
                "to CHROME_TAB_POLLUTION, ended with a 1/1/3 split. "
                "Pass 4 (M1.6b validation — see m1_6b_validation "
                "field below) applied the bp session prologue fix "
                "and re-ran the 5 failed samples: 4 of 5 pass, "
                "Apple still fails. Wolfram and BBC — both labelled "
                "as their own classes in pass 3 — turn out to ALSO "
                "have been CHROME_TAB_POLLUTION. Apple turns out to "
                "be a new failure class (AGENT_BEHAVIOR: agent has "
                "pricing data at msg 7 but keeps searching for more "
                "detail, runs out of turns). The final validated "
                "split is 4/1 CTP/AGENT_BEHAVIOR, superseding the "
                "1/1/3 split above — which is preserved as a "
                "record of what trace reading alone could tell us. "
                "Running meta-lesson: trace classification is "
                "hypothesis; fix + re-run is data."
            ),
            "sonnet_failure_attribution": (
                "5 TOOL_LIMIT failures, final validated "
                "classification after the M1.6b fix + re-run (see "
                "m1_6b_validation field above). Split: "
                "CHROME_TAB_POLLUTION x4, AGENT_BEHAVIOR x1. "
                "Wolfram Alpha--0, BBC News--5, Huggingface--3, "
                "and Allrecipes--0 all passed on re-run with a "
                "clean bp session (bp disconnect + bp connect "
                "prologue applied before each sample), which "
                "validates CHROME_TAB_POLLUTION as their root "
                "cause. Apple--0 still failed both epochs with a "
                "clean bp session — the new trace shows the agent "
                "has the pricing answer at message 7 "
                "('13-inch From $1099', '15-inch From $1299') but "
                "refuses to commit, burning 73 / 169 commands on "
                "non-existent configurator selectors before "
                "hitting max_turns=12. This is AGENT_BEHAVIOR "
                "(over-exploration / refusal to commit to "
                "plausible partial answer), not a bp or site bug. "
                "Tracked as Phase 2 follow-up M2.8. Earlier "
                "trace-only classifications (v2 1/1/3 split with "
                "SITE_RENDER for Wolfram and REF_STALE for BBC) "
                "turned out to be reading symptoms instead of "
                "causes — the SVG-path-coordinates wall the v9 "
                "Wolfram agent tripped over and the 'BBC - 500: "
                "Internal Server Error' page title in the v9 BBC "
                "trace were both downstream of the polluted bp "
                "session, not independent site issues. See "
                "methodology_notes.what_does_not_hold for the "
                "full history of superseded claims."
            ),
            "sonnet_not_environmental_drift": (
                "The original draft said 'slow network to Anthropic "
                "API + site drift since 2026-04-07'. Neither half "
                "is evidence-backed. Per-turn API latency was not "
                "measured; 46:21 wall time is consistent with slow "
                "page loads and long retry loops but does not "
                "imply the API specifically was slow. 'Site drift' "
                "generically covered what are actually 4+ distinct "
                "classes of failure, 3 of which turn out to be "
                "the same root cause (CHROME_TAB_POLLUTION). The "
                "corrected attribution names the specific cause "
                "per sample from the trace."
            ),
            "gpt54_behaviour_not_drift": (
                "GPT-5.4 produced 24/24 lazy (message_count=3, "
                "commands_run=0, mean 930 uncached input tokens per "
                "run vs Sonnet's 96,840 on the same tasks). Uniform "
                "pattern: task + initial snapshot -> single-turn "
                "ANSWER from training data. Some correct (BBC "
                "fossil fuels), some hallucinated (Allrecipes recipe "
                "names), some simply wrong (GitHub storage delta: "
                "agent says 30 GB, real answer is 48 GB). The first "
                "draft labelled this 'gpt-5.4 model drift' — NOT "
                "evidence-based. The correct label is 'single-turn "
                "training-data answer', which is behavioural, not "
                "causal. Actual cause (model-level drift vs Inspect "
                "AI OpenAI Responses adapter context formatting vs "
                "prompt/training interaction) is NOT established by "
                "M1.6."
            ),
            "max_turns_verification": (
                "The v8 canary check was originally designed to "
                "catch silent max_turns relaxation. Apple--3 passing "
                "in v9 is NOT a red flag: 5 other samples hit the "
                "exact max_turns=12 limit, proving the limit is "
                "still enforced. Failure attribution tag for all 5: "
                "TOOL_LIMIT."
            ),
            "what_holds": (
                "Findings that survive all post-mortem rounds plus "
                "the M1.6b fix + re-run validation: (1) "
                "lazy_detection surfaces gpt-5.4's silent capability "
                "collapse (13/24 pass rate looks plausible; 24/24 "
                "lazy shows it's 0 real passes — the M1.1 two-scorer "
                "invariant firing on a second data point). (2) "
                "Per-bucket failure attribution plus a fix + re-run "
                "step resolves the 5 Sonnet failures into 2 "
                "root-cause classes: CHROME_TAB_POLLUTION x4 and "
                "AGENT_BEHAVIOR x1. (3) Cache-hit-rate asymmetry "
                "between Anthropic (0.0%, default caching off) and "
                "OpenAI (73.9%, automatic prefix cache) is visible "
                "in caliper's UsageSummary and was invisible in v8. "
                "(4) CHROME_TAB_POLLUTION is the dominant Sonnet "
                "failure class (4 of 5), validated by M1.6b: bp "
                "attaches to the user's real Chrome and its session "
                "state leaks between samples. The M1.6b fix "
                "(bp disconnect + bp connect prologue in bp_agent) "
                "resolves 4 of 5 v9 failures on the subset re-run, "
                "projecting a full-baseline Sonnet pass rate of "
                "~23/24 (matching the v8 anchor). (5) AGENT_BEHAVIOR "
                "is a new failure class discovered by M1.6b — "
                "Apple--0 has a plausible answer at msg 7 but "
                "refuses to commit. Tracked as Phase 2 M2.8, and "
                "notable as the first caliper-discovered agent-"
                "behaviour bug not already covered by the M1.1 "
                "two-scorer invariant."
            ),
            "what_does_not_hold": (
                "Claims removed across three post-mortem rounds. "
                "(v1 corrections, post trace-read) 'environmental "
                "drift' as a unified root cause; 'slow network to "
                "Anthropic' as the driver of TOOL_LIMIT; 'gpt-5.4 "
                "model drift'; 'most important methodological "
                "finding of Phase 1'; 'most honest agent-eval "
                "baseline'. (v2 corrections, post Codex review) "
                "'Apple--0 ep 2 SITE_RENDER / empty React shell' "
                "(trace showed first bp open returned prices); "
                "'SITE_RENDER x2' (only x1, Wolfram). (v3 "
                "corrections, post M1.6b validation re-run — see "
                "m1_6b_validation field) 'Wolfram Alpha--0 "
                "SITE_RENDER' (with clean bp session the agent "
                "answers in 2-10 commands; the SVG-path-coordinate "
                "wall was a symptom of polluted DOM state, not a "
                "property of Wolfram); 'BBC News--5 REF_STALE' "
                "(clean bp session reaches the article correctly; "
                "the HTTP 500 was either session-pollution or a "
                "real coincident outage — data doesn't distinguish, "
                "but Wolfram's parallel reversal makes pollution "
                "the stronger hypothesis); 'Apple--0 "
                "CHROME_TAB_POLLUTION' (with clean bp session Apple "
                "STILL fails both epochs at max_turns=12, with the "
                "agent having the pricing answer at msg 7 but "
                "refusing to commit — this is a NEW AGENT_BEHAVIOR "
                "failure class); '1/1/3 split' as the final "
                "attribution (the validated split is 4/1 "
                "CTP/AGENT_BEHAVIOR). Each correction round — "
                "trace-read v1, trace-read v2, live-run v3 — "
                "tightened the picture by forcing one more source "
                "of evidence to be consulted."
            ),
            "cost_framing": (
                "All token totals are in the raw ModelUsage sense "
                "(input + output + reasoning + cache_read + "
                "cache_write). caliper v0.1 does NOT track dollars; "
                "see methodology.md principle 5 implementation note "
                "for the rationale."
            ),
            "cache_hit_rate_anthropic": (
                "Sonnet buckets show cache_hit_rate = 0.0 because "
                "Inspect AI's default does not enable Anthropic "
                "prompt caching and the text-protocol solver doesn't "
                "add cache_control to messages. gpt-5.4's 73.9% is "
                "OpenAI's automatic prefix cache kicking in for "
                "prefixes >= 1024 tokens. A future milestone tagged "
                "with SKILL.md caching will wire up Anthropic prompt "
                "caching; until then the asymmetry is a property of "
                "the defaults, not a regression."
            ),
        },
        "reproduce_check": {
            "all_models_pass_in_range": all(
                _model_section(run)["v8_comparison"]["pass_in_range"] for run in runs
            ),
            "apple_minus_3_epoch_2_failed": False,
            "max_turns_limit_still_enforced": True,
            "failure_mode_distribution": (
                "5 TOOL_LIMIT failures on Sonnet run, distributed "
                "across different samples than v8 (not Apple--3)"
            ),
            "m1_6b_validation_outcome": (
                "M1.6b subset re-run (5 failed samples x 2 epochs) "
                "with bp session prologue fix: 8/10 pass. "
                "CHROME_TAB_POLLUTION validated for 4 of 5 v9 "
                "failures. Apple--0 still fails with clean bp "
                "state — new AGENT_BEHAVIOR failure class. "
                "Projected full-baseline Sonnet pass rate with "
                "fix: ~23/24, effectively matching v8 anchor. See "
                "m1_6b_validation field for per-sample details."
            ),
        },
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: build_v9.py <gpt-5.4-log-filename>\n\n"
            "The script expects the GPT-5.4 baseline log to be passed "
            "explicitly so it matches what was actually produced in "
            "the M1.6-E run.",
            file=sys.stderr,
        )
        return 2

    gpt_log_filename = sys.argv[1]
    runs = list(_RUNS) + [
        RunInput(
            model="openai/gpt-5.4",
            log_filename=gpt_log_filename,
            notes=(
                "GPT-5.4 full v8 baseline, same environment as the "
                "Sonnet run above. Observed behaviour: 24/24 lazy, "
                "uniform 'single-turn training-data answer' pattern "
                "(message_count=3, commands_run=0, mean 930 uncached "
                "input tokens vs Sonnet's 96,840 on the same tasks). "
                "This is a BEHAVIOURAL description, not a causal "
                "claim — M1.6 does not establish whether the cause "
                "is model drift, OpenAI Responses adapter context "
                "changes, or prompt/training-data interaction. See "
                "docs/lessons-learned.md M1.6 section for the "
                "corrected attribution."
            ),
        ),
    ]

    v9 = build_v9(runs)
    out_path = _REPO / "baselines" / "v9.json"
    out_path.write_text(json.dumps(v9, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path}")
    print(f"  schema: {v9['schema_version']}")
    print(f"  commit: {v9['caliper_commit']}")
    print(f"  models: {list(v9['models'].keys())}")
    for model, section in v9["models"].items():
        pass_info = section["overall"]["pass_count"]
        print(
            f"  {model}: {pass_info}/{section['overall']['n_runs']} pass, "
            f"in-range={section['v8_comparison']['pass_in_range']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
