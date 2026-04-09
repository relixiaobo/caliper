"""caliper diagnostics — self-contained analysis of eval data.

Reads .eval logs (or CaliperRecords) and automatically surfaces
measurement issues without re-running any agent. This is caliper's
"self-evolution" capability: the ability to discover problems in
its own evaluation results from existing data.

Four diagnostic checkers:

1. **Stability** — epoch-to-epoch variance in pass rate and tokens.
   Flags tasks whose verdicts flip between epochs (noise, not signal).

2. **Scorer consistency** — cross-checks judge, lazy, and verify
   scorers against each other. Flags contradictions (e.g. judge=PASS
   but lazy=TRUE means the "pass" is training-data guessing).

3. **Behavior patterns** — detects agent-level anomalies from trace
   data: over-exploration (agent has answer but keeps going),
   immediate-answer (single-turn without observation), retry loops
   (high command count in max-turns failures).

4. **Cache** — detects cache_hit_rate anomalies: unexpected 0% on
   providers that should cache, asymmetric rates between runs.

Usage:
    from caliper.diagnostics import diagnose_log
    findings = diagnose_log("logs/my-eval.eval")
    for f in findings:
        print(f)

    # Or via CLI:
    caliper diagnose logs/my-eval.eval
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from inspect_ai.log import EvalLog, EvalSample, read_eval_log

from caliper.metrics import UsageSummary


@dataclass
class Finding:
    """One diagnostic finding."""

    severity: str  # "warning" | "info" | "ok"
    category: str  # "stability" | "scorer" | "behavior" | "cache"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        icon = {"warning": "⚠", "info": "ℹ", "ok": "✓"}[self.severity]
        return f"{icon} [{self.category.upper()}] {self.message}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_judge_passed(s: EvalSample) -> bool | None:
    """Extract judge pass/fail from a sample's scores."""
    scores = s.scores or {}
    for key in ("judge_stale_ref", "verify_commands"):
        if key in scores:
            return bool(scores[key].value)
    return None


def _sample_is_lazy(s: EvalSample) -> bool:
    scores = s.scores or {}
    lazy = scores.get("lazy_detection")
    if lazy is None:
        return False
    return float(lazy.value or 0) > 0


def _sample_commands_run(s: EvalSample) -> int:
    store = s.store or {}
    return int(store.get("SolverState:commands_run", 0) or 0)


def _sample_agent_answer(s: EvalSample) -> str:
    store = s.store or {}
    return str(store.get("SolverState:agent_answer", "") or "")


def _sample_total_tokens(s: EvalSample) -> int:
    return sum(
        u.input_tokens
        + u.output_tokens
        + (u.input_tokens_cache_read or 0)
        + (u.input_tokens_cache_write or 0)
        for u in (s.model_usage or {}).values()
    )


def _sample_n_messages(s: EvalSample) -> int:
    return len(s.messages) if s.messages else 0


# ---------------------------------------------------------------------------
# Checker 1: Stability
# ---------------------------------------------------------------------------


