import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.event_engine.models import CanonicalEvent
from app.event_engine.options_context import options_intelligence_service, LiveOptionsContext
from app.event_engine.scoring_service import scoring_service
from app.models.options import OptionChainResponse, OptionsAnalytics, OptionChainStrikeRow, OptionSide, OptionGreeks


def _fake_chain() -> OptionChainResponse:
    analytics = OptionsAnalytics(
        symbol="BANKNIFTY",
        spot_price=52000.0,
        futures_price=52120.0,
        expiry="2026-10-15",
        atm_strike=52000.0,
        atm_iv=14.5,
        pcr_oi=1.05,
        pcr_volume=0.98,
        max_pain_strike=52000.0,
        total_call_oi=100000,
        total_put_oi=110000,
        time_to_expiry_days=4.0,
    )
    row = OptionChainStrikeRow(
        strike=52000.0,
        is_atm=True,
        call=OptionSide(symbol="BANKNIFTY52000CE", ltp=420.0, open_interest=50000, greeks=OptionGreeks(delta=0.5, gamma=0.001, theta=-5.0, vega=10.0, rho=0.05, theoretical_price=420.0, intrinsic_value=0.0, time_value=420.0)),
        put=OptionSide(symbol="BANKNIFTY52000PE", ltp=380.0, open_interest=60000, greeks=OptionGreeks(delta=-0.5, gamma=0.001, theta=-5.0, vega=10.0, rho=0.05, theoretical_price=380.0, intrinsic_value=0.0, time_value=380.0)),
    )
    return OptionChainResponse(underlying="BANKNIFTY", spot_price=52000.0, futures_price=52120.0, expiry="2026-10-15", analytics=analytics, strikes=[row])


@pytest.mark.asyncio
async def test_live_options_context_generation():
    with patch.object(options_intelligence_service._options_svc, "get_option_chain_matrix", new_callable=AsyncMock, return_value=_fake_chain()):
        context = await options_intelligence_service.get_live_options_context("BANKNIFTY")
    assert context.underlying == "BANKNIFTY"
    assert context.spot_price > 0
    assert context.atm_strike > 0
    assert context.days_to_expiry >= 0.1
    assert context.expected_move_points is not None
    assert context.spread_acceptable in (True, False)


def test_real_time_opportunity_scoring_with_hard_gates():
    """Spec §15 & §16: Trading Opportunity Score uses perishable state and obeys hard gates."""
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee Resolution Oct 2026",
        event_type="CENTRAL_BANK",
        sub_type="MONETARY_POLICY_RATE_DECISION",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
        temporal_phase="APPROACHING",
    )

    # 1. Normal live market conditions with good spread
    live_good = LiveOptionsContext(
        underlying="BANKNIFTY",
        spot_price=52000.0,
        futures_price=52120.0,
        expiry="2026-10-15",
        days_to_expiry=4.0,
        atm_strike=52000.0,
        atm_iv=14.5,
        bid_ask_spread_pct=1.2,
        spread_acceptable=True,
        liquidity_acceptable=True,
        market_data_valid=True,
    )

    opp_good = scoring_service.calculate_opportunity_score(
        event=event,
        market_data_available=True,
        live_options=live_good,
        signal_context={"setup_quality": 82.0, "confidence": 85.0, "risk_reward_score": 80.0},
    )

    assert opp_good.status == "SCORED"
    assert opp_good.final_score > 70.0
    # Spec §3 & §27: Operating in SHADOW_MODE
    assert opp_good.final_decision == "EXECUTE_SHADOW"

    # 2. Hard Gate: Unacceptable options spread (>5%) MUST force NO_TRADE (§16)
    live_bad_spread = LiveOptionsContext(
        underlying="BANKNIFTY",
        spot_price=52000.0,
        futures_price=52120.0,
        expiry="2026-10-15",
        days_to_expiry=4.0,
        atm_strike=52000.0,
        atm_iv=28.0,
        bid_ask_spread_pct=6.5,
        spread_acceptable=False,  # Fails gate!
        liquidity_acceptable=True,
        market_data_valid=True,
    )

    opp_bad = scoring_service.calculate_opportunity_score(
        event=event,
        market_data_available=True,
        live_options=live_bad_spread,
        signal_context={"setup_quality": 95.0, "confidence": 95.0},
    )

    assert "SPREAD_ACCEPTABLE" in opp_bad.failed_gates
    assert opp_bad.final_decision == "NO_TRADE"
    assert opp_bad.status == "NO_TRADE"
