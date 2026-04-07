# Chatbot maxTurns Strategy A/B: A Worked Scenario

> A complete experimental design for using caliper to answer one of
> the open questions in chatbot agent infrastructure: **what should
> happen when an agent's tool-call budget runs out?**

This document captures a full case study of using caliper for a
scenario that's structurally different from browser-pilot. It exists
as the second worked example proving caliper's abstractions are
general — the first being browser-pilot itself.

If you're reading this to decide whether to implement the scenario,
the executive summary is: **this is the second consumer caliper was
designed for, and it's the strongest possible test of generality
because the "subject under test" is termination strategy rather than
agent capability.**

---

## 1. The design problem

Agent frameworks need a `maxTurns` mechanism: a limit on how many
"model → tool → model → tool" iterations a single query can do
before the loop is forcibly terminated. This is uncontroversial.

What's controversial is **what should happen when the limit is hit**.
The agent is mid-task. It has called some tools but hasn't yet
synthesized a final answer. The user is waiting. The conversation
state is incomplete.

### How current frameworks handle this

After surveying a dozen agent frameworks (LangChain, LangGraph,
LlamaIndex, smolagents, AutoGen, CrewAI, Pydantic AI, OpenAI Agents
SDK, Vercel AI SDK, Claude Agent SDK, Anthropic Messages API), the
patterns sort into 9 categories, ranked here from worst to best for
chatbot UX:

| # | Pattern | Representative implementations | chatbot fit |
|---|---|---|---|
| 1 | Throw exception / return constant string | LangChain default, LangGraph, LlamaIndex, Pydantic AI | ❌ disaster |
| 2 | Silent stop, return whatever's there | AutoGen NEVER mode, Vercel AI SDK default | ⚠️ half-sentence |
| 3 | Force-finalize: extra LLM call with tools disabled | LangChain `generate` (broken), smolagents `provide_final_answer`, CrewAI `_handle_max_iterations_exceeded` | ✅ theoretical gold standard |
| 4 | Soft warning: inject "N turns left" into context | No mainstream impl; LlamaIndex feature request #12209 | ⚠️ model often ignores |
| 5 | Resumable pause | Anthropic `pause_turn` (protocol level), LangGraph interrupt, Cursor "Continue?" | ✅ cleanest for chatbot |
| 6 | Adaptive budget | Claude Agent SDK resume, Cursor Continue button | ⚠️ better for IDE than chatbot |
| 7 | Per-tool-class budgets | Pydantic AI per-tool retries | ⚠️ complex, low value for chatbot |
| 8 | Token / dollar / time budget instead of turns | Anthropic `max_budget_usd`, OpenAI Assistants, ChatGPT Deep Research time window | ✅ user-friendly mental model |
| 9 | Multi-stage hybrid (warn → finalize → hard cut) | No mainstream impl | ✅ theoretically optimal |

### Why this is unsolved

The reason there's no single dominant pattern is that **the trade-offs
have never been measured**. You can argue from first principles that
ForceFinalize is "the right answer" — but does it actually produce
better user experience than HardCut on real tasks? Does the model
fabricate when forced to finalize without enough information? What's
the cost overhead of the extra LLM call relative to the UX gain?

Nobody has answers. The few attempts (LangChain's `early_stopping_method="generate"`,
OpenAI Agents SDK error handlers) are either broken or treat
force-finalize as an undocumented escape hatch left to the developer.

### The 10 design questions

When designing this mechanism for a real chatbot product, you need
answers to:

1. **Should the limit signal be an exception or a structured state?**
2. **Should we do force-finalize?** If so, with `tool_choice="none"`
   or just with prompt instructions?
3. **How should the finalize prompt be written?** How to avoid
   fabrication while still producing a coherent answer?
4. **Does soft warning ("N turns remaining") actually work?** Or do
   models ignore it?
5. **What unit is the limit?** Turns / tokens / dollars / wall-clock?
6. **How is the post-limit state exposed to the user?** Hidden
   entirely (consumer chatbots) or surfaced as an error?
7. **How does sub-agent limit propagation work?** Should the parent
   agent see anything?
8. **Should the post-limit state be resumable?**
9. **Should the turn count invariant be preserved across error
   recovery paths?**
10. **What's the right default value?** (Industry median is 15–25;
    autonomous agents go to 200–500.)

