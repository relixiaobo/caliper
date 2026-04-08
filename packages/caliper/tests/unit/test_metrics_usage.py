"""Tests for caliper.metrics.usage.UsageSummary.

The test shapes deliberately mirror the ``ModelUsage`` patterns each
Inspect AI provider actually produces (verified by reading
``inspect_ai/model/_providers/*.py``), so these tests fail loudly if
either Inspect AI or our normalisation drifts.

Provider field-support matrix the tests cover:

- Anthropic direct:         input, output, cache_read, cache_write, reasoning
- OpenAI Chat Completions:  input, output, cache_read, reasoning
- OpenAI Responses (gpt-5): same as OpenAI Chat
- Google (Gemini):          input, output, reasoning (NO cache)
- Bedrock / Azure / Mistral / Groq / Together / HF / local:
                            input, output only (NO cache, NO reasoning)
- Grok / OpenAI-compatible: cache_read + reasoning possible

The most important distinction enforced here is
``has_cache_info=False`` → ``cache_hit_rate is None``, vs
``has_cache_info=True and cache_read_tokens == 0`` →
``cache_hit_rate == 0.0``. Conflating the two would make every
Bedrock run look like a cache regression.
"""

from inspect_ai.model import ModelUsage

from caliper.metrics import UsageSummary


# ---------------------------------------------------------------------------
# Construction — one test per realistic provider pattern
# ---------------------------------------------------------------------------


def test_from_anthropic_full_fields():
    """Anthropic direct API populates every optional field."""
    usage = ModelUsage(
        input_tokens=1_000,
        output_tokens=400,
        total_tokens=1_800,
        input_tokens_cache_read=300,
        input_tokens_cache_write=100,
        reasoning_tokens=80,
    )
    s = UsageSummary.from_model_usage(usage)

    assert s.input_tokens == 1_000
    assert s.output_tokens == 400
    assert s.cache_read_tokens == 300
    assert s.cache_write_tokens == 100
    assert s.reasoning_tokens == 80
    assert s.has_cache_info is True
    assert s.has_reasoning_info is True


def test_from_openai_chat_completions():
    """OpenAI Chat Completions: cache_read but no cache_write.

    The OpenAI provider explicitly sets ``input_tokens_cache_write=None``
    because OpenAI's prompt caching is automatic/free and the API
    exposes no "creation" counter. See inspect_ai.model._openai:777
    comment "openai only have cache read stats/pricing".
    """
    usage = ModelUsage(
        input_tokens=800,
        output_tokens=200,
        total_tokens=1_100,
        input_tokens_cache_read=100,
        input_tokens_cache_write=None,
        reasoning_tokens=50,
    )
    s = UsageSummary.from_model_usage(usage)

    assert s.input_tokens == 800
    assert s.cache_read_tokens == 100
    # The key OpenAI-specific assertion: cache_write is 0 but
    # has_cache_info is True because cache_read was reported.
    assert s.cache_write_tokens == 0
    assert s.has_cache_info is True
    assert s.has_reasoning_info is True


def test_from_bedrock_minimal():
    """Bedrock (Anthropic via AWS Converse API) drops all optional
    fields. Both honesty flags must be False."""
    usage = ModelUsage(
        input_tokens=500,
        output_tokens=120,
        total_tokens=620,
    )
    s = UsageSummary.from_model_usage(usage)

    assert s.input_tokens == 500
    assert s.output_tokens == 120
    assert s.cache_read_tokens == 0
    assert s.cache_write_tokens == 0
    assert s.reasoning_tokens == 0
    assert s.has_cache_info is False, (
        "Bedrock does not report cache — has_cache_info must be False"
    )
    assert s.has_reasoning_info is False


def test_from_gemini_reasoning_only():
    """Google Gemini reports reasoning (thoughts_token_count) but no
    cache fields."""
    usage = ModelUsage(
        input_tokens=600,
        output_tokens=300,
        total_tokens=900,
        reasoning_tokens=120,
    )
    s = UsageSummary.from_model_usage(usage)

    assert s.reasoning_tokens == 120
    assert s.has_reasoning_info is True
    assert s.has_cache_info is False
    assert s.cache_hit_rate is None


