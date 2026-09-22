"""
Absorption Reversal Strategy (Live Intraday Desk).

Detects institutional absorption at structural levels (Previous Day High/Low,
VWAP +/- 2std bands):
- High volume + small price displacement + strong rejection wick.
- Enters mean-reversion trade back towards VWAP.
- T1 = VWAP (or 1.2R), T2 = Opposite structural boundary (or 2.0R).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    ADX_TREND_CUTOFF,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr
from app.signals.strategies.candidate import make_candidate


def _extract_wicks(c: dict, spot: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    o = Decimal(str(c.get("open", spot)))
    h = Decimal(str(c.get("high", spot)))
    lo = Decimal(str(c.get("low", spot)))
    cl = Decimal(str(c.get("close", spot)))
    rng = h - lo
    if rng <= Decimal("0"):
        return Decimal("0"), Decimal("0"), rng
    lower_wick = min(o, cl) - lo
    upper_wick = h - max(o, cl)
    return lower_wick / rng, upper_wick / rng, rng


class AbsorptionReversalStrategy(Strategy):
    name = "ABSORPTION_REVERSAL"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if not ctx.candles or len(ctx.candles) < 3:
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        ind = ctx.indicators
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        if atr <= Decimal("0"):
            return None

        # Fail closed on unstable or extreme regimes
        if ctx.regime in ("UNSTABLE", "UNKNOWN"):
            return None

        vol_ratio = ind.get("volume_ratio")
        if vol_ratio is None:
            vol_ratio = 1.0
        try:
            vol_ratio_dec = Decimal(str(vol_ratio))
        except Exception:
            vol_ratio_dec = Decimal("1.0")

        # Must have volume expansion >= 1.25x
        if vol_ratio_dec < Decimal("1.25"):
            return None

        last_c = ctx.candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))

        # Displacement: |close - open| / atr <= 0.40 (absorption: big volume, small progress)
        disp = abs(c_close - c_open) / atr
        if disp > Decimal("0.40"):
            return None

        lower_wick_ratio, upper_wick_ratio, bar_range = _extract_wicks(last_c, spot)
        vwap = ctx.vwap or spot

        # Collect resistance and support reference levels
        resistance_levels: list[tuple[Decimal, str]] = []
        support_levels: list[tuple[Decimal, str]] = []

        bb = ind.get("bollinger_bands", {})
        if isinstance(bb, dict):
            bb_u = bb.get("upper")
            bb_l = bb.get("lower")
            if bb_u is not None:
                resistance_levels.append((Decimal(str(bb_u)), "VWAP_OR_BB_UPPER"))
            if bb_l is not None:
                support_levels.append((Decimal(str(bb_l)), "VWAP_OR_BB_LOWER"))

        # Check resistance absorption (Bearish Reversal -> LONG_PUT)
        for res_price, res_tag in resistance_levels:
            dist_atr = (res_price - spot) / atr
            if abs(dist_atr) <= Decimal("0.50") or c_high >= res_price - (Decimal("0.2") * atr):
                if upper_wick_ratio >= Decimal("0.50") and c_close < (c_high + c_low) / Decimal("2.0"):
                    # Trigger entry below the rejection bar's low
                    entry = normalize_price(c_low, ctx.underlying)
                    stop = normalize_price(c_high + (Decimal("0.25") * atr), ctx.underlying)
                    risk_pts = stop - entry
                    if risk_pts <= Decimal("0"):
                        continue

                    # Target: VWAP or 1.5R
                    t1 = normalize_price(min(entry - (risk_pts * Decimal("1.5")), vwap), ctx.underlying)
                    t2 = normalize_price(entry - (risk_pts * Decimal("2.5")), ctx.underlying)

                    opt = resolve_option_contract(
                        ctx.underlying,
                        spot,
                        "PE",
                        moneyness="ATM",
                    )

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
                        overall_confidence=79.0,
                        option_contract=opt,
                        rationale=[
                            f"Absorption Reversal at {res_tag} ({res_price:.1f})",
                            f"VolumeRatio={vol_ratio_dec:.2f}>=1.25, UpperWick={upper_wick_ratio:.2f}>=0.50, Disp={disp:.2f}<=0.40",
                            f"Targeting mean-reversion to VWAP ({vwap:.1f})",
                        ],
                    )

        # Check support absorption (Bullish Reversal -> LONG_CALL)
        for sup_price, sup_tag in support_levels:
            dist_atr = (spot - sup_price) / atr
            if abs(dist_atr) <= Decimal("0.50") or c_low <= sup_price + (Decimal("0.2") * atr):
                if lower_wick_ratio >= Decimal("0.50") and c_close > (c_high + c_low) / Decimal("2.0"):
                    # Trigger entry above the rejection bar's high
                    entry = normalize_price(c_high, ctx.underlying)
                    stop = normalize_price(c_low - (Decimal("0.25") * atr), ctx.underlying)
                    risk_pts = entry - stop
                    if risk_pts <= Decimal("0"):
                        continue

                    # Target: VWAP or 1.5R
                    t1 = normalize_price(max(entry + (risk_pts * Decimal("1.5")), vwap), ctx.underlying)
                    t2 = normalize_price(entry + (risk_pts * Decimal("2.5")), ctx.underlying)

                    opt = resolve_option_contract(
                        ctx.underlying,
                        spot,
                        "CE",
                        moneyness="ATM",
                    )

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
                        overall_confidence=79.0,
                        option_contract=opt,
                        rationale=[
                            f"Absorption Reversal at {sup_tag} ({sup_price:.1f})",
                            f"VolumeRatio={vol_ratio_dec:.2f}>=1.25, LowerWick={lower_wick_ratio:.2f}>=0.50, Disp={disp:.2f}<=0.40",
                            f"Targeting mean-reversion to VWAP ({vwap:.1f})",
                        ],
                    )

        return None