Of these, **caliper can give data-driven answers to 7** (questions
1, 2, 3, 4, 5, 8, 10). The other 3 (6, 7, 9) are architectural
choices that A/B testing can't decide for you.

---

## 2. Why this is a perfect caliper use case

Two reasons make this scenario uniquely well-suited to caliper:

**First**, no one has measured this before. The 9 patterns above are
described in research and engineering blog posts, but nobody has
**run them head-to-head on the same task set with the same scoring
methodology**. Whatever caliper produces will be the first
quantitative comparison of chatbot termination strategies.

**Second**, it's structurally different from any other agent eval
problem. The standard benchmark question is "can the agent do this
task?". The maxTurns question is "**when the agent can't finish in
time, how does it fail?**" The subject under test is the agent
infrastructure, not the agent.

If caliper can handle this scenario cleanly, it proves the framework's
abstractions are general — they work for "test the strategy" as well
as "test the agent". This is the strongest possible dogfood.

---

## 3. The mental model shift

Before designing the experiment, internalize this difference from
browser-pilot:

| Aspect | browser-pilot | chatbot maxTurns |
|---|---|---|
| **Subject under test** | The agent (its tools, prompts, model) | The agent **infrastructure** (termination strategy) |
| **Task design goal** | "The agent should be able to solve this" | "The agent **must** hit the budget; how does it fail?" |
| **Verification** | Binary: did it complete? | Multi-dimensional: was the user-facing output good? |
| **Variables under test** | 1 (agent config) | 3 (strategy × maxTurns value × model) |
| **Tasks per variant** | Each variant tries the same tasks | Same |
| **Number of strategies** | 1 (the agent) | 9 (the termination strategies) |
| **Mock vs real tools** | Real (the agent must work in the wild) | **Mock** (real network adds noise that masks strategy differences) |

The key insight: in browser-pilot we held the task constant and varied
the agent. In chatbot maxTurns we hold both the task **and** the agent
constant, and vary the *meta-policy* that determines what happens
when the agent runs out of budget.

This is why a new caliper concept is needed: **`Strategy` as a
first-class variable**, not a parameter on Solver but its own axis
in the experimental matrix.

---

## 4. Experimental design

### 4.1 Mock tasks (5–8 tasks designed to force the budget limit)

The first principle: **tasks must always hit the budget**. If a task
sometimes finishes naturally and sometimes hits the limit, you can't
isolate strategy effects. Mock tools make this controllable.

Each task is constructed so that:
- The "correct" path requires K tool calls (we know K because we
  designed the mocks)
- The budget is set to K-2 or K-3 (forcing the limit)
- Mock tools return realistic-looking data (not lorem ipsum)
- The agent has to actually reason about results

#### Task A: research-grants

```yaml
id: research_grants
goal: |
  Find three climate adaptation grants for Southeast Asia. For each,
  give the amount and deadline.
mock_tools:
  - search_grants_db(query, page) → 5 results per page, 50 total grants
  - get_grant_details(grant_id) → full info for one grant
  - check_eligibility(grant_id, region) → bool
  - filter_by_status(grant_id, status="open") → bool
expected_path:
  - search page 1 (5 results) → 1 turn
  - search page 2 (5 more) → 1 turn
  - get_details × 5 candidates → 5 turns
  - check_eligibility × 5 → 5 turns
  - filter_by_status × 3 → 3 turns
  total_min_turns: 15
budget_for_test: 8  # forces budget hit
failure_mode_when_cut: "agent has data but no synthesis"
```

#### Task B: debug-auth-chain

```yaml
id: debug_auth
goal: |
  Find why the /api/auth flow returns 401 for some users and propose
  a fix.
mock_tools:
  - read_file(path) → 8 relevant files available
  - search_logs(query) → log lines
  - check_config(key) → config values
expected_path:
  - read auth.py, middleware.py, session.py, jwt.py → 4 turns
  - search_logs for 401 → 2 turns
  - check_config jwt secret rotation → 2 turns
  - synthesize → 1 turn
  total_min_turns: 9
budget_for_test: 6
failure_mode_when_cut: "agent read code but didn't reach conclusion"
```

#### Task C: comparative-shopping

