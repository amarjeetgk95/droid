"""
IV Regime Mispricing Strategy (Live Intraday Desk).

Exploits Implied Volatility vs Realized Volatility regime dislocations:
- Regime A (IV Compression, IV/RV < 0.85): Directional long options on trend continuation.
- Regime B (IV Expansion, IV/RV > 1.30): Premium decay fade on overextended counter-trend moves.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr
from app.signals.strategies.candidate import make_candidate
from app.quant.strategies.s8_iv_regime import classify_iv_regime


class IVRegimeStrategy(Strategy):
    name = "IV_REGIME"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if not ctx.candles or len(ctx.candles) < 10:
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        ind = ctx.indicators
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        if atr <= Decimal("0"):
            return None

        # F&O data required for IV regime
        fno = ctx.fno or {}
        raw_iv = fno.get("atm_iv") or fno.get("iv")
        if raw_iv is None:
            # Fallback proxy using annualized ATR if fno is degraded
            raw_iv = float(atr / spot) * 19.36
        else:
            try:
                raw_iv = float(raw_iv)
                if raw_iv > 1.0:  # e.g. 14.5% represented as 14.5
                    raw_iv = raw_iv / 100.0
            except Exception:
                return None

        # Realized volatility estimate (annualized)
        closes = [float(c.get("close", spot)) for c in ctx.candles[-20:]]
        if len(closes) >= 5:
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
            import numpy as np
            rv = float(np.std(returns) * np.sqrt(375.0 * 252.0))
        else:
            rv = float(atr / spot) * 19.36

        iv_percentile = fno.get("iv_percentile")
        if iv_percentile is not None:
            try:
                iv_percentile = float(iv_percentile)
            except Exception:
                iv_percentile = None

        regime = classify_iv_regime(raw_iv, rv, iv_percentile)
        if regime == "NEUTRAL":
            return None

        vwap = ctx.vwap or spot
        rsi = ind.get("rsi")
        rsi_val = float(rsi) if rsi is not None else 50.0

        # Regime A: Volatility Compression (Cheap Volatility -> Buy Option Directionally)
        if regime == "COMPRESSION":
            # Bullish trend: spot > vwap and rsi > 52
            if spot > vwap and rsi_val >= 52.0:
                entry = normalize_price(spot, ctx.underlying)
                stop = normalize_price(spot - (Decimal("1.0") * atr), ctx.underlying)
                risk_pts = entry - stop
                if risk_pts <= Decimal("0"):
                    return None

                t1 = normalize_price(entry + (risk_pts * Decimal("1.5")), ctx.underlying)
                t2 = normalize_price(entry + (risk_pts * Decimal("2.5")), ctx.underlying)

                opt = resolve_option_contract(ctx.underlying, spot, "CE", moneyness="ATM")

                return make_candidate(
                    ctx,
                    strategy=self.name,
                    direction="LONG_CALL",
                    entry_min=entry - (Decimal("0.10") * atr),
                    entry_max=entry + (Decimal("0.10") * atr),
                    trigger=entry,
                    stop_loss=stop,
                    target_1=t1,
                    target_2=t2,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.5,
                    signal_type="INTRADAY",
                    is_scalp=False,
                    overall_confidence=78.5,
                    option_contract=opt,
                    rationale=[
                        f"IV Compression setup: IV={raw_iv:.1%}, RV={rv:.1%}, IV/RV={raw_iv/max(rv, 0.001):.2f}",
                        f"Cheap option premium with directional momentum (RSI={rsi_val:.1f} >= 52, Price > VWAP)",
                    ],
                )

            # Bearish trend: spot < vwap and rsi < 48
            elif spot < vwap and rsi_val <= 48.0:
                entry = normalize_price(spot, ctx.underlying)
                stop = normalize_price(spot + (Decimal("1.0") * atr), ctx.underlying)
                risk_pts = stop - entry
                if risk_pts <= Decimal("0"):
                    return None

                t1 = normalize_price(entry - (risk_pts * Decimal("1.5")), ctx.underlying)
                t2 = normalize_price(entry - (risk_pts * Decimal("2.5")), ctx.underlying)

                opt = resolve_option_contract(ctx.underlying, spot, "PE", moneyness="ATM")

                return make_candidate(
                    ctx,
                    strategy=self.name,
                    direction="LONG_PUT",
                    entry_min=entry - (Decimal("0.10") * atr),
                    entry_max=entry + (Decimal("0.10") * atr),
                    trigger=entry,
                    stop_loss=stop,
                    target_1=t1,
                    target_2=t2,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.5,
                    signal_type="INTRADAY",
                    is_scalp=False,
                    overall_confidence=78.5,
                    option_contract=opt,
                    rationale=[
                        f"IV Compression setup: IV={raw_iv:.1%}, RV={rv:.1%}, IV/RV={raw_iv/max(rv, 0.001):.2f}",
                        f"Cheap option premium with downward momentum (RSI={rsi_val:.1f} <= 48, Price < VWAP)",
                    ],
                )

        # Regime B: Volatility Expansion (Expensive Volatility -> Mean Reversion Fade)
        elif regime == "EXPANSION":
            # Overbought fade -> LONG_PUT
            if rsi_val >= 68.0 and spot > vwap:
                entry = normalize_price(spot, ctx.underlying)
                stop = normalize_price(spot + (Decimal("0.8") * atr), ctx.underlying)
                risk_pts = stop - entry
                if risk_pts <= Decimal("0"):
                    return None

                t1 = normalize_price(max(entry - (risk_pts * Decimal("1.5")), vwap), ctx.underlying)
                t2 = normalize_price(entry - (risk_pts * Decimal("2.0")), ctx.underlying)

                opt = resolve_option_contract(ctx.underlying, spot, "PE", moneyness="ATM")

                return make_candidate(
                    ctx,
                    strategy=self.name,
                    direction="LONG_PUT",
                    entry_min=entry - (Decimal("0.10") * atr),
                    entry_max=entry + (Decimal("0.10") * atr),
                    trigger=entry,
                    stop_loss=stop,
                    target_1=t1,
                    target_2=t2,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.0,
                    signal_type="INTRADAY",
                    is_scalp=False,
                    overall_confidence=78.0,
                    option_contract=opt,
                    rationale=[
                        f"IV Expansion fade: IV={raw_iv:.1%}, RV={rv:.1%}, IV/RV={raw_iv/max(rv, 0.001):.2f}",
                        f"Harvesting volatility crush on overbought condition (RSI={rsi_val:.1f} >= 68)",
                    ],
                )

            # Oversold fade -> LONG_CALL
            elif rsi_val <= 32.0 and spot < vwap:
                entry = normalize_price(spot, ctx.underlying)
                stop = normalize_price(spot - (Decimal("0.8") * atr), ctx.underlying)
                risk_pts = entry - stop
                if risk_pts <= Decimal("0"):
                    return None

                t1 = normalize_price(min(entry + (risk_pts * Decimal("1.5")), vwap), ctx.underlying)
                t2 = normalize_price(entry + (risk_pts * Decimal("2.0")), ctx.underlying)

                opt = resolve_option_contract(ctx.underlying, spot, "CE", moneyness="ATM")

                return make_candidate(
                    ctx,
                    strategy=self.name,
                    direction="LONG_CALL",
                    entry_min=entry - (Decimal("0.10") * atr),
                    entry_max=entry + (Decimal("0.10") * atr),
                    trigger=entry,
                    stop_loss=stop,
                    target_1=t1,
                    target_2=t2,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.0,
                    signal_type="INTRADAY",
                    is_scalp=False,
                    overall_confidence=78.0,
                    option_contract=opt,
                    rationale=[
                        f"IV Expansion fade: IV={raw_iv:.1%}, RV={rv:.1%}, IV/RV={raw_iv/max(rv, 0.001):.2f}",
                        f"Harvesting volatility crush on oversold condition (RSI={rsi_val:.1f} <= 32)",
                    ],
                )

        return None