def test_from_mistral_basic():
    """Mistral / Groq / Together / Azure all populate only input and
    output. Both flags False."""
    usage = ModelUsage(input_tokens=400, output_tokens=100, total_tokens=500)
    s = UsageSummary.from_model_usage(usage)

    assert s.has_cache_info is False
    assert s.has_reasoning_info is False
    assert s.cache_hit_rate is None
    assert s.reasoning_tokens == 0


# ---------------------------------------------------------------------------
# Derived properties
# ---------------------------------------------------------------------------


def test_total_input_tokens_includes_cache():
    s = UsageSummary(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=0,
        cache_read_tokens=200,
        cache_write_tokens=30,
        has_reasoning_info=False,
        has_cache_info=True,
        cache_aware_input_tokens=330,
    )
    assert s.total_input_tokens == 330  # 100 + 200 + 30


def test_total_tokens_sums_everything():
    s = UsageSummary(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=10,
        cache_read_tokens=200,
        cache_write_tokens=30,
        has_reasoning_info=True,
        has_cache_info=True,
        cache_aware_input_tokens=330,
    )
    assert s.total_tokens == 380  # 330 input + 50 output


def test_uncached_input_tokens_includes_cache_write_REGRESSION():
    """REGRESSION TEST for the Codex M1.2 P2 finding.

    ``cache_write_tokens`` are tokens the provider had to read fresh
    AND additionally write into the cache — they were never served
    from cache, so they belong in ``uncached_input_tokens``. The
    earlier definition of ``uncached_input_tokens = input_tokens``
    silently dropped them, hiding exactly the SKILL.md-invalidation
    spike this accessor exists to expose.

    For non-Anthropic providers ``cache_write_tokens`` is always 0
    so this fix is backward-compatible everywhere except the place
    where it actually matters.
    """
    s = UsageSummary(
        input_tokens=777,
        output_tokens=0,
        reasoning_tokens=0,
        cache_read_tokens=999,
        cache_write_tokens=111,
        has_reasoning_info=False,
        has_cache_info=True,
        cache_aware_input_tokens=777 + 999 + 111,
    )
    # Was 777 (the bug). Should be 777 + 111 = 888.
    assert s.uncached_input_tokens == 888


def test_skill_md_invalidation_spike_visible_REGRESSION():
    """The narrative regression: simulate two consecutive Anthropic
    runs where the second one happens right after a SKILL.md edit.

    Run 1 (warm cache): user message is fresh, prefix is cache_read.
    Run 2 (cold cache): user message is fresh, prefix is cache_write.

    Total input volume (input + cache_read + cache_write) is similar.
    The signal that something changed must be visible in
    ``uncached_input_tokens``: low for run 1, much higher for run 2.

    Pre-fix: both runs reported the same uncached_input_tokens (just
    the user message), hiding the spike.
    """
    warm = UsageSummary.from_model_usage(
        ModelUsage(
            input_tokens=200,           # user message
            output_tokens=300,
            input_tokens_cache_read=5_000,  # SKILL.md prefix from cache
            input_tokens_cache_write=0,
        )
    )
    cold = UsageSummary.from_model_usage(
        ModelUsage(
            input_tokens=200,           # user message
            output_tokens=300,
            input_tokens_cache_read=0,
            input_tokens_cache_write=5_000,  # SKILL.md prefix re-written
        )
    )
    # Total input volume is identical between the two runs.
    assert warm.total_input_tokens == cold.total_input_tokens == 5_200
    # But the spike is visible in uncached_input_tokens.
    assert warm.uncached_input_tokens == 200
    assert cold.uncached_input_tokens == 5_200, (
        "SKILL.md cache invalidation must show as a spike in "
        "uncached_input_tokens — that's the entire point of this metric"
    )
    # And in cache_hit_rate.
    assert warm.cache_hit_rate is not None and warm.cache_hit_rate > 0.95
    assert cold.cache_hit_rate == 0.0


