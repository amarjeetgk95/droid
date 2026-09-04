"""
VWAP_SCALP Strategy (§7)
Timeframe: 1M / 3M
Detection:
  - abs(price - VWAP) / VWAP >= 0.3%
  - Rejection wick + rejection close back toward VWAP
  - Initial Risk: NIFTY 6-8 pts, BANKNIFTY 22-28 pts (HIGH_VOL: 9-12 / 30-38)
  - Targets: T1 = 1.5R, T2 = 2.5R
  - TTL: Original = 240s, Runner = 480s
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract


class VWAPScalpStrategy(Strategy):
    name = "VWAP_SCALP"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        # VWAP Scalp runs on 1M/3M candles
        if ctx.timeframe not in ("1M", "3M"):
            return None

        # In trending regime, VWAP mean-reversion is suppressed (§15)
        if ctx.regime in ("TREND_UP", "TREND_DOWN"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        ind = ctx.indicators
        tick = Decimal("0.05")

        # Resolve VWAP
        vwap_val = ctx.vwap
        if vwap_val is None:
            raw_vwap = ind.get("vwap") or ind.get("trend", {}).get("vwap")
            if raw_vwap:
                vwap_val = Decimal(str(raw_vwap))
            else:
                return None

        if vwap_val <= Decimal("0"):
            return None

        # Check deviation >= 0.3%
        dev_pct = abs(spot - vwap_val) / vwap_val * Decimal("100")
        if dev_pct < Decimal("0.3"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 2:
            return None

        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None

        # Risk parameters by instrument (§7)
        is_high_vol = ctx.regime == "HIGH_VOL"
        if ctx.underlying == "NIFTY":
            base_risk = Decimal("10.0") if is_high_vol else Decimal("7.0")
        elif ctx.underlying == "BANKNIFTY":
            base_risk = Decimal("34.0") if is_high_vol else Decimal("25.0")
        else:  # SENSEX
            base_risk = Decimal("70.0") if is_high_vol else Decimal("50.0")

        # ── BULLISH REVERSAL TOWARD VWAP (Price below VWAP, bouncing up) ──
        if spot < vwap_val:
            lower_wick = min(c_open, c_close) - c_low
            if (lower_wick / candle_range) >= Decimal("0.30") and c_close >= c_open:
                entry_min = normalize_price(spot, tick)
                entry_max = normalize_price(spot + (candle_range * Decimal("0.2")), tick)
                trigger = normalize_price(c_high + tick, tick)
                stop_loss = normalize_price(c_low - tick, tick)
                risk_pts = max(base_risk, entry_min - stop_loss)
                stop_loss = normalize_price(entry_min - risk_pts, tick)

                t1 = normalize_price(entry_min + (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(min(vwap_val, entry_min + (risk_pts * Decimal("2.5"))), tick)
                # Strike selector: ATM or 1-strike ITM for CE (offset -1)
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=-1)

                return SignalCandidate(
                    underlying=ctx.underlying,
                    strategy=self.name,
                    direction="LONG_CALL",
                    timeframe=ctx.timeframe,
                    spot_price=spot,
                    signal_type="SCALP",
                    is_scalp=True,
                    entry_min=entry_min,
                    entry_max=entry_max,
                    trigger=trigger,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    risk_points=risk_pts,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.5,
                    max_chase_fraction=0.35 if is_high_vol else 0.50,
                    ttl_seconds=240,
                    time_stop_seconds=240,
                    runner_ttl_seconds=480,
                    technical_score=78.0,
                    mtf_score=70.0,
                    fno_score=75.0,
                    regime_score=85.0 if ctx.regime in ("RANGE", "LOW_VOL") else 70.0,
                    overall_confidence=78.0,
                    rationale=[
                        f"Price stretched {float(dev_pct):.2f}% below VWAP ({float(vwap_val)}) with bullish rejection wick",
                        f"Mean-reversion magnet targeting institutional session VWAP",
                        f"Micro-scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        # ── BEARISH REJECTION FROM VWAP (Price above VWAP, falling down) ──
        elif spot > vwap_val:
            upper_wick = c_high - max(c_open, c_close)
            if (upper_wick / candle_range) >= Decimal("0.30") and c_close <= c_open:
                entry_min = normalize_price(spot - (candle_range * Decimal("0.2")), tick)
                entry_max = normalize_price(spot, tick)
                trigger = normalize_price(c_low - tick, tick)
                stop_loss = normalize_price(c_high + tick, tick)
                risk_pts = max(base_risk, stop_loss - entry_max)
                stop_loss = normalize_price(entry_max + risk_pts, tick)

                t1 = normalize_price(entry_max - (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(max(vwap_val, entry_max - (risk_pts * Decimal("2.5"))), tick)
                # Strike selector: ATM or 1-strike ITM for PE (offset +1)
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=1)

                return SignalCandidate(
                    underlying=ctx.underlying,
                    strategy=self.name,
                    direction="LONG_PUT",
                    timeframe=ctx.timeframe,
                    spot_price=spot,
                    signal_type="SCALP",
                    is_scalp=True,
                    entry_min=entry_min,
                    entry_max=entry_max,
                    trigger=trigger,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    risk_points=risk_pts,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.5,
                    max_chase_fraction=0.35 if is_high_vol else 0.50,
                    ttl_seconds=240,
                    time_stop_seconds=240,
                    runner_ttl_seconds=480,
                    technical_score=78.0,
                    mtf_score=70.0,
                    fno_score=75.0,
                    regime_score=85.0 if ctx.regime in ("RANGE", "LOW_VOL") else 70.0,
                    overall_confidence=78.0,
                    rationale=[
                        f"Price extended {float(dev_pct):.2f}% above VWAP ({float(vwap_val)}) with bearish rejection wick",
                        f"Mean-reversion magnet targeting institutional session VWAP",
                        f"Micro-scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        return None
