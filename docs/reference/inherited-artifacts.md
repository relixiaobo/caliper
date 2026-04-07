# Inherited Artifacts (Verbatim)

This document contains the **exact code, prompts, and tables** that
caliper Phase 1 must port from `browser-pilot/tests/agent/run.py`. They
were debugged across 8 weeks of iteration and contain non-obvious bug
fixes — port them verbatim, do not "improve" them on the fly.

If you change one of these, you are taking responsibility for re-running
the self-evaluation tests in Phase 2. Default to copying first, refining
later.

> **Source of truth at time of extraction**: `browser-pilot/tests/agent/run.py`
> as of commit `2c2f135` (the v8 stale-ref tolerance commit).

---

## 1. The v8 stale-reference tolerant judge prompt

This is the most important artifact in the project. Every change to it
must pass the self-evaluation suite (`tests/self_eval/judge_quality.py`)
before merge.

The format string takes two variables: `task['goal']` and `ref` (the
reference answer string), plus the agent's actual answer.

```python
judge_prompt = f"""You are grading whether a web agent correctly answered a question about a live website.

Task: {task['goal']}
Reference answer (may be outdated — the benchmark was authored in 2023/2024): {ref}
Agent's answer: {agent_answer}

Grading rules:
- The agent visited the live site NOW. If the task asks for "latest", "current",
  "recent", or "most recent" data, the agent's answer reflects today's reality.
  The reference may be stale. Accept factually-plausible current answers even when
  the specific product version/name/date differs from the reference.
  Example: reference says "MacBook Air M2 $1099"; agent says "MacBook Air M5 $1099" —
  this is CORRECT (Apple moved to M5, prices held). Similarly iPhone 15 → iPhone 17.
- For non-time-sensitive tasks (pronunciations, math, historical facts, fixed
  documentation like "Enterprise has X GB more than Team"), the agent's answer must
  match the reference's substantive content.
- The agent's wording may differ but the substance must match.
- Partial answers covering the key information count as correct.
- An answer that describes how to do it without actually having done it is INCORRECT.
- An answer that fabricates details the agent couldn't have verified is INCORRECT.
- An empty or evasive answer is INCORRECT.

Respond with ONLY a JSON object on a single line:
{{"verdict": "correct"}} or {{"verdict": "incorrect", "reason": "<short reason>"}}"""
```

**Judge call configuration**:

```python
# The judge LLM call uses these specific parameters:
judge_response, _, _ = call_llm(
    model=model,                          # any chat model
    messages=[{"role": "user", "content": judge_prompt}],
    system="You are an evaluator. Respond only with the JSON object requested.",
    temperature=0,                        # deterministic
)
```

The minimal eval-focused system prompt + temperature=0 are essential for
reproducibility. **Do not use the agent's SKILL.md as the judge's system
prompt** — that was the source of several confusing bugs in v6.

### History

- v0–v4: prompt asked for "CORRECT or INCORRECT" as a single word; parser
  used `"CORRECT" in response` which silently flipped 38% of verdicts
  (`"CORRECT" in "INCORRECT"` is `True`).
- v5: switched to JSON output + INCORRECT-first fallback parser. Revealed
  the historical bug.
- v6: added `temperature=0` and minimal evaluator system prompt for
  determinism.
- v8: added the stale-reference tolerance rules. Compare bucket pass rate
  jumped Sonnet 3/6 → 5/6, gpt-5.4 2/6 → 6/6.

---

## 2. The anti-substring-bug verdict parser

This is the **single most important line of code in caliper**. The
substring-bug regression test (`tests/unit/test_json_verdict_parser.py`)
must enforce that this parser is correct.