# ---------------------------------------------------------------------------
# cache_hit_rate — the most important derived value
# ---------------------------------------------------------------------------


def test_cache_hit_rate_none_when_provider_silent():
    """REGRESSION GUARD: providers that don't report cache must get
    cache_hit_rate=None, never 0.0. Conflating the two would make
    every Bedrock/Azure/Mistral/Gemini run look like a cache
    regression in A/B diffs."""
    s = UsageSummary.from_model_usage(
        ModelUsage(input_tokens=1_000, output_tokens=100, total_tokens=1_100)
    )
    assert s.cache_hit_rate is None, (
        "provider-silent cache must be None, not 0.0"
    )


def test_cache_hit_rate_zero_when_reported_but_empty():
    """has_cache_info=True but cache_read_tokens=0 is a real
    'cold start' that should show 0.0, not None."""
    usage = ModelUsage(
        input_tokens=1_000,
        output_tokens=100,
        input_tokens_cache_read=0,
        input_tokens_cache_write=0,
    )
    s = UsageSummary.from_model_usage(usage)
    assert s.has_cache_info is True
    assert s.cache_hit_rate == 0.0


def test_cache_hit_rate_full():
    usage = ModelUsage(
        input_tokens=0,
        output_tokens=100,
        input_tokens_cache_read=1_000,
        input_tokens_cache_write=0,
    )
    s = UsageSummary.from_model_usage(usage)
    assert s.cache_hit_rate == 1.0


def test_cache_hit_rate_mixed():
    usage = ModelUsage(
        input_tokens=200,
        output_tokens=100,
        input_tokens_cache_read=600,
        input_tokens_cache_write=200,
    )
    s = UsageSummary.from_model_usage(usage)
    # cache_read / (input + cache_read + cache_write) = 600 / 1000
    assert s.cache_hit_rate == 0.6


def test_cache_hit_rate_handles_zero_total_input():
    """Division-by-zero guard: has_cache_info=True but total input is
    0 (a pathological edge case) must return 0.0, not raise."""
    s = UsageSummary(
        input_tokens=0,
        output_tokens=100,
        reasoning_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        has_reasoning_info=False,
        has_cache_info=True,
        cache_aware_input_tokens=0,
    )
    assert s.cache_hit_rate == 0.0


# ---------------------------------------------------------------------------
# Aggregation: __add__ and zero()
# ---------------------------------------------------------------------------


def test_add_sums_all_token_fields():
    a = UsageSummary(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=10,
        cache_read_tokens=20,
        cache_write_tokens=5,
        has_reasoning_info=True,
        has_cache_info=True,
        cache_aware_input_tokens=125,
    )
    b = UsageSummary(
        input_tokens=200,
        output_tokens=100,
        reasoning_tokens=0,
        cache_read_tokens=40,
        cache_write_tokens=10,
        has_reasoning_info=False,
        has_cache_info=True,
        cache_aware_input_tokens=250,
    )
    c = a + b
    assert c.input_tokens == 300
    assert c.output_tokens == 150
    assert c.reasoning_tokens == 10
    assert c.cache_read_tokens == 60
    assert c.cache_write_tokens == 15
    assert c.cache_aware_input_tokens == 375


