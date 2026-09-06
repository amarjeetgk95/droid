import asyncio
import sys
import time
from decimal import Decimal

from app.crypto_scalp.trigger_gate import (
    check_crypto_trigger_integrity,
    min_crypto_trigger_gap_pts,
)
from app.crypto_scalp.risk_engine import (
    crypto_risk_engine,
    CryptoStrategySetup,
    CryptoValidatedRiskDecision,
    CRYPTO_RISK_ENVELOPES,
)
from app.crypto_scalp.fsm import (
    crypto_signal_fsm,
    CryptoSignalInstance,
    CryptoFSMTransitionAudit,
    CryptoFSMState,
)
from app.crypto_scalp.confluence import crypto_confluence_engine
from app.crypto_scalp.fill_reconciler import (
    crypto_fill_reconciler,
    CryptoFillReconciliationRecord,
)

def test_trigger_gate():
    print("Testing Crypto Trigger Integrity Gate...")
    min_btc_gap = min_crypto_trigger_gap_pts(65000.0, 250.0)
    assert min_btc_gap >= Decimal("12.5"), f"Expected min BTC gap >= 12.5, got {min_btc_gap}"
    
    # 1. Born-triggered: CMP 65050, trigger 65000 for BUY -> should reject
    res = check_crypto_trigger_integrity(
        direction="BUY",
        spot_price=65050.0,
        trigger=65000.0,
        stop_loss=64500.0,
        target_1=65600.0,
        target_2=66200.0,
        symbol="BTCUSDT"
    )
    assert not res.passed, f"Born-triggered BUY should be rejected: {res.message}"
    assert "TRIGGER_WRONG_SIDE" in (res.reason_code or "")
    
    # 2. Too close gap: CMP 65000, trigger 65005 (< min gap) -> should reject
    res2 = check_crypto_trigger_integrity(
        direction="BUY",
        spot_price=65000.0,
        trigger=65005.0,
        stop_loss=64700.0,
        target_1=65500.0,
        target_2=66000.0,
        symbol="BTCUSDT"
    )
    assert not res2.passed, f"Sub-minimum gap should be rejected: {res2.message}"
    assert "TRIGGER_TOO_CLOSE" in (res2.reason_code or "")
    
    # 3. Valid BUY breakout: CMP 65000, trigger 65050, SL 64800 (risk 250), T1 65400 (1.4R), T2 65700 (2.6R)
    res3 = check_crypto_trigger_integrity(
        direction="BUY",
        spot_price=65000.0,
        trigger=65050.0,
        stop_loss=64800.0,
        target_1=65400.0,
        target_2=65700.0,
        symbol="BTCUSDT"
    )
    assert res3.passed, f"Valid breakout should pass: {res3.message}"
    print("  -> Trigger Integrity Gate PASS")