```python
import json
import re

def parse_judge_verdict(response: str) -> tuple[bool, str]:
    """Parse {"verdict": "correct|incorrect", "reason": "..."} from judge response.

    Falls back to keyword check (with INCORRECT-first ordering) if JSON
    parsing fails — defensive against models that ignore the format spec.
    """
    # Try JSON first
    text = response.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find first { and matching }
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        verdict = str(obj.get("verdict", "")).lower().strip()
                        reason = str(obj.get("reason", "")).strip()
                        if verdict in ("correct", "incorrect"):
                            return verdict == "correct", reason or verdict
                    except json.JSONDecodeError:
                        pass
                    break

    # Fallback: keyword check (INCORRECT first to avoid substring trap)
    upper = response.upper()
    if "INCORRECT" in upper:
        return False, "fallback parse"
    if "CORRECT" in upper:
        return True, "fallback parse"
    return False, f"unparseable: {response[:60]}"
```

### Mandatory unit tests

Any caliper port of this parser must pass these tests (write them in
`tests/unit/test_json_verdict_parser.py` before writing the parser):

```python
import pytest
from caliper.scorers.json_verdict import parse_judge_verdict

def test_json_correct():
    verdict, _ = parse_judge_verdict('{"verdict":"correct"}')
    assert verdict is True

def test_json_incorrect():
    verdict, _ = parse_judge_verdict('{"verdict":"incorrect","reason":"empty"}')
    assert verdict is False

def test_json_with_markdown_fences():
    verdict, _ = parse_judge_verdict('```json\n{"verdict":"correct"}\n```')
    assert verdict is True

def test_keyword_correct_fallback():
    verdict, _ = parse_judge_verdict("CORRECT")
    assert verdict is True

def test_keyword_incorrect_fallback_NOT_substring_bug():
    """REGRESSION TEST for v0-v4 substring bug.

    The previous parser checked `"CORRECT" in response`, which returns
    True for "INCORRECT". Any future change to parse_judge_verdict must
    keep this test passing.
    """
    verdict, _ = parse_judge_verdict("INCORRECT")
    assert verdict is False, "INCORRECT should NOT be parsed as correct (substring trap)"

def test_keyword_incorrect_in_sentence():
    verdict, _ = parse_judge_verdict("This answer is INCORRECT because of X.")
    assert verdict is False

def test_garbage_input_defaults_to_false():
    verdict, _ = parse_judge_verdict("foo bar baz")
    assert verdict is False

def test_empty_input():
    verdict, _ = parse_judge_verdict("")
    assert verdict is False
```

The test named `test_keyword_incorrect_fallback_NOT_substring_bug` is
the most important regression test in the project.

---

## 3. Lazy detection: the observation command set

The lazy detector marks a run as `lazy_failure` if the agent produced an
ANSWER without ever calling a "real observation" command. The set of
commands that count as observation is fixed:

```python
OBSERVATION_COMMANDS = {
    "read",         # bp read
    "snapshot",     # bp snapshot
    "eval",         # bp eval
    "screenshot",   # bp screenshot
    "tabs",         # bp tabs
    "cookies",      # bp cookies
    "locate",       # bp locate
}
```

**Why these and not others**:

- `open` is *navigation*, not observation — the agent goes somewhere
  but hasn't looked at content yet
- `click`, `type`, `keyboard`, `press` are *actions* that change page
  state but don't return content the agent can read
- `upload`, `auth`, `frame` are *control plane* operations
- The 7 commands above are the ones that return data the agent can
  reason about

### Lazy detection logic

```python
def detect_lazy(state) -> bool:
    """An agent that gave an answer without observing the page is lazy.

    The runner auto-opens task.start_url before the agent loop, so the
    LLM does see an initial snapshot. Lazy detection specifically catches
    the case where the agent ignored that snapshot, made up an answer
    from training data, and never called any observation command in the
    loop itself.
    """
    has_answer = bool(state.get("agent_answer", ""))
    observed = state.get("observed_page", False)
    return has_answer and not observed
```

In the caliper port, `observed_page` becomes a metadata flag set by the
solver whenever it executes a command in `OBSERVATION_COMMANDS`.

### Generalizing to other CLI tools

The set above is `bp`-specific. The `text_protocol_agent` solver in
caliper takes `observation_commands` as a parameter so each CLI gets its
own set:

| Tool | Observation commands |
|---|---|
| `bp` (browser-pilot) | `{"read", "snapshot", "eval", "screenshot", "tabs", "cookies", "locate"}` |
| `cu` (computer-pilot) | `{"snapshot", "screenshot", "ocr", "tell"}` (TBD when computer-pilot adapter is written) |

---

## 4. The bp command extractor (text protocol parser)

The text protocol agent extracts `bp xxx` lines from LLM free-text
output. Multi-line eval scripts (with unclosed quotes spanning lines)
are handled specially.

```python
def extract_bp_commands(text: str) -> list[str]:
    """Extract bp commands from LLM response."""
    commands = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip().strip("`")
        if line.startswith("bp "):
            # Handle multi-line eval with unclosed quotes
            if line.count("'") % 2 == 1 or line.count('"') % 2 == 1:
                multi = [line]
                quote_char = "'" if line.count("'") % 2 == 1 else '"'
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip()
                    if next_line.strip().startswith("`"):
                        next_line = next_line.strip().strip("`")
                    multi.append(next_line)
                    if quote_char in next_line:
                        break
                    i += 1
                commands.append("\n".join(multi))
            else:
                commands.append(line)
        i += 1
    return commands
```

In the caliper port, the prefix `"bp "` becomes a parameter (so the same
extractor works for `cu`, `kubectl`, etc.):

```python
def extract_commands(text: str, cli_prefix: str) -> list[str]:
    # Same logic, but `line.startswith(cli_prefix + " ")`
    ...
```

### Required unit tests

```python
def test_extract_simple():
    cmds = extract_commands("bp open https://example.com", "bp")
    assert cmds == ["bp open https://example.com"]

def test_extract_multiple_per_response():
    text = """Let me do this:
bp open https://example.com
bp read
"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 2

def test_extract_multiline_eval_single_quotes():
    text = """bp eval 'function() {
  return 42;
}'"""
    cmds = extract_commands(text, "bp")
    assert len(cmds) == 1
    assert "function" in cmds[0]
    assert "return 42" in cmds[0]

def test_extract_strips_backticks():
    text = "`bp open https://example.com`"
    cmds = extract_commands(text, "bp")
    assert cmds == ["bp open https://example.com"]
```

---

## 5. ANSWER multi-line extractor

The agent writes its final answer in an `ANSWER:` block. The block can
be on a single line or span multiple lines until a terminator.

```python
def extract_answer(text: str) -> str | None:
    """Extract ANSWER: from LLM response.

    Handles three patterns:
      1. ANSWER: text on same line              → just that text
      2. ANSWER: <newline> markdown block       → collect until DONE/FAIL/end
      3. ANSWER: short text + more on next line → collect both, joined
    """
    lines = text.split("\n")
    answer_idx = None
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("ANSWER:"):
            answer_idx = i
            break

    if answer_idx is None:
        return None

    # Collect everything from ANSWER: through end of message,
    # stopping at terminal markers
    parts = []
    first_line_rest = lines[answer_idx].strip()[7:].strip()
    if first_line_rest:
        parts.append(first_line_rest)

    blank_run = 0
    for j in range(answer_idx + 1, len(lines)):
        l = lines[j].rstrip()
        stripped = l.strip()

        # Stop at terminal markers
        if stripped in ("DONE", "FAIL"):
            break
        if stripped.startswith("```"):  # code fence boundary - keep parsing
            continue

        if not stripped:
            blank_run += 1
            # Allow up to 2 consecutive blanks within markdown bullets
            if blank_run >= 3 and parts:
                break
            continue

        blank_run = 0
        parts.append(stripped)

    if not parts:
        return None
    # Join with single space; collapse to keep it on one line for fuzzy match
    answer = " ".join(parts)
    # Cap excessively long answers
    if len(answer) > 2000:
        answer = answer[:2000]
    return answer