def test_aggregating_silent_with_aware_does_not_dilute_cache_hit_rate_REGRESSION():
    """REGRESSION TEST for the Codex M1.2 P2 finding.

    A mixed-provider bucket (e.g. one Bedrock sample + one Anthropic
    sample) must NOT include the cache-silent provider's input
    tokens in the cache_hit_rate denominator. The pre-fix
    implementation OR'd has_cache_info and summed all token fields,
    so Bedrock's input tokens contributed to the denominator as if
    they were "input that should have been cached but wasn't",
    silently understating the rate.

    Root fix: track ``cache_aware_input_tokens`` as a separate field
    that only sums input from samples whose cache state was reported.
    The aggregated cache_hit_rate is computed against that subset, so
    the silent provider's contribution is correctly excluded.
    """
    silent = UsageSummary.from_model_usage(
        # Bedrock-style: 500 input tokens, no cache info
        ModelUsage(input_tokens=500, output_tokens=50, total_tokens=550)
    )
    aware = UsageSummary.from_model_usage(
        # Anthropic-style: 500 input + 500 cache_read = 50% hit
        ModelUsage(
            input_tokens=500,
            output_tokens=50,
            input_tokens_cache_read=500,
            input_tokens_cache_write=0,
        )
    )
    assert silent.has_cache_info is False
    assert aware.has_cache_info is True
    assert aware.cache_hit_rate == 0.5

    combined = silent + aware
    # The aggregate knows about cache (because at least one operand did).
    assert combined.has_cache_info is True
    # The CRITICAL assertion: rate must reflect the cache-aware
    # subset only. 500 cache_read / (500 aware_input + 500 cache_read)
    # = 0.5, NOT 500 / (500 + 500 + 500) = 0.333
    assert combined.cache_hit_rate is not None
    assert combined.cache_hit_rate == 0.5, (
        f"Bedrock's silent input tokens must NOT enter the "
        f"cache_hit_rate denominator. Got {combined.cache_hit_rate}, "
        f"expected 0.5 (the rate of the cache-aware subset)."
    )
    # total_input_tokens still sums everything — that field is the
    # raw "how much did we feed into models" number.
    assert combined.total_input_tokens == 1500


def test_aggregating_two_silent_summaries_stays_silent():
    a = UsageSummary.from_model_usage(
        ModelUsage(input_tokens=300, output_tokens=50, total_tokens=350)
    )
    b = UsageSummary.from_model_usage(
        ModelUsage(input_tokens=400, output_tokens=60, total_tokens=460)
    )
    combined = a + b
    assert combined.has_cache_info is False
    assert combined.cache_hit_rate is None


# ---------------------------------------------------------------------------
# Codex M1.2 P2 (round 2) regression: OpenAI Responses adapter conflates
# cold cache with no-info-reported.
#
# inspect_ai/model/_providers/openai_responses.py:216 sets
#     input_tokens_cache_read=cached_tokens if cached_tokens > 0 else None
# so a real cold-cache call (cached_tokens=0) becomes None — indistinguishable
# downstream from a provider that doesn't report cache at all.
#
# from_model_usage takes an optional `model` parameter; when the model
# is known to use Inspect AI's openai_responses adapter (gpt-5 family,
# o-series, or codex), we reinterpret cache_read=None as 0.
# ---------------------------------------------------------------------------


def test_openai_responses_cold_cache_with_model_hint_REGRESSION():
    """REGRESSION TEST for the Codex M1.2 P2 round-2 finding.

    A gpt-5 (OpenAI Responses adapter) cold-cache call has
    ``input_tokens_cache_read=None`` even though the API really did
    return ``cached_tokens=0``. Without provider context, our
    UsageSummary classifies this as ``has_cache_info=False`` and
    ``cache_hit_rate=None`` — hiding the cold-cache regression
    we're trying to expose.

    With ``model="openai/gpt-5"`` passed in, the None is
    reinterpreted as 0, and ``cache_hit_rate`` correctly reads 0.0.
    """
    usage = ModelUsage(
        input_tokens=5_000,
        output_tokens=300,
        input_tokens_cache_read=None,  # adapter normalised 0 → None
        input_tokens_cache_write=None,
        reasoning_tokens=120,
    )
    s = UsageSummary.from_model_usage(usage, model="openai/gpt-5")
    assert s.has_cache_info is True, (
        "openai/gpt-5 uses the Responses adapter with the cold-cache "
        "bug; with the model hint we must treat None as 0"
    )
    assert s.cache_read_tokens == 0
    assert s.cache_hit_rate == 0.0