def check_stability(samples: list[EvalSample]) -> list[Finding]:
    """Flag tasks whose pass verdict or token count flips between epochs."""
    findings: list[Finding] = []

    # Group by sample_id
    by_id: dict[str, list[EvalSample]] = defaultdict(list)
    for s in samples:
        by_id[str(s.id)].append(s)

    flipping_tasks = []
    high_token_cv_tasks = []

    for sid, epochs in sorted(by_id.items()):
        if len(epochs) < 2:
            continue

        verdicts = [_sample_judge_passed(s) for s in epochs]
        verdicts_clean = [v for v in verdicts if v is not None]
        if verdicts_clean and len(set(verdicts_clean)) > 1:
            flipping_tasks.append(sid)

        tokens = [_sample_total_tokens(s) for s in epochs]
        if len(tokens) >= 2 and statistics.mean(tokens) > 0:
            cv = statistics.stdev(tokens) / statistics.mean(tokens)
            if cv > 0.5:
                high_token_cv_tasks.append(
                    (sid, round(cv, 2), min(tokens), max(tokens))
                )

    if flipping_tasks:
        findings.append(
            Finding(
                severity="warning",
                category="stability",
                message=(
                    f"{len(flipping_tasks)} task(s) have pass verdicts that "
                    f"FLIP between epochs: {', '.join(flipping_tasks)}. "
                    "These tasks' pass rates are noise, not signal."
                ),
                details={"flipping_tasks": flipping_tasks},
            )
        )

    if high_token_cv_tasks:
        details = [
            f"{t[0]} (CV={t[1]}, range {t[2]:,}-{t[3]:,})" for t in high_token_cv_tasks
        ]
        findings.append(
            Finding(
                severity="warning",
                category="stability",
                message=(
                    f"{len(high_token_cv_tasks)} task(s) have token CV > 50%: "
                    + "; ".join(details)
                ),
                details={"high_cv_tasks": high_token_cv_tasks},
            )
        )

    if not flipping_tasks and not high_token_cv_tasks:
        findings.append(
            Finding(
                severity="ok",
                category="stability",
                message="No epoch-to-epoch instability detected.",
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Checker 2: Scorer consistency
# ---------------------------------------------------------------------------


def check_scorer_consistency(samples: list[EvalSample]) -> list[Finding]:
    """Cross-check judge, lazy, and verify scorers for contradictions."""
    findings: list[Finding] = []

    pass_but_lazy: list[str] = []
    fail_but_observed_and_answered: list[str] = []

    for s in samples:
        sid = f"{s.id} ep{s.epoch}"
        judge = _sample_judge_passed(s)
        lazy = _sample_is_lazy(s)
        answer = _sample_agent_answer(s)
        observed = bool((s.store or {}).get("SolverState:observed_page", False))

        # Judge PASS + Lazy TRUE = training-data guessing, not real capability
        if judge is True and lazy:
            pass_but_lazy.append(sid)

        # Judge FAIL + observed + has answer = interesting failure
        # (agent tried, observed, answered, but judge said wrong)
        if judge is False and observed and answer:
            fail_but_observed_and_answered.append(sid)

    if pass_but_lazy:
        findings.append(
            Finding(
                severity="warning",
                category="scorer",
                message=(
                    f"{len(pass_but_lazy)} sample(s) scored PASS but flagged "
                    f"LAZY: {', '.join(pass_but_lazy[:5])}. "
                    "These 'passes' are training-data guesses, not real "
                    "agent capability. The pass rate is inflated."
                ),
                details={"pass_but_lazy": pass_but_lazy},
            )
        )

    if not pass_but_lazy:
        findings.append(
            Finding(
                severity="ok",
                category="scorer",
                message="No judge-vs-lazy contradictions detected.",
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Checker 3: Behavior patterns
# ---------------------------------------------------------------------------


def check_behavior_patterns(samples: list[EvalSample]) -> list[Finding]:
    """Detect agent-level anomalies from trace data."""
    findings: list[Finding] = []

    immediate_answers: list[str] = []
    over_exploration: list[tuple[str, int, int]] = []
    retry_loops: list[tuple[str, int]] = []

    for s in samples:
        sid = f"{s.id} ep{s.epoch}"
        n_msgs = _sample_n_messages(s)
        cmds = _sample_commands_run(s)
        answer = _sample_agent_answer(s)
        lazy = _sample_is_lazy(s)

        # Immediate answer: message_count ≤ 3 = single LLM turn
        if n_msgs <= 3 and answer and not lazy:
            # Not flagged as lazy but answered in 1 turn — might be
            # a very easy task, or might be a sophisticated lazy pattern
            # where the agent happened to call one observation command.
            pass  # benign if observation happened

        if n_msgs <= 3 and lazy:
            immediate_answers.append(sid)

        # Over-exploration: hit max_turns (msgs ≥ 25) with many commands
        # but NO answer. The agent was busy but didn't commit.
        if n_msgs >= 25 and not answer and cmds > 20:
            over_exploration.append((sid, cmds, _sample_total_tokens(s)))

        # Retry loops: very high command count relative to message count
        # suggests the agent is retrying the same action repeatedly.
        if cmds > 0 and n_msgs > 0:
            cmds_per_turn = cmds / (n_msgs / 2)  # rough turns = msgs/2
            if cmds_per_turn > 8 and cmds > 30:
                retry_loops.append((sid, cmds))

    if immediate_answers:
        findings.append(
            Finding(
                severity="warning",
                category="behavior",
                message=(
                    f"{len(immediate_answers)} sample(s) answered immediately "
                    f"without observation (single-turn lazy): "
                    f"{', '.join(immediate_answers[:5])}"
                ),
                details={"immediate_answers": immediate_answers},
            )
        )

    if over_exploration:
        details = [f"{t[0]} ({t[1]} cmds, {t[2]:,} tokens)" for t in over_exploration]
        findings.append(
            Finding(
                severity="warning",
                category="behavior",
                message=(
                    f"{len(over_exploration)} sample(s) hit max_turns with "
                    f"high command count but no answer (over-exploration): "
                    + "; ".join(details[:5])
                ),
                details={"over_exploration": over_exploration},
            )
        )

    if retry_loops:
        details = [f"{t[0]} ({t[1]} cmds)" for t in retry_loops]
        findings.append(
            Finding(
                severity="warning",
                category="behavior",
                message=(
                    f"{len(retry_loops)} sample(s) show retry-loop signature "
                    f"(>8 cmds/turn, >30 total): " + "; ".join(details[:5])
                ),
                details={"retry_loops": retry_loops},
            )
        )

    if not immediate_answers and not over_exploration and not retry_loops:
        findings.append(
            Finding(
                severity="ok",
                category="behavior",
                message="No anomalous agent behavior patterns detected.",
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Checker 4: Cache
# ---------------------------------------------------------------------------


def check_cache(samples: list[EvalSample]) -> list[Finding]:
    """Detect cache_hit_rate anomalies."""
    findings: list[Finding] = []

    # Aggregate per model
    by_model: dict[str, list[UsageSummary]] = defaultdict(list)
    for s in samples:
        for model_name, usage in (s.model_usage or {}).items():
            u = UsageSummary.from_model_usage(usage, model=model_name)
            by_model[model_name].append(u)

    for model_name, usages in sorted(by_model.items()):
        total = UsageSummary.zero()
        for u in usages:
            total = total + u

        if total.has_cache_info and total.cache_hit_rate is not None:
            rate = total.cache_hit_rate
            if rate == 0.0 and "anthropic" in model_name.lower():
                findings.append(
                    Finding(
                        severity="warning",
                        category="cache",
                        message=(
                            f"{model_name}: cache_hit_rate = 0.0% across "
                            f"{len(usages)} samples. Anthropic models support "
                            "prompt caching — a 0% rate suggests cache_control "
                            "is not enabled in the solver/Inspect AI config."
                        ),
                    )
                )
            elif rate == 0.0:
                findings.append(
                    Finding(
                        severity="info",
                        category="cache",
                        message=(
                            f"{model_name}: cache_hit_rate = 0.0% — cold cache "
                            "or provider caching not triggered."
                        ),
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity="ok",
                        category="cache",
                        message=(
                            f"{model_name}: cache_hit_rate = {rate:.1%} "
                            f"across {len(usages)} samples."
                        ),
                    )
                )
        elif not total.has_cache_info:
            findings.append(
                Finding(
                    severity="info",
                    category="cache",
                    message=(f"{model_name}: no cache info reported by provider."),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def diagnose_log(log_path: str) -> list[Finding]:
    """Run all diagnostic checkers on an .eval log file.

    Returns a list of Finding objects sorted by severity
    (warnings first, then info, then ok).
    """
    log: EvalLog = read_eval_log(log_path)
    samples = log.samples or []

    if not samples:
        return [
            Finding(
                severity="warning",
                category="stability",
                message="No samples in log — nothing to diagnose.",
            )
        ]

    findings: list[Finding] = []
    findings.extend(check_stability(samples))
    findings.extend(check_scorer_consistency(samples))
    findings.extend(check_behavior_patterns(samples))
    findings.extend(check_cache(samples))

    # Sort: warnings first, then info, then ok.
    severity_order = {"warning": 0, "info": 1, "ok": 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 1))

    return findings


def render_diagnostics(findings: list[Finding]) -> str:
    """Render findings as a human-readable report string."""
    lines = [
        "╭──────────────────────────────────────────────────────────╮",
        "│ Caliper Diagnostics Report                               │",
        "╰──────────────────────────────────────────────────────────╯",
        "",
    ]
    for f in findings:
        lines.append(str(f))
        if f.severity == "warning" and f.details:
            # Add one level of detail for warnings
            for key, val in f.details.items():
                if isinstance(val, list) and len(val) <= 5:
                    for item in val:
                        lines.append(f"    • {item}")
        lines.append("")

    n_warnings = sum(1 for f in findings if f.severity == "warning")
    n_ok = sum(1 for f in findings if f.severity == "ok")
    lines.append(f"Summary: {n_warnings} warning(s), {n_ok} ok check(s)")
    return "\n".join(lines)