```yaml
id: shopping_compare
goal: |
  Find a 15-inch laptop under $1500 with at least 16GB RAM and 4+ star
  reviews. Compare three candidates.
mock_tools:
  - search_products(query, filters) → product list
  - get_specs(product_id) → detailed specs
  - get_reviews(product_id) → review summary
expected_path:
  - search → 1 turn
  - get_specs × 5 candidates → 5 turns
  - get_reviews × 5 → 5 turns
  - filter and compare → 1 turn
  total_min_turns: 12
budget_for_test: 7
failure_mode_when_cut: "agent compared partial data, no decision"
```

#### Task D: multi-source-summarize

```yaml
id: multi_source
goal: |
  Read these 3 emails, summarize the action items, and draft a
  consolidated response.
mock_tools:
  - read_email(email_id) → full email content
  - extract_action_items(text) → list of items
  - draft_response(items, recipient) → draft text
expected_path:
  - read_email × 3 → 3 turns
  - extract_action_items × 3 → 3 turns
  - draft_response → 1 turn
  - revise → 1 turn
  total_min_turns: 8
budget_for_test: 5
failure_mode_when_cut: "agent read emails but didn't synthesize"
```

#### Task E: knowledge-worker-compound

```yaml
id: compound_task
goal: |
  Look up customer order #12345, check the inventory for the items,
  and if anything is back-ordered, draft a customer notification.
mock_tools:
  - lookup_order(order_id) → order with items
  - check_inventory(item_id) → stock count
  - get_customer(customer_id) → customer info
  - draft_notification(template, data) → notification text
expected_path:
  - lookup_order → 1 turn
  - check_inventory × 4 items → 4 turns
  - get_customer → 1 turn
  - draft_notification → 1 turn
  - review and adjust → 1 turn
  total_min_turns: 8
budget_for_test: 5
failure_mode_when_cut: "agent gathered data but didn't draft notification"
```

### Why these 5 tasks?

Each task creates a **different "shape of incompleteness"** when cut
off. That's important: a strategy that finalizes well on one shape
might fail on another.

| Task | What's missing when cut at budget |
|---|---|
| research-grants | Synthesis (data collected, no aggregation) |
| debug-auth | Conclusion (evidence read, no diagnosis) |
| shopping | Decision (candidates compared, no choice) |
| multi-source | Cross-source integration |
| compound | Final deliverable (steps done, no draft) |

The 5 tasks span the natural failure modes. If a strategy works on
all 5, it's robust. If it works on only some, you've found a
trade-off worth knowing about.

### 4.2 Strategies (9 implementations)

Each strategy is a class implementing a `LimitStrategy` protocol:

```python
from typing import Protocol
from dataclasses import dataclass

@dataclass
class Termination:
    kind: str  # "natural" | "hard_cut" | "finalized" | "paused" | "extended"
    text: str | None  # final user-facing text
    metadata: dict  # strategy-specific info

class LimitStrategy(Protocol):
    name: str
    description: str

    def before_turn(self, turn_idx: int, max_turns: int, state) -> None:
        """Hook for soft-warning injection. Default: noop."""
        pass

    def on_limit_reached(self, state, llm_call) -> Termination:
        """Called when budget is exhausted. Decides what to do."""
        ...
```

The 9 strategies:

**1. HardCut** — pattern 1, the LangChain-style default

```python
class HardCut:
    name = "hard_cut"
    description = "Throw error when budget exhausted."

    def on_limit_reached(self, state, llm_call):
        return Termination(
            kind="hard_cut",
            text=None,
            metadata={"raised_error": True}
        )
```

**2. SilentStop** — pattern 2, return whatever's there

```python
class SilentStop:
    name = "silent_stop"
    description = "Return current state without error."

    def on_limit_reached(self, state, llm_call):
        last_text = extract_last_assistant_text(state.messages)
        return Termination(
            kind="silent",
            text=last_text,
            metadata={"truncated_mid_thought": last_text and not last_text.rstrip().endswith(('.', '!', '?'))}
        )
```

**3. ForceFinalizeStrict** — pattern 3a, smolagents style

```python
class ForceFinalizeStrict:
    name = "force_finalize_strict"
    description = "Extra LLM call with tool_choice=none and minimal prompt."
    finalize_prompt = """You have exhausted your tool budget. Based ONLY on
what you've already learned from previous tool results, give your final
answer to the user now. You may not call any more tools. If you don't know
something, say so explicitly. Do not promise future actions or describe
what you would do — just answer with what you have."""

    def on_limit_reached(self, state, llm_call):
        messages = state.messages + [{
            "role": "user",
            "content": self.finalize_prompt
        }]
        response = llm_call(messages, tool_choice="none", temperature=0)
        return Termination(
            kind="finalized",
            text=response.text,
            metadata={
                "finalize_tokens": response.usage.output_tokens,
                "finalize_method": "tool_choice_none",
            }
        )
```