def test_openai_responses_warm_cache_with_model_hint():
    """Sanity check: when cache_read is reported normally (warm cache),
    the model hint doesn't change anything."""
    usage = ModelUsage(
        input_tokens=200,
        output_tokens=300,
        input_tokens_cache_read=4_800,
        input_tokens_cache_write=None,
    )
    s = UsageSummary.from_model_usage(usage, model="openai/gpt-5")
    assert s.has_cache_info is True
    assert s.cache_read_tokens == 4_800
    assert s.cache_hit_rate == 0.96  # 4800 / 5000


def test_o_series_uses_responses_adapter_too():
    """o1 / o3-mini / o4 are also routed to the Responses adapter."""
    usage = ModelUsage(input_tokens=1_000, output_tokens=200)
    s = UsageSummary.from_model_usage(usage, model="openai/o3-mini")
    assert s.has_cache_info is True
    assert s.cache_hit_rate == 0.0


def test_codex_uses_responses_adapter_too():
    usage = ModelUsage(input_tokens=1_000, output_tokens=200)
    s = UsageSummary.from_model_usage(usage, model="openai/codex-1")
    assert s.has_cache_info is True
    assert s.cache_hit_rate == 0.0


def test_standard_openai_chat_completions_unaffected():
    """gpt-4o uses the Chat Completions adapter (NOT Responses).
    That adapter does NOT have the None-as-0 bug, so its cache_read
    is genuinely None when cache info is unsupported.

    With model='openai/gpt-4o', we should NOT reinterpret None as 0
    — it's a true 'unknown'.
    """
    usage = ModelUsage(
        input_tokens=1_000,
        output_tokens=200,
        input_tokens_cache_read=None,
    )
    s = UsageSummary.from_model_usage(usage, model="openai/gpt-4o")
    assert s.has_cache_info is False
    assert s.cache_hit_rate is None


def test_anthropic_None_remains_unknown_with_model_hint():
    """Anthropic's None means 'caching wasn't enabled in the request',
    which is genuinely 'unknown', not 'cold cache'. The model hint
    must NOT make Anthropic look like cold cache."""
    usage = ModelUsage(input_tokens=1_000, output_tokens=200)
    s = UsageSummary.from_model_usage(
        usage, model="anthropic/claude-sonnet-4-6"
    )
    assert s.has_cache_info is False
    assert s.cache_hit_rate is None


def test_bedrock_None_remains_unknown_with_model_hint():
    usage = ModelUsage(input_tokens=1_000, output_tokens=200)
    s = UsageSummary.from_model_usage(
        usage, model="bedrock/anthropic.claude-3"
    )
    assert s.has_cache_info is False
    assert s.cache_hit_rate is None


def test_no_model_hint_falls_back_to_pre_fix_behavior():
    """When the caller doesn't know the provider (no model arg),
    we have no way to disambiguate cold vs unknown for OpenAI
    Responses. We default to 'unknown' (the safer rendering — None,
    not 0.0). The caller should pass `model=` whenever possible."""
    usage = ModelUsage(input_tokens=1_000, output_tokens=200)
    s = UsageSummary.from_model_usage(usage)  # no model
    assert s.has_cache_info is False
    assert s.cache_hit_rate is None


def test_model_hint_strips_provider_prefix():
    """The model hint may or may not include the 'provider/' prefix.
    Both should work."""
    usage = ModelUsage(input_tokens=1_000, output_tokens=200)
    s1 = UsageSummary.from_model_usage(usage, model="gpt-5")
    s2 = UsageSummary.from_model_usage(usage, model="openai/gpt-5")
    assert s1.has_cache_info is True
    assert s2.has_cache_info is True
    assert s1.cache_hit_rate == s2.cache_hit_rate == 0.0


def test_zero_is_additive_identity():
    s = UsageSummary(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=10,
        cache_read_tokens=20,
        cache_write_tokens=5,
        has_reasoning_info=True,
        has_cache_info=True,
        cache_aware_input_tokens=125,
    )
    z = UsageSummary.zero()
    assert s + z == s
    assert z + s == s


def test_zero_has_all_flags_false():
    z = UsageSummary.zero()
    assert z.has_cache_info is False
    assert z.has_reasoning_info is False
    assert z.total_tokens == 0
    assert z.cache_hit_rate is None
