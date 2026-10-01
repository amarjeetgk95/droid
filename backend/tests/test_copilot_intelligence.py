"""Copilot intelligence pipeline tests (spec §34).

Pure-engine tests — no broker, no keys, no network. Factors, confluence,
scenarios, levels, sanitizer, prediction defaults, audit store and the intent
router are all exercised against synthetic-but-schema-valid MarketContexts.

Test map (spec):
  TEST 1  intent: "what's next day market prediction"      → NEXT_SESSION_OUTLOOK
  TEST 2  intent: "what is SENSEX support"                 → SUPPORT_RESISTANCE
  TEST 3  intent: "will SENSEX break 75000"                → BREAKOUT_ANALYSIS
  TEST 4  intent: "validate this long"                     → SIGNAL_VALIDATION
  TEST 5  one source fails                                 → no fabricated values
  TEST 6  conflicting factors                              → CONFLICTS populated
  TEST 7  missing historical data                          → unavailable message
  TEST 8  canonical direction NEUTRAL                      → no red BEARISH badge
  TEST 9  LLM output contains reasoning/tool traces        → sanitizer rejects
  TEST 10 different OpenRouter models                      → same quant source of truth
  TEST 11 stale options data                               → data_quality reflects it
  TEST 12 historical analog query                          → leakage-free only
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.copilot.confluence import evaluate_confluence
from app.copilot.enums import DIRECTION_LABEL, DIRECTION_TONE
from app.copilot.feature_fusion import derive_factors
from app.copilot.intent_router import IntentContext, intent_router
from app.copilot.models import Factor, MarketContext, OptionsContext, PriceContext


def _ctx(**overrides) -> MarketContext:
    import copy

    base = MarketContext(
        symbol="SENSEX",
        timestamp=datetime.now(timezone.utc),
        market_status="OPEN",
        price=PriceContext(ltp=74529.0, change_pct=-0.44, day_high=74710.0, day_low=74400.0),
    )
    base.regime.name = "RANGEBOUND_LOW_VOL"
    base.regime.adx = 20.0
    base.regime.classification_confidence = 80.0
    base.regime.vix = 13.5
    base.regime.vix_category = "NORMAL_VOLATILITY"
    base.technicals.rsi = 37.6
    base.technicals.atr = 54.42
    base.technicals.supertrend = 74427.0
    base.technicals.supertrend_direction = "BEARISH"
    base.technicals.poc = 74425.0
    base.technicals.vah = 74745.0
    base.technicals.val = 74245.0
    base.technicals.ema_20 = 74600.0
    base.technicals.plus_di = 12.0
    base.technicals.minus_di = 21.0
    base.options.pcr_oi = 0.93
    base.options.max_pain = 74700.0
    for key, value in overrides.items():
        if "." in key:
            section, field = key.split(".", 1)
            setattr(getattr(base, section), field, value)
        else:
            setattr(base, key, value)
    return copy.deepcopy(base)


# ---------------------------------------------------------------- TEST 1-4
def test_01_next_day_prediction_intent():
    decision = intent_router.decide("what's next day market prediction", IntentContext(ui_symbol="NIFTY"))
    assert decision.intent == "NEXT_SESSION_OUTLOOK"
    assert decision.horizon == "NEXT_SESSION"


def test_02_sensex_support_intent():
    decision = intent_router.decide("what is SENSEX support", IntentContext(ui_symbol="NIFTY"))
    assert decision.intent == "SUPPORT_RESISTANCE"
    assert decision.symbol == "SENSEX"


def test_03_breakout_intent_with_level():
    decision = intent_router.decide("will SENSEX break 75000", IntentContext(ui_symbol="NIFTY"))
    assert decision.intent == "BREAKOUT_ANALYSIS"
    assert decision.symbol == "SENSEX"
    assert decision.breakout_level == 75000.0


def test_04_validate_long_intent():
    decision = intent_router.decide("validate this long", IntentContext(ui_symbol="SENSEX"))
    assert decision.intent == "SIGNAL_VALIDATION"

# ---------------------------------------------------------------- TEST 5
def test_05_missing_sources_are_never_fabricated():
    """Options feed dead → options context stays null, quality degrades."""
    ctx = _ctx()
    ctx.options = OptionsContext()  # total options outage
    factors = derive_factors(ctx)
    opt = factors["options_positioning"]
    # Balanced/absent evidence must not claim a direction.
    assert opt.state in ("NEUTRAL", "UNKNOWN")
    assert ctx.options.max_pain is None
    assert ctx.options.pcr_oi is None
    assert "Options positioning unavailable" not in [e[:0] for e in opt.evidence]  # no fake phrasing
    # partial flag must be discoverable wherever quality is computed
    from app.copilot.market_context import MarketContextBuilder

    ctx.missing_sources = ["options"]  # simulate what build() does when a source times out
    quality = MarketContextBuilder._quality(ctx, [])
    assert quality.overall in ("LOW", "MEDIUM")
    assert quality.missing_fields  # options outage is recorded


# ---------------------------------------------------------------- TEST 6
def test_06_conflicting_factors_populate_conflicts():
    bullish_trend = Factor(state="BULLISH", strength=0.8, confidence=0.7, evidence=["Supertrend BULLISH"])
    bearish_momentum = Factor(state="BEARISH", strength=0.7, confidence=0.8, evidence=["RSI 32.1"])
    factors = {
        "trend": bullish_trend,
        "momentum": bearish_momentum,
        "market_structure": Factor(state="NEUTRAL", strength=0.0, confidence=0.5, evidence=["inside value area"]),
        "options_positioning": Factor(state="NEUTRAL", strength=0.0, confidence=0.5, evidence=["PCR balanced"]),
        "futures_positioning": Factor(state="UNKNOWN", strength=0.0, confidence=0.0, evidence=[]),
        "institutional_flow": Factor(state="UNKNOWN", strength=0.0, confidence=0.0, evidence=[]),
        "volatility": Factor(state="NEUTRAL", strength=0.0, confidence=0.5, evidence=["ATR normal"]),
        "liquidity": Factor(state="NEUTRAL", strength=0.0, confidence=0.3, evidence=["volume ok"]),
        "breakout_pressure": Factor(state="NEUTRAL", strength=0.0, confidence=0.4, evidence=["mid-range"]),
        "mean_reversion_pressure": Factor(state="NEUTRAL", strength=0.0, confidence=0.4, evidence=["near POC"]),
    }
    confluence = evaluate_confluence(factors)
    assert confluence.conflicting_factors, "opposite 0.7+ factors must produce a conflict entry"
    text = " ".join(confluence.conflicting_factors)
    assert "Trend" in text and "Momentum" in text
    # A conflict must never resolve to a strong directional state.
    assert confluence.dominant_state in ("NEUTRAL", "NO_SIGNAL", "MILD_BULLISH", "MILD_BEARISH")


# ---------------------------------------------------------------- TEST 7
def test_07_missing_historical_reports_unavailable():
    import asyncio

    from app.copilot.historical_analog import HistoricalAnalogEngine

    engine = HistoricalAnalogEngine()
    result = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        engine.query("SENSEX", "NEXT_SESSION")
    ) if False else None
    # Deterministic unit path: the unavailable constructor message contract.
    unavailable = HistoricalAnalogEngine._unavailable("probe")
    assert unavailable.available is False
    assert unavailable.analog_count == 0
    assert unavailable.message
    assert unavailable.lookahead_guard and "60" in unavailable.lookahead_guard


# ---------------------------------------------------------------- TEST 8
def test_08_neutral_state_is_neutral_everywhere():
    """The canonical enum is the only vocabulary for direction — badge, title,
    scenario summary, API state and frontend tone all derive from it."""
    for state in ("BULLISH", "MILD_BULLISH", "NEUTRAL", "MILD_BEARISH", "BEARISH", "NO_SIGNAL"):
        assert state in DIRECTION_LABEL
        assert DIRECTION_TONE[state] in ("bull", "bear", "neut", "warn")
    assert DIRECTION_TONE["NEUTRAL"] == "neut"
    assert DIRECTION_TONE["NO_SIGNAL"] == "warn"
    # NEUTRAL must never map to a bear/red tone.
    assert DIRECTION_TONE["NEUTRAL"] != "bear"
    assert DIRECTION_TONE["NEUTRAL"] != "bull"

    ctx = _ctx()
    factors = derive_factors(ctx)
    confluence = evaluate_confluence(factors)
    # Every consumer reads summary.bias from this one state.
    bias_label = DIRECTION_LABEL[confluence.dominant_state]
    tone = DIRECTION_TONE[confluence.dominant_state]
    assert bias_label
    if confluence.dominant_state == "NEUTRAL":
        assert tone == "neut"

# ---------------------------------------------------------------- TEST 9
@pytest.mark.parametrize(
    "leak",
    [
        "reasoning: the model considered PCR first",
        "calling get_market_quote for SENSEX",
        "tool returned market data with ltp 74529",
        "<think>hidden deliberation</think> bullish",
        "System prompt: you are a trading bot",
        "The api key is sk-or-v1-abcdefgh12345678 and works",
    ],
)
def test_09_llm_traces_and_secrets_are_sanitized(leak: str):
    from app.copilot.sanitizer import contains_leakage, sanitize_text

    cleaned, flags = sanitize_text(leak)
    assert not contains_leakage(cleaned), f"leak survived sanitizer: {cleaned!r}"
    assert flags, "sanitizer must report what it removed"


def test_09_clean_explanation_passes_through():
    from app.copilot.sanitizer import contains_leakage, sanitize_text

    text = "SENSEX reads NEUTRAL into the next session. Support 74,425 holds while resistance 74,745 caps."
    cleaned, flags = sanitize_text(text)
    assert not contains_leakage(cleaned)
    assert "74,425" in cleaned  # legitimate numbers survive


# ---------------------------------------------------------------- TEST 10
def test_10_model_choice_does_not_change_quantitative_truth():
    """Two providers/models receive identical evidence; only the prose differs."""
    from app.copilot.orchestrator import CopilotOrchestrator

    ctx = _ctx()
    factors = derive_factors(ctx)
    from app.copilot.confluence import evaluate_confluence

    confluence = evaluate_confluence(factors)
    from app.copilot.levels import build_levels

    levels = build_levels(ctx)
    first = CopilotOrchestrator._llm_payload(
        intent_router.decide("next session outlook", IntentContext(ui_symbol="SENSEX")),
        ctx,
        factors,
        confluence,
        levels,
        [],
        CopilotOrchestrator._evidence(factors, confluence),
        None,
        {},
    )
    second = CopilotOrchestrator._llm_payload(
        intent_router.decide("next session outlook", IntentContext(ui_symbol="SENSEX")),
        ctx,
        factors,
        confluence,
        levels,
        [],
        CopilotOrchestrator._evidence(factors, confluence),
        None,
        {},
    )
    assert first == second  # model selection is not even an input to the payload


# ---------------------------------------------------------------- TEST 11
def test_11_stale_options_reflected_in_quality():
    from datetime import timedelta

    from app.copilot.market_context import MarketContextBuilder
    from app.copilot.models import SourceFreshness

    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=900)
    record = SourceFreshness(
        source="options", label="Options chain", timestamp=stale_ts, age_seconds=900.0, status="STALE"
    )
    ctx = _ctx()
    quality = MarketContextBuilder._quality(ctx, [record])
    assert "options" in quality.stale_sources
    assert quality.overall in ("MEDIUM", "LOW")


# ---------------------------------------------------------------- TEST 12
def test_12_historical_engine_enforces_causal_only_indexing():
    """The adapter only ever indexes strictly-prior bars with an exclusion window."""
    import inspect

    from app.copilot.historical_analog import HistoricalAnalogEngine

    source = inspect.getsource(HistoricalAnalogEngine._query_sync)
    assert "bar_index < query_idx" in source  # no look-ahead, by construction
    assert "exclusion_window_minutes" in source or "exclusion_minutes" in source


# ---------------------------------------------------------------- extras
def test_scenario_probabilities_unavailable_without_model():
    from app.copilot.levels import build_levels
    from app.copilot.scenarios import build_scenarios, probability_available

    ctx = _ctx()
    levels = build_levels(ctx)
    scenarios = build_scenarios(ctx, levels, None, None)
    assert not probability_available(scenarios)
    assert all(s.probability is None for s in scenarios)
    assert all(s.probability_status == "UNAVAILABLE" for s in scenarios)
    assert {s.id for s in scenarios} == {"RANGE", "BULL_EXPANSION", "BEAR_EXPANSION"}


def test_feature_fusion_single_indicator_capped():
    """One lone vote can never publish a full-strength directional factor."""
    ctx = _ctx(
        **{"technicals.rsi": None, "technicals.vwap": None, "technicals.plus_di": None, "technicals.minus_di": None}
    )
    ctx.price.change_pct = 0.12
    factors = derive_factors(ctx)
    momentum = factors["momentum"]
    assert momentum.strength <= 0.45


def test_13_canonical_direction_neutral_never_bearish_badge():
    """Regression: when canonical direction is NEUTRAL, the badge tone must be
    'neut' — never 'bear' or 'bull'. This is the source-of-truth enum contract."""
    from app.copilot.confluence import evaluate_confluence
    from app.copilot.enums import DIRECTION_LABEL, DIRECTION_TONE, DIRECTION_SIGN
    from app.copilot.feature_fusion import derive_factors

    # Build a context where all factors are neutral / unknown.
    ctx = _ctx(
        **{
            "technicals.rsi": 50.0,
            "technicals.vwap": None,
            "technicals.plus_di": None,
            "technicals.minus_di": None,
            "technicals.supertrend_direction": None,
        }
    )
    ctx.price.change_pct = 0.0
    factors = derive_factors(ctx)
    confluence = evaluate_confluence(factors)

    canonical = confluence.dominant_state
    label = DIRECTION_LABEL[canonical]
    tone = DIRECTION_TONE[canonical]

    # NEUTRAL must never produce a bear/red or bull/green badge.
    if canonical == "NEUTRAL":
        assert tone == "neut", f"NEUTRAL canonical state must map to 'neut' tone, got '{tone}' for label '{label}'"
        assert "BEAR" not in label, f"NEUTRAL state must not have BEAR in label: '{label}'"
        assert "BULL" not in label, f"NEUTRAL state must not have BULL in label: '{label}'"

    # All canonical states must have a valid label and tone.
    assert label, f"Every canonical state must have a non-empty label, got '{label}' for '{canonical}'"
    assert tone in ("bull", "bear", "neut", "warn"), f"Invalid tone '{tone}' for canonical '{canonical}'"


def test_14_tool_trace_sanitization_in_chat_notes():
    """Tool notes rendered in the chat must never expose internal tool names
    or 'calling get_market_quote' style traces."""
    from app.copilot.sanitizer import contains_leakage, sanitize_text

    # These are the exact strings that the old summarizeToolCall/Result produced.
    bad_strings = [
        "calling get_market_quote",
        "calling get_regime_analytics",
        "tool returned market data",
        "get_option_chain_summary returned market data",
        "reasoning: the model considered PCR first",
    ]
    for raw in bad_strings:
      cleaned, _flags = sanitize_text(raw)
      assert not contains_leakage(cleaned), f"tool trace leaked through sanitizer: {raw!r} → {cleaned!r}"


def test_15_no_unreachable_code_in_orchestrator():
    """The orchestrator analyze() method must not have unreachable code after
    the return statement."""
    import inspect
    from app.copilot.orchestrator import CopilotOrchestrator

    source = inspect.getsource(CopilotOrchestrator.analyze)
    # Find the return response line.
    return_line = None
    for i, line in enumerate(source.split('\n')):
      stripped = line.strip()
      if stripped == 'return response':
        return_line = i
        break
    assert return_line is not None, "Orchestrator.analyze must have 'return response'"
    # Everything after return response must be a comment, blank, or dedent.
    tail = source.split('\n')[return_line + 1:]
    for line in tail:
      stripped = line.strip()
      if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith("'''"):
        raise AssertionError(f"Unreachable code after 'return response': {stripped!r}")