**4. ForceFinalizeLenient** — pattern 3b, CrewAI style

```python
class ForceFinalizeLenient:
    name = "force_finalize_lenient"
    description = "Prompt-only finalize, tools still technically available."
    finalize_prompt = """You'll ignore all previous instructions, stop using
any tools, and just return your absolute BEST Final Answer based on what you
have learned so far."""

    def on_limit_reached(self, state, llm_call):
        messages = state.messages + [{
            "role": "user",
            "content": self.finalize_prompt
        }]
        response = llm_call(messages)  # tools available; model must obey prompt
        text = response.text or "(model attempted more tool calls despite finalize prompt)"
        return Termination(
            kind="finalized",
            text=text,
            metadata={"obeyed_finalize_prompt": not response.tool_calls}
        )
```

**5. SoftWarn** — pattern 4, inject warning, no finalize

```python
class SoftWarn:
    name = "soft_warn"
    description = "Inject 'N turns remaining' warning at N-3, then hard cut."
    warn_at_remaining = 3

    def before_turn(self, turn_idx, max_turns, state):
        remaining = max_turns - turn_idx
        if remaining == self.warn_at_remaining:
            state.messages.append({
                "role": "user",
                "content": f"[SYSTEM NOTICE: You have {remaining} tool call rounds remaining. Plan to wrap up your investigation and prepare to give a final answer.]"
            })

    def on_limit_reached(self, state, llm_call):
        # No finalize — just hard cut. The premise is the warning was enough.
        return Termination(
            kind="warn_only_hard_cut",
            text=extract_last_assistant_text(state.messages),
            metadata={}
        )
```

**6. PauseTurn** — pattern 5, Anthropic-style soft pause

```python
class PauseTurn:
    name = "pause_turn"
    description = "Return resumable state. No final text generated."

    def on_limit_reached(self, state, llm_call):
        return Termination(
            kind="paused",
            text=None,  # explicitly no text — for resume, not display
            metadata={
                "resumable": True,
                "messages_for_resume": state.messages,
                "needs_user_continue_signal": True,
            }
        )
```

Note: PauseTurn is **n/a for direct UX comparison** because it doesn't
produce final text. It's measured on a different axis (whether resume
works correctly).

**7. AdaptiveBudget** — pattern 6, extend if making progress

```python
class AdaptiveBudget:
    name = "adaptive_budget"
    description = "Extend budget if agent appears to be making progress."
    extension_amount = 5
    max_extensions = 2

    def on_limit_reached(self, state, llm_call):
        extensions = state.metadata.get("extensions", 0)
        if extensions < self.max_extensions and self._making_progress(state):
            state.metadata["extensions"] = extensions + 1
            state.metadata["extended_max_turns"] = state.max_turns + self.extension_amount
            return Termination(
                kind="extended",
                text=None,
                metadata={"continue_loop_with_more_budget": True}
            )
        # Otherwise hard cut after extensions exhausted
        return Termination(
            kind="hard_cut_after_extension",
            text=None,
            metadata={"final_extensions_used": extensions}
        )

    def _making_progress(self, state) -> bool:
        # Heuristic: did the last 3 turns each call new tools and get results?
        recent = state.messages[-6:]  # last 3 turns = 3 user + 3 assistant
        return len([m for m in recent if "tool_calls" in m]) >= 3
```

**8. TokenBudget** — pattern 8, switch unit from turns to tokens

```python
class TokenBudget:
    name = "token_budget"
    description = "Use token count as the budget instead of turn count."
    max_tokens_total = 50_000

    def on_limit_reached(self, state, llm_call):
        # Same as HardCut — the budget is just measured differently
        return Termination(
            kind="token_budget_exhausted",
            text=extract_last_assistant_text(state.messages),
            metadata={"total_tokens_used": state.metadata.get("total_tokens", 0)}
        )

    # The actual integration is in the solver loop:
    # if total_tokens > self.max_tokens_total: trigger on_limit_reached
```

**9. MultiStage** — pattern 9, hybrid: warn → finalize → fallback

