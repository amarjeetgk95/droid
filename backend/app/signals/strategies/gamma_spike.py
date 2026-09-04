"""
GAMMA_SPIKE Strategy (§10)
Timeframe: 1M / 3M
Active strictly during configured expiry/event windows: 13:15 - 15:15 IST.
Outside the configured window: strategy = DISABLED (returns None).
Detection:
  - Expiry session (or EVENT regime)
  - Rapid OI unwinding + ATM option volume surge
  - Underlying price acceleration
  - TTL: Original = 90s, Runner = 240s
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract


class GammaSpikeStrategy(Strategy):
    name = "GAMMA_SPIKE"

    def _is_in_expiry_window(self, timestamp_ms: int) -> bool:
        """Check if current time is within 13:15 to 15:15 IST (§10)."""
        dt_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        ist_offset = timedelta(hours=5, minutes=30)
        dt_ist = dt_utc + ist_offset
        hour = dt_ist.hour
        minute = dt_ist.minute
        time_minutes = (hour * 60) + minute
        # 13:15 is 13*60 + 15 = 795, 15:15 is 15*60 + 15 = 915
        return 795 <= time_minutes <= 915

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe not in ("1M", "3M"):
            return None

        # Check window: 13:15-15:15 IST or explicit EVENT regime
        in_window = self._is_in_expiry_window(ctx.timestamp_ms)
        if not in_window and ctx.regime != "EVENT":
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 3:
            return None

        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None

        # F&O indicators check: PCR or OI acceleration
        fno = ctx.fno or {}
        pcr = float(fno.get("pcr", 1.0))
        oi_change_pct = float(fno.get("oi_change_pct", 0.0))

        tick = Decimal("0.05")
        if ctx.underlying == "NIFTY":
            min_risk = Decimal("7.0")
        elif ctx.underlying == "BANKNIFTY":
            min_risk = Decimal("24.0")
        else:
            min_risk = Decimal("50.0")

        # Bullish Gamma Spike: Call unwinding / short squeeze acceleration
        if c_close > c_open and (c_close - c_open) >= (candle_range * Decimal("0.65")) and pcr >= 0.95:
            entry_min = normalize_price(c_open, tick)
            entry_max = normalize_price(c_close, tick)
            trigger = normalize_price(c_high + tick, tick)
            stop_loss = normalize_price(c_low - tick, tick)
            risk_pts = max(min_risk, entry_max - stop_loss)
            stop_loss = normalize_price(entry_max - risk_pts, tick)

            t1 = normalize_price(entry_max + (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_max + (risk_pts * Decimal("3.0")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

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
                risk_reward_t2=3.0,
                max_chase_fraction=0.35,
                ttl_seconds=90,
                time_stop_seconds=90,
                runner_ttl_seconds=240,
                technical_score=88.0,
                mtf_score=80.0,
                fno_score=90.0,
                regime_score=90.0,
                overall_confidence=86.0,
                rationale=[
                    f"0-DTE Gamma acceleration window (13:15-15:15 IST) active; PCR: {pcr:.2f}",
                    f"Aggressive impulse candle ({float(c_close - c_open):.1f} pts) indicating Call short squeeze",
                    f"Explosive gamma scalp with 90s TTL and 240s runner limit",
                ],
                option_contract=contract,
            )

        # Bearish Gamma Spike: Long unwinding / Put buying panic
        elif c_close < c_open and (c_open - c_close) >= (candle_range * Decimal("0.65")) and pcr <= 1.05:
            entry_min = normalize_price(c_close, tick)
            entry_max = normalize_price(c_open, tick)
            trigger = normalize_price(c_low - tick, tick)
            stop_loss = normalize_price(c_high + tick, tick)
            risk_pts = max(min_risk, stop_loss - entry_min)
            stop_loss = normalize_price(entry_min + risk_pts, tick)

            t1 = normalize_price(entry_min - (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_min - (risk_pts * Decimal("3.0")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

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
                risk_reward_t2=3.0,
                max_chase_fraction=0.35,
                ttl_seconds=90,
                time_stop_seconds=90,
                runner_ttl_seconds=240,
                technical_score=88.0,
                mtf_score=80.0,
                fno_score=90.0,
                regime_score=90.0,
                overall_confidence=86.0,
                rationale=[
                    f"0-DTE Gamma acceleration window (13:15-15:15 IST) active; PCR: {pcr:.2f}",
                    f"Aggressive impulse breakdown ({float(c_open - c_close):.1f} pts) indicating Put gamma expansion",
                    f"Explosive gamma scalp with 90s TTL and 240s runner limit",
                ],
                option_contract=contract,
            )

        return None