```

### History

This function went through 3 iterations during v3-v6:
- **v3 first version**: only captured text on the same line as `ANSWER:`
  → empty answers when the agent put `ANSWER:` on its own line followed
  by content
- **v3 second version**: collected subsequent non-empty lines, stopped at
  first blank → cut off markdown bulleted lists
- **v5 final version** (above): tracks blank-run count, allows up to 2
  blanks, stops at terminal markers, caps at 2000 chars

---

## 6. Compact snapshot text formatter

This is a runner-side optimization, not part of the bp CLI. When the
solver receives a snapshot result from the bp daemon, it reformats the
JSON into a compact bracketed text form before adding it to the
conversation. This was the v3 change that cut total token usage by 24%.

```python
import json

def truncate_snapshot(output: str, max_elements: int = 30) -> str:
    """Reformat snapshot output for the LLM context.

    Snapshots dominate token usage because each one persists in conversation
    history for every subsequent turn. We:
      1. Convert verbose JSON elements ({"ref":1,"role":"link","name":"X"})
         to compact text ([1] link "X") — about 60% smaller per element.
      2. Truncate to max_elements (default 30) since most useful elements
         are listed first.
      3. For non-snapshot results (eval, read, etc.), cap raw output length.
    """
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return output[:3000]

    if not isinstance(data, dict):
        return output[:3000]

    # bp read result — keep title/url/text but cap text length
    if "text" in data and "elements" not in data:
        text = data.get("text", "")
        if len(text) > 3000:
            text = text[:3000] + "... [truncated]"
        return f'page: {data.get("title", "")}\nurl: {data.get("url", "")}\n---\n{text}'

    # snapshot result
    if "elements" in data:
        elements = data["elements"]
        total = len(elements)
        shown = elements[:max_elements]
        lines = []
        title = data.get("title", "")
        url = data.get("url", "")
        if title or url:
            lines.append(f"page: {title} | {url}")
        for el in shown:
            ref = el.get("ref")
            role = el.get("role", "")
            name = el.get("name", "")
            line = f'[{ref}] {role} "{name}"'
            if "value" in el and el["value"]:
                line += f' value="{el["value"]}"'
            if el.get("checked"):
                line += " checked"
            lines.append(line)
        if total > max_elements:
            lines.append(f"... ({total - max_elements} more elements)")
        return "\n".join(lines)

    # eval result, error, etc.
    return output[:3000]
```

---

## 7. Pricing table (per million tokens, USD)

Pinned to **2026-01**. Update this table when providers change pricing,
and add a `pricing_date` field to baselines so old runs remain
interpretable.

```python
# caliper/metrics/pricing.py
from dataclasses import dataclass

@dataclass
class ModelPricing:
    input: float          # $/Mtok for fresh input
    output: float         # $/Mtok for output
    cache_read: float     # $/Mtok for cache reads (Anthropic ~10% of input)
    cache_write: float    # $/Mtok for cache creation (Anthropic ~125% of input)
    reasoning: float = 0  # $/Mtok for reasoning tokens (gpt-5 family)

PRICING = {
    "claude-opus-4-6":          ModelPricing(input=15.0, output=75.0, cache_read=1.5,   cache_write=18.75),
    "claude-sonnet-4-6":        ModelPricing(input=3.0,  output=15.0, cache_read=0.3,   cache_write=3.75),
    "claude-haiku-4-5":         ModelPricing(input=1.0,  output=5.0,  cache_read=0.1,   cache_write=1.25),
    "claude-haiku-4-5-20251001":ModelPricing(input=1.0,  output=5.0,  cache_read=0.1,   cache_write=1.25),
    "gpt-5.4":                  ModelPricing(input=5.0,  output=15.0, cache_read=0.625, cache_write=5.0,  reasoning=15.0),
}