```python
class MultiStage:
    name = "multi_stage"
    description = "Soft warn at N-3, force-finalize at N, hard-cut as fallback."

    def before_turn(self, turn_idx, max_turns, state):
        if turn_idx == max_turns - 3:
            state.messages.append({
                "role": "user",
                "content": "[SYSTEM: 3 tool rounds remaining. Begin wrapping up.]"
            })

    def on_limit_reached(self, state, llm_call):
        # Stage 1: try force-finalize
        try:
            messages = state.messages + [{
                "role": "user",
                "content": "Budget exhausted. Provide your final answer based on what you have. No more tools."
            }]
            response = llm_call(messages, tool_choice="none", temperature=0)
            if response.text:
                return Termination(
                    kind="multi_stage_finalized",
                    text=response.text,
                    metadata={"stage_reached": "finalize"}
                )
        except Exception:
            pass

        # Stage 2: fallback to extracting whatever text exists
        last_text = extract_last_assistant_text(state.messages)
        return Termination(
            kind="multi_stage_fallback",
            text=last_text,
            metadata={"stage_reached": "fallback"}
        )
```

### 4.3 The UX judge (multi-dimensional scorer)

This is the most novel component. Standard caliper judges return
binary correct/incorrect. The chatbot UX judge returns **5 dimensions
of UX quality**, each scored 0–2.

**Why multi-dimensional**: a single score collapses trade-offs.
ForceFinalizeStrict might score high on completeness but low on
no_fabrication (the model invents details when forced to finalize).
A single number would hide this. The 5 dimensions surface the
trade-off explicitly.

**The 5 dimensions**:

1. **completeness** (0/1/2)
   - 0: cut off mid-thought, ends in "let me check..."
   - 1: partial but coherent, ends naturally
   - 2: fully formed conclusion

2. **usefulness** (0/1/2)
   - 0: nothing actionable
   - 1: partial info, user needs a follow-up
   - 2: addresses the core ask

3. **honesty** (0/1/2)
   - 0: claims to have done things it didn't
   - 1: vague or slightly overclaims
   - 2: accurate about what was found

4. **no_fabrication** (0/1/2) ← the most important
   - Cross-references final text against actual tool_results in history
   - 0: invents specific data the bot never received
   - 1: borderline (general claims that could be inferred)
   - 2: only cites things actually retrieved

5. **no_error_surface** (0/1/2)
   - 0: user sees raw error / "max turns reached" / stack trace
   - 1: technical wording but not raw
   - 2: completely user-friendly

**Aggregate**: Total UX score = sum / 10, range 0.0–1.0.

**The scorer implementation sketch**:

```python
@scorer(metrics=[mean_score(), per_dimension_breakdown()])
def chatbot_ux_judge(judge_model: str = "claude-sonnet-4-6"):

    UX_PROMPT = """You are evaluating the user-facing experience of a chatbot
that hit its tool call budget mid-task.

User asked: {goal}

Chatbot's interaction history:
- Tool calls made: {n_tool_calls}
- Tool results received: {n_tool_results}
- Termination kind: {termination_kind}

Tool results the bot actually saw (for fabrication check):
{tool_results_summary}

Final user-facing text the chatbot produced:
---
{final_text}
---

Score 0-2 on each dimension (0=bad, 1=borderline, 2=good):

1. completeness — natural ending or cut mid-thought?
2. usefulness — actionable information for the user?
3. honesty — accurately reflects what the bot did?
4. no_fabrication — only cites things actually in the tool history?
5. no_error_surface — no raw error visible to user?

Respond with ONLY a JSON object:
{{"completeness": N, "usefulness": N, "honesty": N, "no_fabrication": N,
"no_error_surface": N, "reason": "<2 sentence explanation>"}}"""

    async def score(state, target):
        prompt = UX_PROMPT.format(
            goal=state.input,
            n_tool_calls=count_tool_calls(state.messages),
            n_tool_results=count_tool_results(state.messages),
            termination_kind=state.metadata.get("termination_kind", "unknown"),
            tool_results_summary=summarize_tool_results(state.messages, max_chars=2000),
            final_text=state.metadata.get("final_text") or "(no text)",
        )
        response = await call_judge_llm(prompt, judge_model, temperature=0)
        scores = parse_ux_json(response)
        overall = sum(scores.values()) / (5 * 2)  # normalize 0..1
        return Score(
            value=overall,
            metadata={"per_dimension": scores, "judge_reason": scores.get("reason", "")},
        )

    return score
```

