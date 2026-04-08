"""Normalised observability view over Inspect AI's ``ModelUsage``.

Inspect AI supports ~27 model-provider backends, and each one populates
a different subset of ``ModelUsage`` fields. This module produces ONE
cross-provider view so caliper's report layer can aggregate per-bucket
usage without branching on which fields the underlying provider
happened to report.

## Provider support matrix (Inspect AI 0.3.205)

Verified by reading each provider adapter under
``inspect_ai/model/_providers/`` and noting which ``ModelUsage``
fields it assigns:

| Provider                        | input | output | cache_read | cache_write | reasoning |
| ------------------------------- | :---: | :----: | :--------: | :---------: | :-------: |
| anthropic (direct)              |  ✅   |   ✅   |     ✅     |     ✅      |    ✅     |
| openai (Chat Completions)       |  ✅   |   ✅   |     ✅     |     ❌      |    ✅     |
| openai_responses (gpt-5 family) |  ✅   |   ✅   |     ✅     |     ❌      |    ✅     |
| google (Gemini)                 |  ✅   |   ✅   |     ❌     |     ❌      |    ✅     |
| bedrock (Anthropic on AWS)      |  ✅   |   ✅   |     ❌     |     ❌      |    ❌     |
| grok (xAI)                      |  ✅   |   ✅   |     ✅     |     ❌      |    ✅     |
| perplexity                      |  ✅   |   ✅   |     ❌     |     ❌      |    ✅     |
| azureai                         |  ✅   |   ✅   |     ❌     |     ❌      |    ❌     |
| mistral                         |  ✅   |   ✅   |     ❌     |     ❌      |    ❌     |
| groq                            |  ✅   |   ✅   |     ❌     |     ❌      |    ❌     |
| together                        |  ✅   |   ✅   |     ❌     |     ❌      |    ❌     |
| hf / mockllm / local runners    |  ✅   |   ✅   |     ❌     |     ❌      |    ❌     |
| cloudflare / fireworks /        |  ✅   |   ✅   |  ⚠ upstream | ❌     |  ⚠ upstream |
|   openrouter / ollama / vllm /  |       |        |            |             |           |
|   sambanova / sglang            |       |        |            |             |           |

Key observations that shape the design:

1. **Only Anthropic (direct) reports ``input_tokens_cache_write``.**
   Every other provider — including Anthropic via Bedrock, which
   routes through the AWS Converse API — reports ``None``. OpenAI's
   prompt caching is automatic/free with no caller-visible "creation"
   event. Caliper exposes the field but downstream reports should
   not expect it outside Anthropic runs.

2. **``cache_hit_rate`` is the canary for prompt-prefix regressions.**
   A SKILL.md edit invalidates the cached prefix and the next run's
   cache_hit_rate drops to near zero while total tokens look roughly
   unchanged. Catching this is the main reason this module exists.

3. **``usage.total_cost`` is always ``None`` in 0.3.205.** Inspect AI
   has a ``ModelCost`` schema and a ``compute_model_cost`` function,
   but the bundled model YAML data ships with zero ``cost:`` entries.
   Caliper deliberately does NOT duplicate a pricing table: the
   iteration workflow this module supports is same-model comparison
   where fewer tokens = strictly cheaper, and cross-provider dollar
   comparison is out of scope for M1.2.

## Honesty flags

Inspect AI uses ``None`` to signal "this provider does not report
this field". We preserve that distinction via the ``has_cache_info``
and ``has_reasoning_info`` boolean flags. This matters because a
Bedrock run's ``cache_read_tokens == 0`` has a different meaning
than an Anthropic run's ``cache_read_tokens == 0``:

- Anthropic: "I checked, there really was no cache hit"
- Bedrock:   "I don't know, the API didn't expose it"

The report layer must render the provider-silent case as ``—``,
not ``0.0``, so it's not mistaken for a cache regression.

## What this module deliberately does not compute

- **Dollar cost.** Same-model iteration doesn't need it; cross-model
  comparison is out of scope for M1.2.
- **"Effective tokens" single-number metric.** Would require
  provider-specific cache-discount weights (Anthropic cache_write is
  1.25×; OpenAI has no cache_write; Gemini caches differently). No
  universal formula exists that isn't silently wrong for somebody.
- **Aggregation across whole logs.** ``caliper.report.*`` in M1.4
  consumes this module to produce bucket reports and A/B diffs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from inspect_ai.model import ModelUsage

# ---------------------------------------------------------------------------
# Provider-detection helper
# ---------------------------------------------------------------------------

# Inspect AI's openai_responses adapter (used for gpt-5 / o-series /
# codex / etc.) has a known information loss: when the OpenAI API
# returns ``cached_tokens=0`` for a real cold cache hit, the adapter
# normalises that to ``input_tokens_cache_read=None`` (see
# inspect_ai/model/_providers/openai_responses.py:216). Downstream we
# can't distinguish "cold cache" from "provider doesn't report cache"
# without external context.
#
# This regex matches model names that route through the Responses
# adapter, mirroring Inspect AI's responses_preferred logic in
# inspect_ai/model/_providers/openai.py:138-147:
#
#     responses_preferred = (
#         self.is_o_series() or self.is_codex() or self.is_gpt_5()
#     )
#
# Limitations: this is a name-based heuristic. Inspect AI also routes
# to Responses when ``background=True``, when image-output modalities
# are requested, or when the user passes ``responses_api=True``
# explicitly. Those runtime triggers aren't visible from a stored
# ``ModelUsage``, so caliper's reinterpretation will miss them in
# those edge cases. The fallback (``has_cache_info=False``) is the
# safer rendering, so missing those is not catastrophic.
_O_SERIES_LEADING = re.compile(r"^o\d+")
_O_SERIES_INNER = re.compile(r"o\d+")


def _uses_openai_responses_adapter(model: str) -> bool:
    """True iff Inspect AI's openai_responses adapter would handle this
    model name (and therefore the cache_read=None-as-cold-cache bug
    applies). Mirrors ``responses_preferred`` in inspect_ai 0.3.205.
    """
    name = model.rsplit("/", 1)[-1].lower()
    if "gpt-5" in name:
        return True
    if "codex" in name:
        return True
    # o-series: matches "o1", "o3-mini", "o4-preview" etc.
    if _O_SERIES_LEADING.match(name):
        return True
    if "gpt" not in name and _O_SERIES_INNER.search(name):
        return True
    return False


@dataclass(frozen=True)
class UsageSummary:
    """One model's normalised token usage for one sample (or one call).

    All token fields are non-negative ints — provider-reported ``None``
    is coerced to ``0`` for arithmetic, but the absence is preserved
    in the ``has_*_info`` flags so downstream reports can distinguish
    "provider reported zero" from "provider did not report".
    """

    # Always populated by every provider Inspect AI supports.
    input_tokens: int
    output_tokens: int

    # Populated only when the provider reports them; otherwise 0 here
    # with the corresponding has_*_info flag set to False.
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int

    # Honesty flags — True iff the provider populated the field at
    # all (even if its value was zero). A False here means "unknown",
    # not "zero". See module docstring for the Bedrock vs Anthropic
    # example of why this distinction matters.
    has_reasoning_info: bool
    has_cache_info: bool

    # Total input tokens contributed by samples whose cache state was
    # actually reported by the provider. For a single ``ModelUsage``,
    # this equals ``total_input_tokens`` when ``has_cache_info`` is
    # True and 0 otherwise. After ``__add__`` aggregation, this is
    # the sum over only the cache-aware operands — used as the
    # ``cache_hit_rate`` denominator so a mixed bucket (Bedrock
    # silent + Anthropic aware) doesn't dilute the rate by counting
    # the silent provider's input tokens as "should have hit but
    # didn't".
    cache_aware_input_tokens: int

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------

    @property
    def total_input_tokens(self) -> int:
        """Every input token counted, cached or not.

        Equals ``input_tokens + cache_read_tokens + cache_write_tokens``.
        This is the denominator for ``cache_hit_rate``.
        """
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        """All tokens the model touched: inputs (cached or not) + output.

        Matches Inspect AI's own ``ModelUsage.total_tokens`` for
        providers that compute it, but we derive rather than trust
        so the number is reproducible from the other fields.
        """
        return self.total_input_tokens + self.output_tokens

    @property
    def uncached_input_tokens(self) -> int:
        """Input tokens that were NOT served from cache.

        This is ``input_tokens + cache_write_tokens``. Cache-write
        tokens are tokens the provider had to read fresh AND
        additionally pay to write into the cache — they were never
        served from cache. Including them here is what makes this
        accessor expose the SKILL.md-invalidation spike: after a
        prefix change, the next Anthropic call reports a large
        ``cache_write_tokens`` (the new prefix being seeded), and
        ``uncached_input_tokens`` jumps even though
        ``total_input_tokens`` stays roughly constant.

        On non-Anthropic providers ``cache_write_tokens`` is always 0
        and this reduces to ``input_tokens``.
        """
        return self.input_tokens + self.cache_write_tokens

    @property
    def cache_hit_rate(self) -> float | None:
        """Fraction of input served from cache (0.0 to 1.0), computed
        only over the cache-aware subset of contributing samples.

        Returns ``None`` when no operand reported cache state — in
        that case the result is "unknown", not "zero". Returning 0.0
        for cache-silent providers (Bedrock, Azure, Mistral, Groq,
        Together, Gemini, local runners) would make every such run
        look like a cache regression in A/B diffs.

        For aggregated summaries (a bucket containing both
        cache-silent and cache-aware samples), the denominator is
        ``cache_aware_input_tokens`` — the sum of input tokens from
        ONLY the cache-aware operands. This prevents the silent
        provider's input from contaminating the rate computation.
        """
        if not self.has_cache_info:
            return None
        denominator = self.cache_aware_input_tokens
        return self.cache_read_tokens / denominator if denominator else 0.0

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_model_usage(
        cls, usage: ModelUsage, *, model: str | None = None
    ) -> "UsageSummary":
        """Normalise an Inspect AI ``ModelUsage`` into a ``UsageSummary``.

        Works for every provider: fields the provider did not report
        become 0 in the numeric fields and ``False`` in the
        ``has_*_info`` flags.

        Args:
            usage: The Inspect AI ``ModelUsage`` to normalise.
            model: Optional model identifier (e.g.
                ``"openai/gpt-5"``, ``"anthropic/claude-sonnet-4-6"``).
                When provided, caliper uses provider-specific
                knowledge to disambiguate Inspect AI's None-as-zero
                conflations.

                Specifically, the openai_responses adapter (used for
                gpt-5 / o-series / codex models) sets
                ``input_tokens_cache_read=None`` for a *real* cold
                cache hit (where the API returned ``cached_tokens=0``),
                making it indistinguishable from "provider doesn't
                report cache". When the model hint identifies one of
                those models, caliper reinterprets ``None`` as ``0``
                so the cold-cache state shows as
                ``cache_hit_rate=0.0`` instead of being silently
                rendered as ``None``. Other providers (Anthropic,
                Bedrock, standard OpenAI Chat Completions, etc.)
                are unaffected.

                Pass the model name from
                ``EvalSample.model_usage.items()`` whenever you have it.
        """
        cache_read = usage.input_tokens_cache_read
        cache_write = usage.input_tokens_cache_write
        reasoning = usage.reasoning_tokens

        # Disambiguate the openai_responses adapter's cold-cache None.
        # See ``_uses_openai_responses_adapter`` for the predicate
        # rationale.
        if (
            cache_read is None
            and model is not None
            and _uses_openai_responses_adapter(model)
        ):
            cache_read = 0

        cache_read_int = cache_read or 0
        cache_write_int = cache_write or 0
        has_cache = (cache_read is not None) or (cache_write is not None)
        # cache_aware_input_tokens is the slice of input tokens whose
        # cache state was actually observed by the provider. For a
        # single ``ModelUsage`` that's all-or-nothing: either the
        # provider reported cache (so every input token here is
        # cache-aware) or it didn't (so none of them are).
        all_input = usage.input_tokens + cache_read_int + cache_write_int
        return cls(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=reasoning or 0,
            cache_read_tokens=cache_read_int,
            cache_write_tokens=cache_write_int,
            has_reasoning_info=reasoning is not None,
            has_cache_info=has_cache,
            cache_aware_input_tokens=all_input if has_cache else 0,
        )

    @classmethod
    def zero(cls) -> "UsageSummary":
        """The additive identity: all zeros, all honesty flags False.

        Useful as a starting accumulator when summing usage across a
        set of samples or across a bucket.
        """
        return cls(
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            has_reasoning_info=False,
            has_cache_info=False,
            cache_aware_input_tokens=0,
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def __add__(self, other: "UsageSummary") -> "UsageSummary":
        """Sum two summaries.

        Token fields add as ints. Honesty flags are OR'd: if either
        operand knew about cache, the aggregated summary knows about
        cache. The crucial detail is that ``cache_aware_input_tokens``
        is also summed, so the aggregated ``cache_hit_rate`` denominator
        excludes input tokens that came from cache-silent operands.

        Worked example:

            silent  = Bedrock run, 500 input tokens, no cache info
                       → cache_aware_input_tokens = 0
            aware   = Anthropic run, 500 input + 500 cache_read
                       → cache_aware_input_tokens = 1000
            sum     = total_input_tokens = 1500
                      cache_aware_input_tokens = 1000
                      cache_hit_rate = 500 / 1000 = 0.5
                      (NOT 500 / 1500 = 0.333 — the silent input
                       must not contaminate the rate)
        """
        return UsageSummary(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            has_reasoning_info=self.has_reasoning_info or other.has_reasoning_info,
            has_cache_info=self.has_cache_info or other.has_cache_info,
            cache_aware_input_tokens=(
                self.cache_aware_input_tokens + other.cache_aware_input_tokens
            ),
        )