PRICING_DATE = "2026-01"
```

### Cost calculation

```python
def cost_usd(model: str, usage) -> float:
    """Compute USD cost from a usage object.

    `usage` should have these fields (Inspect AI exposes them):
        input_tokens          — fresh input tokens
        cache_read_tokens     — Anthropic cache_read_input_tokens (charged at cache_read rate)
        cache_creation_tokens — Anthropic cache_creation_input_tokens (charged at cache_write rate)
        output_tokens
        reasoning_tokens      — gpt-5.x reasoning model output

    Returns: dollars (float)
    """
    p = PRICING[model]
    return (
        usage.input_tokens          * p.input        +
        usage.cache_read_tokens     * p.cache_read   +
        usage.cache_creation_tokens * p.cache_write  +
        usage.output_tokens         * p.output       +
        usage.reasoning_tokens      * p.reasoning
    ) / 1_000_000
```

### Cache hit rate

```python
def cache_hit_rate(usage) -> float:
    """Fraction of input tokens served from cache (0.0 to 1.0).

    A high hit rate means the cacheable prefix is stable across runs.
    A SKILL.md edit invalidates the prefix and drops this to 0% for the
    next run, then it climbs back up.
    """
    served_from_cache = usage.cache_read_tokens
    total_input = (
        usage.input_tokens +
        usage.cache_read_tokens +
        usage.cache_creation_tokens
    )
    return served_from_cache / total_input if total_input else 0.0
```

---

## 8. LLM client quirks (per provider)

### Anthropic

- Supports `cache_control` on message blocks. The default behavior in
  Inspect AI is `cache-prompt: auto` which enables caching when tools
  are present.
- Returns `usage.cache_read_input_tokens` and
  `usage.cache_creation_input_tokens` separately from `usage.input_tokens`.
- Reasoning models (Opus 4.5+, Sonnet 4.6+) return reasoning content in
  a separate content block; tokens count toward `output_tokens`.

### OpenAI

- `gpt-5.x` reasoning models **reject the `temperature` parameter** —
  any non-default value causes a 400 error. The runner code handles this:

  ```python
  if temperature is not None and not model.startswith("gpt-5"):
      kwargs["temperature"] = temperature
  ```

- `gpt-5.x` returns `prompt_tokens_details.cached_tokens` for prompt
  cache hits (different field name from Anthropic).
- Reasoning tokens are exposed as `usage.completion_tokens_details.reasoning_tokens`.

When porting `call_llm` to caliper, both quirks must be preserved.

---

## 9. Failure attribution categories

Every failed sample should be tagged with one of these. The bucket
report aggregates failures by tag.

```python
FAILURE_TAGS = {
    "TOOL_BUG":     "The tool returned the wrong thing (not what the agent asked for)",
    "TOOL_LIMIT":   "The tool can't do what's needed; gap in capability not bug",
    "SKILL_GAP":    "The LLM doesn't know the right way to use the tool",
    "LLM_LIMIT":    "The model isn't capable enough for this task",
    "LLM_BEHAVIOR": "Lazy / inconsistent / fabricating; capable but won't",
    "SITE_ISSUE":   "External service problem (Cloudflare, rate limit, real outage)",
    "REF_STALE":    "Benchmark reference answer is outdated",
    "NOISE":        "Single failure that doesn't reproduce on retry",
}
```

In Inspect AI terms, this becomes a metadata field on each failed
Sample. Custom report aggregators (`caliper report --by failure_tag`)
group by it.

---

## 10. Things to NOT port

Some patterns from `run.py` should be **dropped** in the caliper port,
not preserved:

- ❌ `subprocess.run` directly — use Inspect AI's tool/sandbox abstraction
- ❌ The `_truncate_snapshot` JSON-string parsing as a runner concern —
  in caliper this becomes a *solver* concern, not a runner concern
- ❌ The hardcoded `model = "claude-sonnet-4-6"` default — caliper
  should accept it as a parameter from the eval config
- ❌ `print()` for progress reporting — use Inspect AI's logging
- ❌ Manual `test-results/agent-*.json` writing — Inspect AI handles
  this with `.eval` log files
- ❌ The bucket aggregation written into `v7_baseline.py` as inline
  code — in caliper this is a separate `report/bucket.py` module

The principle: **port the LLM-facing logic verbatim** (judge prompt,
parser, observation set). **Reimplement the orchestration** to fit
Inspect AI's idioms.