The key technical detail: **the judge sees the tool results history**,
so it can detect fabrication by cross-referencing the final text
against what was actually retrieved. This is the "lazy detection"
principle from browser-pilot, applied to a multi-dimensional context.

### 4.4 Phased rollout

The full Cartesian matrix is expensive:

```
9 strategies × 5 tasks × 6 maxTurns values × 3 models × 3 runs = 2,430 runs
```

At ~$0.05/run that's ~$120, plus several hours of wall time. Don't
do this in one go. Use focused phases:

#### Phase A: Strategy comparison (cheap, highest information)

```
1 model (Sonnet) × 1 maxTurns (=10, intentionally tight)
× 5 tasks × 9 strategies × 3 runs
= 135 runs ≈ $7, ~1 hour
```

**Output**: A 9-strategy × 5-dimension matrix. Identify the top 3–5
strategies by overall UX score.

#### Phase B: Cross-model validation

```
3 models × 1 maxTurns × 5 tasks × top 5 strategies × 3 runs
= 225 runs ≈ $15
```

**Output**: Confirmation that Phase A's winners hold on Haiku and
GPT-5.4, not just Sonnet. Detect any "this strategy only works on
Sonnet" effects.

#### Phase C: maxTurns sweep

```
1 model (Sonnet) × 6 maxTurns values × 5 tasks × top 3 strategies × 3 runs
= 270 runs ≈ $15
```

**Output**: UX-vs-budget curves for the finalist strategies. Reveals
the "knee" of the curve — where increasing the budget stops helping.
**This directly answers question #10 (default value)**.

#### Total

```
Phase A + B + C = 630 runs ≈ $40
```

Roughly 5–8 hours of wall clock for the full series. Compared to the
2,430-run Cartesian, this is 75% cheaper while answering all the
same questions.

#### Phase D (optional): Real-network validation

Replace mock tools with real network calls for the top strategy on
1–2 tasks. Verify the lab finding holds when real-world variance is
introduced. Adds $30–50 and is the only way to bridge from "the
mock test passes" to "production behavior matches."

---

## 5. Sample output (what the report would look like)

After running Phase A:

```
========================================================================
Phase A Report — Strategy Comparison
Model: claude-sonnet-4-6, maxTurns=10, 5 tasks × 3 runs = 135 runs
========================================================================

Per-strategy 5-dimensional UX breakdown
─────────────────────────────────────────────────────────────────────────
Strategy              Overall  Compl   Usef    Hon    NoFab   NoErr  $/run
HardCut                 0.21    0.12   0.31   0.42   0.95    0.10   $0.018
SilentStop              0.45    0.28   0.51   0.55   0.92    0.95   $0.020
ForceFinalizeStrict     0.78    0.85   0.71   0.62 ⚠ 0.61 ⚠  0.95   $0.024
ForceFinalizeLenient    0.72    0.81   0.65   0.78   0.72    0.95   $0.025
SoftWarn (only)         0.51    0.45   0.58   0.61   0.85    0.92   $0.022
SoftWarn+Finalize       0.81    0.88   0.74   0.71   0.65    0.95   $0.026
PauseTurn               n/a     n/a    n/a    n/a    n/a     0.95   $0.018
AdaptiveBudget          0.85    0.92   0.79   0.74   0.71    0.92   $0.041
MultiStage              0.83    0.89   0.77   0.72   0.69    0.95   $0.027

Per-task detail (top 4 strategies)
─────────────────────────────────────────────────────────────────────────
                       research debug   shop   summ   compound
ForceFinalizeStrict     0.81    0.55    0.85   0.79   0.90
ForceFinalizeLenient    0.78    0.65    0.72   0.76   0.71
SoftWarn+Finalize       0.85    0.75    0.83   0.82   0.80
AdaptiveBudget          0.88    0.82    0.85   0.85   0.85    ← most consistent
MultiStage              0.85    0.78    0.84   0.83   0.85

Honesty dimension (lower = more fabrication risk)
─────────────────────────────────────────────────────────────────────────
ForceFinalizeStrict: 0.62 ⚠
  → Most fabrication on debug task: invents root causes when forced
ForceFinalizeLenient: 0.78
  → Slightly safer; tools available means less "made up" pressure
SoftWarn+Finalize: 0.71
MultiStage: 0.72
AdaptiveBudget: 0.74

Variance analysis (CV across 3 runs per cell)
─────────────────────────────────────────────────────────────────────────
Most stable: AdaptiveBudget (CV 8%) — deterministic extension behavior
Least stable: ForceFinalizeStrict (CV 24%) — fabrication is itself stochastic
```