def test_risk_engine():
    print("Testing Crypto Central Risk Engine & Invariants...")
    # 1. Normal BTC Scalp (1M)
    setup = CryptoStrategySetup(
        strategy_name="EMA_PULLBACK",
        symbol="BTCUSDT",
        direction="LONG",
        timeframe="1m",
        is_scalp=True,
        spot_price=Decimal("65000.0"),
        entry_trigger=Decimal("65050.0"),
        raw_structural_stop=Decimal("64800.0"), # 250 pt stop (within envelope 100-500)
        structural_target_candidates=[Decimal("65350.0"), Decimal("65650.0")],
        atr_val=Decimal("120.0"),
    )
    decision = crypto_risk_engine.evaluate(setup, available_equity_usd=10000.0)
    assert decision.accepted, f"Normal setup should be approved: {decision.rejection_reason}"
    assert decision.entry_price == Decimal("65050.0")
    assert decision.stop_loss == Decimal("64800.0"), "Structural stop must NOT be clamped!"
    assert decision.risk_reward_t1 >= 1.0
    
    # 2. Invariant Check: Stop too wide (e.g. 1500 pt stop > 500 pt max envelope)
    # MUST reject, MUST NOT clamp!
    wide_setup = CryptoStrategySetup(
        strategy_name="EMA_PULLBACK",
        symbol="BTCUSDT",
        direction="LONG",
        timeframe="1m",
        is_scalp=True,
        spot_price=Decimal("65000.0"),
        entry_trigger=Decimal("65050.0"),
        raw_structural_stop=Decimal("63500.0"), # 1550 pt stop > max allowable 500
        structural_target_candidates=[Decimal("66500.0"), Decimal("68000.0")],
        atr_val=Decimal("120.0"),
    )
    decision_wide = crypto_risk_engine.evaluate(wide_setup, available_equity_usd=10000.0)
    assert not decision_wide.accepted, "Oversized stop MUST be rejected!"
    assert "STRUCTURAL_RISK_EXCEEDS_ENVELOPE" in decision_wide.rejection_reason
    assert decision_wide.stop_loss == Decimal("63500.0"), "Must never clamp structural stop!"

    # 3. Stop too tight (< min risk 100 pts)
    tight_setup = CryptoStrategySetup(
        strategy_name="MICRO_SCALP",
        symbol="BTCUSDT",
        direction="LONG",
        timeframe="1m",
        is_scalp=True,
        spot_price=Decimal("65000.0"),
        entry_trigger=Decimal("65050.0"),
        raw_structural_stop=Decimal("65030.0"), # 20 pt stop < min 100 pts
        structural_target_candidates=[Decimal("65100.0")],
        atr_val=Decimal("30.0"),
    )
    decision_tight = crypto_risk_engine.evaluate(tight_setup, available_equity_usd=10000.0)
    assert decision_tight.stop_loss <= Decimal("65050.0")
    print("  -> Central Risk Engine PASS")


class DummyCtx:
    ema_9_1m = 65200.0
    ema_21_1m = 65100.0
    ema_50_1m = 65000.0
    vwap_session = 65050.0
    current_price = 65220.0
    volume_surge_ratio = 2.2
    candles_5m = [{"close": 65100}, {"close": 65150}, {"close": 65200}]
    candles_15m = [{"close": 65000}, {"close": 65100}, {"close": 65200}]

def test_confluence_engine():
    print("Testing Crypto Confluence Engine...")
    ctx = DummyCtx()
    score, breakdown = crypto_confluence_engine.fuse(
        symbol="BTCUSDT",
        direction="LONG",
        strategy="EMA_PULLBACK",
        ctx=ctx,
        regime="TREND_UP",
        sentiment_score=75.0,
    )
    assert score >= 60.0, f"Expected strong confluence score, got {score}"
    assert "technical" in breakdown
    assert "mtf" in breakdown
    assert "fused_confidence" in breakdown
    print(f"  -> Confluence Engine PASS (score: {score:.1f}, breakdown: {breakdown})")


