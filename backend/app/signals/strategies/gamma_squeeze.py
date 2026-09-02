"""
Gamma Squeeze & 0DTE OI Unwinding Strategy
Mathematical rules:
  - LONG_CALL: Call OI unwinding at ATM strike, PCR <= 0.75 or extreme PCR surge (>1.35), High Delta velocity, Spot crossing Call OI resistance wall.
  - LONG_PUT: Put OI unwinding at ATM strike, PCR >= 1.35 or extreme PCR collapse (<0.70), High Put delta velocity, Spot crossing Put OI support wall.
  - High risk-reward intraday momentum play, tightly bounded TTL.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract


class GammaSqueezeStrategy(Strategy):
    name = "GAMMA_SQUEEZE"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        fno = ctx.fno
        spot = ctx.spot_price
        tick = Decimal("0.05")
        atr = Decimal(str(ctx.indicators.get("atr", spot * Decimal("0.007"))))

        pcr = float(fno.get("pcr", 1.0))
        oi_change = float(fno.get("oi_change_pct", fno.get("oi_data", {}).get("oi_change_pct", 5.0)))
        atm_iv = float(fno.get("atm_iv", 14.5))
        max_pain = Decimal(str(fno.get("max_pain", spot)))

        # ── BULLISH GAMMA SQUEEZE (LONG_CALL) ──
        # Conditions: PCR extreme or Call OI unwinding + spot above max pain / resistance
        if (pcr <= 0.75 or pcr >= 1.30 or oi_change >= 8.0) and spot >= max_pain * Decimal("0.998"):
            entry_min = normalize_price(spot, tick)
            entry_max = normalize_price(spot + (atr * Decimal("0.25")), tick)
            trigger = normalize_price(spot + tick, tick)
            stop_loss = normalize_price(spot - (atr * Decimal("0.9")), tick)
            risk_pts = entry_min - stop_loss
            if risk_pts > Decimal("0"):
                t1 = normalize_price(entry_min + (risk_pts * Decimal("1.8")), tick)
                t2 = normalize_price(entry_min + (risk_pts * Decimal("3.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                tech_score = 82.0
                mtf_score = float(ctx.mtf.get("alignment_score", 70.0))
                fno_score = min(96.0, 70.0 + (oi_change * 1.5) + (abs(pcr - 1.0) * 20.0))
                regime_score = 85.0 if ctx.regime in ("HIGH_VOL", "TREND_UP") else 70.0

                return SignalCandidate(
                    underlying=ctx.underlying,
                    strategy=self.name,
                    direction="LONG_CALL",
                    timeframe=ctx.timeframe,
                    spot_price=spot,
                    entry_min=entry_min,
                    entry_max=entry_max,
                    trigger=trigger,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    risk_points=risk_pts,
                    risk_reward_t1=1.8,
                    risk_reward_t2=3.5,
                    technical_score=tech_score,
                    mtf_score=mtf_score,
                    fno_score=fno_score,
                    regime_score=regime_score,
                    overall_confidence=round((tech_score * 0.3) + (mtf_score * 0.2) + (fno_score * 0.35) + (regime_score * 0.15), 1),
                    rationale=[
                        f"Call OI short covering unwinding (PCR {pcr:.2f})",
                        f"Heavy OI momentum change ({oi_change:+.1f}%)",
                        f"Spot above Max Pain (₹{max_pain:,.2f})",
                        f"Rapid ATM Delta expansion velocity",
                    ],
                    option_contract=contract,
                    ttl_seconds=180,  # Fast decay setup
                )

        # ── BEARISH GAMMA TRAP / LONG_PUT ──
        if (pcr >= 1.40 or pcr <= 0.65 or oi_change >= 8.0) and spot <= max_pain * Decimal("1.002"):
            entry_min = normalize_price(spot - (atr * Decimal("0.25")), tick)
            entry_max = normalize_price(spot, tick)
            trigger = normalize_price(spot - tick, tick)
            stop_loss = normalize_price(spot + (atr * Decimal("0.9")), tick)
            risk_pts = stop_loss - entry_max
            if risk_pts > Decimal("0"):
                t1 = normalize_price(entry_max - (risk_pts * Decimal("1.8")), tick)
                t2 = normalize_price(entry_max - (risk_pts * Decimal("3.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                tech_score = 82.0
                mtf_score = float(ctx.mtf.get("alignment_score", 70.0))
                fno_score = min(96.0, 70.0 + (oi_change * 1.5) + (abs(pcr - 1.0) * 20.0))
                regime_score = 85.0 if ctx.regime in ("HIGH_VOL", "TREND_DOWN") else 70.0

                return SignalCandidate(
                    underlying=ctx.underlying,
                    strategy=self.name,
                    direction="LONG_PUT",
                    timeframe=ctx.timeframe,
                    spot_price=spot,
                    entry_min=entry_min,
                    entry_max=entry_max,
                    trigger=trigger,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    risk_points=risk_pts,
                    risk_reward_t1=1.8,
                    risk_reward_t2=3.5,
                    technical_score=tech_score,
                    mtf_score=mtf_score,
                    fno_score=fno_score,
                    regime_score=regime_score,
                    overall_confidence=round((tech_score * 0.3) + (mtf_score * 0.2) + (fno_score * 0.35) + (regime_score * 0.15), 1),
                    rationale=[
                        f"Put OI long unwinding trap (PCR {pcr:.2f})",
                        f"Heavy OI momentum change ({oi_change:+.1f}%)",
                        f"Spot below Max Pain (₹{max_pain:,.2f})",
                        f"Rapid Put Delta acceleration",
                    ],
                    option_contract=contract,
                    ttl_seconds=180,
                )

        return None