This single report directly addresses 7 of the 10 design questions:

| Q | Answer from this data |
|---|---|
| 1 (exception vs state?) | HardCut scores 0.21 — definitely use state, not exception |
| 2 (force-finalize?) | Yes; both ForceFinalize variants beat HardCut/SilentStop. Prefer Lenient over Strict on honesty grounds. |
| 3 (finalize prompt design?) | Strict prompt (`tool_choice=none`) creates fabrication pressure; Lenient prompt is safer but sometimes ignored. There's a real tension. |
| 4 (does soft warning work?) | SoftWarn alone scores 0.51 — slightly better than SilentStop (0.45), much worse than Finalize. **Empirical evidence: warnings have a small effect, not zero, not enough on their own.** |
| 5 (budget unit?) | TokenBudget would need its own runs; not in this matrix |
| 8 (resume?) | PauseTurn is n/a on this UX axis — needs a resume-completion test instead |
| 10 (default value?) | Phase C's curves give this directly |

---

## 6. New caliper components needed

This scenario requires extending caliper beyond what browser-pilot
needed. Estimated additions:

| Component | Lines | Purpose |
|---|---|---|
| `caliper.strategies.limit.*` | ~700 (9 × ~80) | The 9 LimitStrategy implementations |
| `caliper.solvers.limit_strategy_agent` | ~150 | New solver: agent loop with strategy hooks |
| `caliper.scorers.chatbot_ux_judge` | ~120 | 5-dimensional UX scorer |
| `caliper.mocks.*` | ~200 | Mock tool framework |
| `caliper.datasets.limit_tasks.*` | ~300 | The 5 mock tasks |
| `caliper.report.multi_dim` | ~100 | Per-dimension breakdown reports |
| `caliper.report.strategy_matrix` | ~80 | Strategy × task matrix |
| `caliper.report.budget_curve` | ~80 | UX vs maxTurns sweep curves |
| **Total** | **~1,730** | |

**~1,730 lines** is significant — comparable to the entire core
caliper library. It's because the chatbot scenario is essentially a
**second consumer** with its own task semantics, scorer semantics, and
report semantics.

Critically, however, ~80% of caliper's existing primitives are
**reused unchanged**:
- JSON verdict parser (anti-substring-bug)
- Variance enforcement (N≥2 default)
- Cost / cache tracking
- Bucket aggregation infrastructure
- A/B comparison reports
- Test set as code discipline

Only the **scenario-specific** pieces are new. This is the dogfooding
test of caliper's design.

---

## 7. What caliper can't answer (be honest)

Caliper has limits even on this scenario it's well-suited for. List
them upfront so users know what to expect.

**1. Real human feedback is irreplaceable**

The LLM judge's UX dimensions correlate with human judgment but
aren't human judgment. For shipping a chatbot product, you eventually
need a user study. Caliper provides a *proxy for UX*, not UX itself.

**2. Generalization across user populations is limited**

Tasks designed by us reflect "failure modes we thought of". Real users
will hit failure modes we didn't think of. Mock task design is
necessarily incomplete.

**3. Strategy implementation bugs aren't auto-detected**

If the ForceFinalize implementation has a bug (wrong prompt, wrong
parameter), caliper measures the buggy version's score — but doesn't
distinguish "this strategy is bad" from "this implementation is bad".
Trace inspection is still required.

**4. Production stack constraints aren't modeled**

Streaming token output, concurrent retries, distributed timeouts,
production rate limits — none of these are in caliper's model. You're
testing the policy logic, not the production system that runs it.

**5. "Optimal default" is a range, not a number**

Phase C produces a UX-vs-budget curve. Picking a point on it requires
a product decision: how much UX gain is worth a unit of cost? Caliper
gives the curve; the product manager picks the point.

**6. Sub-agent / parent propagation needs new task structure**

Question 7 in the design questions list (sub-agent limit propagation)
requires a parent-with-sub-agent task type that caliper doesn't have
yet. This would be a Phase 4+ extension.