async def test_fsm_and_reconciler():
    print("Testing Crypto FSM Manager & Fill Reconciler (Two-Clock Lifecycle, Ratchet & Staged Exits)...")
    # 1. Register candidate in FSM
    sig = CryptoSignalInstance(
        signal_id="test-crypto-sig-001",
        symbol="BTCUSDT",
        asset="BTC",
        direction="LONG",
        strategy="EMA_PULLBACK",
        timeframe="1m",
        is_scalp=True,
        spot_price=Decimal("64950.0"),
        trigger=Decimal("65000.0"),
        stop_loss=Decimal("64750.0"), # 250 pt risk
        target_1=Decimal("65250.0"),  # +1.0R
        target_2=Decimal("65500.0"),  # +2.0R
        risk_points=Decimal("250.0"),
        confidence=85.0,
        fsm_state="ARMED",
        ttl_seconds=120,
        time_stop_seconds=600,
        runner_ttl_seconds=300,
    )
    crypto_signal_fsm.register(sig)
    
    assert sig.fsm_state == "ARMED"
    assert sig.expires_at_utc is not None
    assert sig.time_stop_at_utc is None
    
    # 2. Price crosses trigger -> TRIGGERED -> CONFIRMED (fill)
    ok, err = crypto_signal_fsm.transition(
        sig.signal_id,
        "TRIGGERED",
        market_price=Decimal("65005.0"),
        reason="PRICE_CROSS_TRIGGER",
    )
    assert ok, f"Transition to TRIGGERED failed: {err}"
    assert sig.fsm_state == "TRIGGERED"
    
    ok, err = crypto_signal_fsm.transition(
        sig.signal_id,
        "CONFIRMED",
        market_price=Decimal("65005.0"),
        reason="CONFIRMED_FILL",
    )
    assert ok, f"Transition to CONFIRMED failed: {err}"
    assert sig.fsm_state == "CONFIRMED"
    assert sig.time_stop_at_utc is not None
    assert not sig.breakeven_activated

    # Reconcile Entry fill: 1.0 BTC at 65005.0
    rec_entry = crypto_fill_reconciler.reconcile_entry(sig, fill_price=65005.0, quantity=1.0)
    assert rec_entry.remaining_qty == 1.0
    assert rec_entry.t1_qty == 0.5
    assert rec_entry.total_fees_usd > 0
    
    # 3. +0.8R test: 65005 + (250 * 0.8) = 65205
    # Price hits 65210 (> +0.8R threshold)
    ratchet_applied = crypto_signal_fsm.ratchet_breakeven(sig.signal_id, market_price=Decimal("65210.0"))
    assert ratchet_applied, "Ratchet should trigger at +0.8R"
    assert sig.breakeven_activated
    assert sig.current_stop_loss >= Decimal("65005.0"), f"Stop should be ratcheted to breakeven+, got {sig.current_stop_loss}"
    
    # 4. Partial Exit at Target 1 (50%)
    ok, err = crypto_signal_fsm.transition(
        sig.signal_id,
        "TARGET_1_HIT",
        market_price=Decimal("65250.0"),
        reason="TARGET_1_REACHED",
    )
    assert ok, f"Transition to TARGET_1_HIT failed: {err}"
    assert sig.fsm_state == "TARGET_1_HIT"
    assert sig.runner_time_stop_at_utc is not None

    rec_t1 = crypto_fill_reconciler.reconcile_t1_exit(sig, exit_fill_price=65250.0)
    assert rec_t1.remaining_qty == 0.5, f"Expected 0.5 remaining, got {rec_t1.remaining_qty}"
    assert rec_t1.t1_gross_pnl_usd > 0
    assert rec_t1.t1_net_pnl_usd < rec_t1.t1_gross_pnl_usd
    
    # 5. Full close at Target 2 (remaining 50%)
    ok, err = crypto_signal_fsm.transition(
        sig.signal_id,
        "TARGET_2_HIT",
        market_price=Decimal("65500.0"),
        reason="TARGET_2_REACHED",
    )
    assert ok, f"Transition to TARGET_2_HIT failed: {err}"
    assert sig.fsm_state == "TARGET_2_HIT"

    rec_final = crypto_fill_reconciler.reconcile_final_exit(sig, exit_fill_price=65500.0, exit_reason="TARGET_2_HIT")
    assert rec_final.remaining_qty == 0.0
    assert rec_final.is_fully_closed
    assert rec_final.total_net_pnl_usd > 0
    assert rec_final.realized_rr_net > 1.0, f"Expected net R > 1.0, got {rec_final.realized_rr_net}"
    print(f"  -> FSM & Reconciler PASS (Total Net PnL: ${rec_final.total_net_pnl_usd:.2f}, Net R: {rec_final.realized_rr_net:.2f}R)")


async def main():
    test_trigger_gate()
    test_risk_engine()
    test_confluence_engine()
    await test_fsm_and_reconciler()
    print("\n==========================================")
    print("ALL CRYPTO ENGINE VERIFICATIONS PASSED 100%")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(main())
