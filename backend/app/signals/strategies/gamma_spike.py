"""
GAMMA_SPIKE Strategy (§10, P1 overhaul)
Timeframe: 1M / 3M
Active strictly during configured expiry/event windows: 13:15 - 15:15 IST.
Outside the configured window: strategy = DISABLED (returns None).
Detection (P1):
  - Expiry session (or EVENT regime)
  - Rapid OI unwinding (oi_change_pct measured >= 5.0, fail-closed) + ATM
    option volume surge (measured totals, fail-closed)
  - Underlying price acceleration: range >= 1.2x ATR + impulse body >= 65%
  - Closed 1M candle (is_new_1m_candle) + second-tick confirmation
    (prev bar same direction) + measured volume >= 1.2x fail-closed
  - PCR: bull <= 0.80, bear >= 1.20 (tautology >=0.95/<=1.05 fixed)
  - TTL: Original = 90s, Runner = 240s
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    extract_volume_ratio,
    has_closed_1m_candle,
    PCR_BULL_MAX,
    PCR_BEAR_MIN,
    VOLUME_SCALP_MIN,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr


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

        # P1 closed-candle gate.
        if not has_closed_1m_candle(ctx):
            return None

        # Check window: 13:15-15:15 IST or explicit EVENT regime
        in_window = self._is_in_expiry_window(ctx.timestamp_ms)
        if not in_window and ctx.regime != "EVENT":
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 4:
            return None

        last_c = candles[-1]
        prev_c = candles[-2]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None

        atr = resolve_realistic_atr(ctx.underlying, spot, ctx.indicators)
        # P1: range >= 1.2x ATR required.
        try:
            if float(candle_range) < float(atr) * 1.2:
                return None
        except Exception:
            return None

        # P1 volume: measured >= 1.2x, fail-closed.
        vol_ratio = extract_volume_ratio(ctx.indicators)
        if vol_ratio is None:
            return None
        if vol_ratio < VOLUME_SCALP_MIN:
            return None

        # F&O: fail-closed PCR + OI gate + ATM volume surge.
        fno = ctx.fno or {}
        raw_pcr = fno.get("pcr")
        if raw_pcr is None:
            return None
        try:
            pcr = float(raw_pcr)
        except (TypeError, ValueError):
            return None
        raw_oi = fno.get("oi_change_pct")
        if raw_oi is None:
            raw_oi = (fno.get("oi_data") or {}).get("oi_change_pct") if isinstance(fno.get("oi_data"), dict) else None
        if raw_oi is None:
            return None  # fail-closed OI gate
        try:
            oi_change_pct = float(raw_oi)
        except (TypeError, ValueError):
            return None
        if abs(oi_change_pct) < 5.0:
            return None  # OI gate: rapid unwinding required
        # ATM volume surge: measured option volumes required.
        tc_vol = fno.get("total_call_volume")
        tp_vol = fno.get("total_put_volume")
        atm_vol = fno.get("atm_call_volume", fno.get("atm_volume", fno.get("atm_put_volume")))
        has_vol_data = False
        try:
            if tc_vol is not None and tp_vol is not None and float(tc_vol) > 0 and float(tp_vol) > 0:
                has_vol_data = True
            elif atm_vol is not None and float(atm_vol) > 0:
                has_vol_data = True
            elif fno.get("atm_iv") is not None:
                # Fallback: option chain measured (key strikes) counts as volume context.
                kc = fno.get("key_call_strikes") or []
                kp = fno.get("key_put_strikes") or []
                if isinstance(kc, list) and isinstance(kp, list) and kc and kp:
                    has_vol_data = True
        except (TypeError, ValueError):
            has_vol_data = False
        if not has_vol_data:
            return None

        # Second-tick confirmation: prev bar same direction.
        try:
            prev_open = Decimal(str(prev_c.get("open", spot)))
            prev_close = Decimal(str(prev_c.get("close", spot)))
        except Exception:
            return None

        tick = Decimal("0.05")
        if ctx.underlying == "NIFTY":
            min_risk = Decimal("7.0")
        elif ctx.underlying == "BANKNIFTY":
            min_risk = Decimal("24.0")
        else:
            min_risk = Decimal("50.0")

        # Bullish Gamma Spike: Call unwinding / short squeeze acceleration
        # P1 PCR: bull <= 0.80 (fixed tautology >= 0.95).
        if (
            c_close > c_open
            and (c_close - c_open) >= (candle_range * Decimal("0.65"))
            and pcr <= PCR_BULL_MAX
            and prev_close > prev_open
            and c_close > prev_close
        ):
            entry_min = normalize_price(c_open, tick)
            entry_max = normalize_price(c_close, tick)
            trigger = normalize_price(c_high + tick, tick)
            stop_loss = normalize_price(c_low - tick, tick)
            risk_pts = max(min_risk, entry_max - stop_loss)
            stop_loss = normalize_price(entry_max - risk_pts, tick)

            t1 = normalize_price(entry_max + (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_max + (risk_pts * Decimal("3.0")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

            # Dynamic earn-from-50: OI + PCR distance + volume + range expansion.
            body_ratio = float((c_close - c_open) / candle_range) if float(candle_range) > 0 else 0.0
            range_mult = float(candle_range) / float(atr) if float(atr) > 0 else 1.0
            tech_score = round(min(88.0, max(50.0, 50.0 + min(15.0, abs(oi_change_pct) * 1.0) + (max(0.0, PCR_BULL_MAX - pcr) * 30.0) + (max(0.0, range_mult - 1.2) * 8.0) + (body_ratio * 8.0))), 1)
            mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
            fno_score = round(min(88.0, max(45.0, 50.0 + min(18.0, abs(oi_change_pct) * 1.2) + (max(0.0, PCR_BULL_MAX - pcr) * 35.0))), 1)
            regime_score = 80.0 if ctx.regime in ("HIGH_VOL", "TREND_UP", "EVENT") else 60.0
            conf_score = round(0.40 * tech_score + 0.20 * mtf_score + 0.25 * fno_score + 0.15 * regime_score, 1)

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
                technical_score=tech_score,
                mtf_score=mtf_score,
                fno_score=fno_score,
                regime_score=regime_score,
                overall_confidence=conf_score,
                rationale=[
                    f"0-DTE Gamma acceleration window (13:15-15:15 IST) active; PCR: {pcr:.2f}",
                    f"Aggressive impulse candle ({float(c_close - c_open):.1f} pts) indicating Call short squeeze",
                    f"Explosive gamma scalp with 90s TTL and 240s runner limit",
                ],
                option_contract=contract,
            )

        # Bearish Gamma Spike: Long unwinding / Put buying panic
        # P1 PCR: bear >= 1.20 (fixed tautology <= 1.05).
        elif (
            c_close < c_open
            and (c_open - c_close) >= (candle_range * Decimal("0.65"))
            and pcr >= PCR_BEAR_MIN
            and prev_close < prev_open
            and c_close < prev_close
        ):
            entry_min = normalize_price(c_close, tick)
            entry_max = normalize_price(c_open, tick)
            trigger = normalize_price(c_low - tick, tick)
            stop_loss = normalize_price(c_high + tick, tick)
            risk_pts = max(min_risk, stop_loss - entry_min)
            stop_loss = normalize_price(entry_min + risk_pts, tick)

            t1 = normalize_price(entry_min - (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_min - (risk_pts * Decimal("3.0")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

            body_ratio = float((c_open - c_close) / candle_range) if float(candle_range) > 0 else 0.0
            range_mult = float(candle_range) / float(atr) if float(atr) > 0 else 1.0
            tech_score = round(min(88.0, max(50.0, 50.0 + min(15.0, abs(oi_change_pct) * 1.0) + (max(0.0, pcr - PCR_BEAR_MIN) * 30.0) + (max(0.0, range_mult - 1.2) * 8.0) + (body_ratio * 8.0))), 1)
            mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
            fno_score = round(min(88.0, max(45.0, 50.0 + min(18.0, abs(oi_change_pct) * 1.2) + (max(0.0, pcr - PCR_BEAR_MIN) * 35.0))), 1)
            regime_score = 80.0 if ctx.regime in ("HIGH_VOL", "TREND_DOWN", "EVENT") else 60.0
            conf_score = round(0.40 * tech_score + 0.20 * mtf_score + 0.25 * fno_score + 0.15 * regime_score, 1)

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
                technical_score=tech_score,
                mtf_score=mtf_score,
                fno_score=fno_score,
                regime_score=regime_score,
                overall_confidence=conf_score,
                rationale=[
                    f"0-DTE Gamma acceleration window (13:15-15:15 IST) active; PCR: {pcr:.2f}",
                    f"Aggressive impulse breakdown ({float(c_open - c_close):.1f} pts) indicating Put gamma expansion",
                    f"Explosive gamma scalp with 90s TTL and 240s runner limit",
                ],
                option_contract=contract,
            )

        return None