---

## 8. Phased implementation plan

Don't build all 1,730 lines at once. Incremental phases:

### Step 0: Implement the 9 strategies as plain Python

**No caliper involvement.** Pure Python library that translates the 9
patterns into executable code.

- **Goal**: prove every pattern can be written, find ambiguities
- **Output**: ~700 lines, 9 LimitStrategy classes, no tests
- **Estimate**: 1–2 days

### Step 1: Minimum viable closed loop

- 1 mock task (research-grants)
- 3 strategies (HardCut, ForceFinalizeStrict, MultiStage — most differentiated)
- chatbot_ux_judge implementation
- 1 model × 1 budget × 1 task × 3 strategies × N=3 = 9 runs

**Goal**: validate that the entire mechanism runs end-to-end. Verify
the judge produces sensible scores. Inspect 9 traces in `inspect view`.

**Output**: First viable strategy comparison, even if tiny.

**Estimate**: 2–3 days

### Step 2: Phase A complete

Add the remaining strategies and tasks. Run the full Phase A matrix
(135 runs).

**Goal**: produce the 9-strategy × 5-dimension matrix shown in
section 5.

**Estimate**: 1 day (mostly waiting for runs)

### Step 3: Phase B + Phase C

Cross-model validation and budget sweep.

**Goal**: final report ready for publication / internal review.

**Estimate**: 2 days

**Total: ~1–2 weeks** to produce a publishable comparison report.

---

## 9. Why this scenario benefits caliper itself

The chatbot maxTurns scenario isn't just a use case for caliper —
it's a **test of caliper's design**. Building it will reveal:

1. **Whether `Strategy` deserves to be a first-class concept** in
   caliper core (currently it's specific to this scenario)
2. **Whether the UX judge's 5 dimensions** are the right number
   (too few? too many? overlap?)
3. **Whether mock tools** are scenario-specific or general enough
   to promote to caliper core (browser-pilot might also benefit)
4. **Whether multi-dimensional report formats** are clear or
   confusing — the existing single-value reports might not generalize
5. **Whether the abstractions hold** when the "subject under test"
   shifts from agent to infrastructure

These findings inform caliper v0.2. **The chatbot scenario is the
second dogfood, and a more challenging one than browser-pilot.**

---

## 10. The publication value

If this scenario is implemented and run, the deliverable is **a
report no one else has produced**:

> "The First Empirical Comparison of Chatbot maxTurns Termination
> Strategies"
>
> 9 strategies × 5 task patterns × 3 models × N=3 runs.
> Total cost: $40. Total wall time: half a day.
>
> Findings:
> - HardCut is empirically a disaster (UX 0.21)
> - ForceFinalizeStrict trades completeness for honesty (0.85 vs 0.62)
> - SoftWarn alone has small effect (+0.06 over silent), confirms
>   research-community suspicion that "soft warnings don't work" is
>   overstated
> - AdaptiveBudget is the most consistent across task types but
>   70% more expensive
> - The optimal default budget is 12, with diminishing returns above 15

This is publishable in a blog, a technical report, or a research
paper. **It also serves as caliper's strongest marketing material**
because it answers a question that every team building agent products
has, but no one has actually measured.

Browser-pilot's v8 baseline is interesting to people who use
browser-pilot. The chatbot maxTurns report is interesting to **every
team that ships an LLM agent**, which is a much wider audience.

---

## Summary

This document captures a complete experimental design for using
caliper to investigate chatbot maxTurns termination strategies. The
key points:

1. **Subject under test is the strategy**, not the agent
2. **Tasks must force the budget limit** (mock tools required)
3. **Judge is multi-dimensional**, not binary
4. **9 strategies, 5 tasks, 3 models, 3 phases** = ~$40 of compute
   for a publishable comparison
5. **Caliper needs ~1,700 lines of new components**, but reuses 80%
   of its existing primitives unchanged
6. **7 of 10 design questions** can be answered with hard data; the
   other 3 are architectural and require human judgment
7. **The implementation roadmap is incremental**: 9 runs → 135 runs
   → 630 runs across 4 steps over 1–2 weeks

Whether or not this scenario is implemented immediately, it serves
as a worked example of how to think about caliper-style evaluation
in a non-browser-pilot context, and as a north star for the kinds
of questions caliper is designed to answer.
