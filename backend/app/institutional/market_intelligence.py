"""
Market Intelligence & Price Action Engine — §§25,26,27,28,29,69
Central market-understanding layer. Fuses evidence from all analysis modules
before generating breakout/setup signal (§1 — coherent MI layer, not loosely connected indicators).
Organizes evidence into independent dimensions, identifies supporting/contradictory/missing/stale/invalid.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Any
from enum import Enum

from app.algo.money import D
from app.institutional.instrument_registry import CapabilityMap
from app.institutional.events import InstrumentEvent

DataState = Literal["VALID", "MISSING", "STALE", "NOT_APPLICABLE", "INVALID"]
Trend = Literal["BULLISH", "BEARISH", "NEUTRAL", "RANGING"]
Structure = Literal["HH_HL", "LL_LH", "HH_HL_MIXED", "RANGE", "UNKNOWN"]
MomentumState = Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "DIVERGENT"]
MarketRegime = Literal["TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING", "VOLATILE", "BREAKOUT", "REVERSAL"]


@dataclass
class Evidence:
    dimension: str  # PRICE_ACTION, STRUCTURE, MOMENTUM, PARTICIPATION, POSITIONING, VOLATILITY, LIQUIDITY, MARKET_REGIME
    signal: str
    weight: int = 1
    detail: str = ""
    state: DataState = "VALID"


@dataclass
class MarketContext:
    instrument: str
    timestamp_utc: int
    asset_class: str
    market_session: str
    data_quality: DataState = "VALID"
    data_freshness: str = "LIVE"  # LIVE/RECENT/STALE/DISCONNECTED/FEED_DEGRADED etc

    price_action: dict[str, Any] = field(default_factory=dict)
    levels: dict[str, list] = field(default_factory=dict)
    participation: dict[str, str] = field(default_factory=dict)
    positioning: dict[str, str] = field(default_factory=dict)
    technical: dict[str, str] = field(default_factory=dict)

    scores: dict[str, int] = field(default_factory=dict)
    supporting_evidence: list[Evidence] = field(default_factory=list)
    conflicting_evidence: list[Evidence] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    stale_evidence: list[str] = field(default_factory=list)
    invalid_evidence: list[str] = field(default_factory=list)

    cross_market: dict[str, Any] = field(default_factory=dict)
    synchronization_status: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "timestamp_utc": self.timestamp_utc,
            "asset_class": self.asset_class,
            "market_session": self.market_session,
            "data_quality": self.data_quality,
            "data_freshness": self.data_freshness,
            "price_action": self.price_action,
            "levels": self.levels,
            "participation": self.participation,
            "positioning": self.positioning,
            "technical": self.technical,
            "scores": self.scores,
            "supporting_evidence": [{"dimension": e.dimension, "signal": e.signal, "detail": e.detail, "state": e.state} for e in self.supporting_evidence],
            "conflicting_evidence": [{"dimension": e.dimension, "signal": e.signal, "detail": e.detail, "state": e.state} for e in self.conflicting_evidence],
            "missing_evidence": self.missing_evidence,
            "stale_evidence": self.stale_evidence,
            "invalid_evidence": self.invalid_evidence,
            "cross_market": self.cross_market,
            "synchronization_status": self.synchronization_status,
        }


class MarketIntelligenceEngine:
    """
    Consumes all validated available analysis-module outputs (§25) and determines full market state.
    Does NOT decide breakout — that's BreakoutStrategyEngine. Separations enforced (§2).
    """

    def evaluate(
        self,
        instrument_id: str,
        canonical_ts_ms: int | None = None,
        # All module inputs — asset-specific via CapabilityMap
        spot_price: Decimal | None = None,
        futures_price: Decimal | None = None,
        vwap: Decimal | None = None,
        volumes: dict[str, Any] | None = None,
        oi_data: dict[str, Any] | None = None,
        options_data: dict[str, Any] | None = None,  # PCR, OI chain etc.
        futures_basis: Decimal | None = None,
        breadth: dict[str, Any] | None = None,
        support_resistance: dict[str, list] | None = None,
        multi_timeframe: dict[str, str] | None = None,  # 1m/3m/5m/15m structure
        volatility: dict[str, Any] | None = None,
        liquidity: dict[str, Any] | None = None,
        # Crypto-specific
        funding: dict[str, Any] | None = None,
        liquidations: dict[str, Any] | None = None,
        basis: Decimal | None = None,
        long_short: dict[str, Any] | None = None,
        # Cross-market
        synchronized_snapshot: Any | None = None,  # SynchronizedSnapshot
        data_health: str = "LIVE",
        feed_health: str = "HEALTHY",
        market_session: str = "OPEN",
    ) -> MarketContext:
        canonical_ts_ms = canonical_ts_ms or int(time.time()*1000)
        try:
            from app.institutional.instrument_registry import asset_registry
            prof = asset_registry.get(instrument_id)
            asset_class = prof.asset_class if prof else "INDEX"
        except Exception:
            asset_class = "INDEX"

        # Data state semantics (§28)
        def _state(val, applicable: bool) -> DataState:
            if not applicable:
                return "NOT_APPLICABLE"
            if val is None:
                return "MISSING"
            if data_health in ("STALE", "FEED_DEGRADED", "DISCONNECTED"):
                return "STALE"
            if feed_health == "FEED_DEGRADED":
                return "INVALID"
            return "VALID"

        supporting: list[Evidence] = []
        conflicting: list[Evidence] = []
        missing: list[str] = []
        stale: list[str] = []
        invalid: list[str] = []

        # Helper to track
        def add_evidence(dim: str, signal: str, detail: str = "", is_supporting: bool = True, val_available: bool = True, applicable: bool = True):
            state = _state(val_available if val_available else None, applicable)
            ev = Evidence(dimension=dim, signal=signal, detail=detail, state=state)
            if state == "MISSING": missing.append(f"{dim}:{signal}")
            elif state == "STALE": stale.append(f"{dim}:{signal}")
            elif state == "INVALID": invalid.append(f"{dim}:{signal}")
            elif state == "NOT_APPLICABLE": pass
            else:
                (supporting if is_supporting else conflicting).append(ev)

        # ── PRICE ACTION ──────────────────────────────────────────────
        structure: Structure = "UNKNOWN"
        trend: Trend = "NEUTRAL"
        momentum: MomentumState = "NEUTRAL"
        location = "UNKNOWN"
        if multi_timeframe:
            # Derive structure from timeframe biases
            bullish_ct = sum(1 for v in multi_timeframe.values() if "BULL" in v.upper())
            bearish_ct = sum(1 for v in multi_timeframe.values() if "BEAR" in v.upper())
            if bullish_ct >= 3: trend = "BULLISH"; structure = "HH_HL"
            elif bearish_ct >= 3: trend = "BEARISH"; structure = "LL_LH"
            elif bullish_ct == bearish_ct: trend = "RANGING"; structure = "RANGE"

        if spot_price is not None and vwap is not None:
            vwap_rel = "ABOVE" if spot_price > vwap else "BELOW" if spot_price < vwap else "AT"
        else:
            vwap_rel = "UNKNOWN"

        # ── PARTICIPATION ─────────────────────────────────────────────
        vol_state = "UNKNOWN"
        if volumes:
            ch = volumes.get("volume_change", 0)
            if ch > 0.3: vol_state = "STRONG"; add_evidence("PARTICIPATION", "volume expansion", f"vol change {ch:.0%}", True, True, True)
            elif ch < -0.2: vol_state = "WEAK"; add_evidence("PARTICIPATION", "volume contraction", f"vol change {ch:.0%}", False, True, True)
            else: vol_state = "NORMAL"

        breadth_state = "UNKNOWN"
        if CapabilityMap.supports(instrument_id, "breadth") and breadth is not None:
            breadth_state = breadth.get("breadth", "UNKNOWN")
        elif not CapabilityMap.supports(instrument_id, "breadth"):
            breadth_state = "NOT_APPLICABLE"

        # ── POSITIONING ───────────────────────────────────────────────
        fut_state = "UNKNOWN"
        if oi_data:
            oi_ch = oi_data.get("oi_change_pct", 0)
            if futures_price and spot_price:
                basis_val = futures_price - spot_price
                if oi_ch > 5 and basis_val > 0: fut_state = "LONG_BUILDUP"; add_evidence("POSITIONING", "futures long buildup", True, detail=f"OI {oi_ch:.1f}% basis {basis_val}")
                elif oi_ch > 5 and basis_val < 0: fut_state = "SHORT_BUILDUP"
                elif oi_ch < -5: fut_state = "SHORT_COVERING_OR_LONG_UNWINDING"

        opt_state = "UNKNOWN"
        if CapabilityMap.supports(instrument_id, "pcr") or CapabilityMap.supports(instrument_id, "options_chain"):
            if options_data:
                pcr = options_data.get("pcr", 1.0)
                if pcr > 1.2: opt_state = "BULLISH"; add_evidence("POSITIONING", "options bullish PCR", f"PCR {pcr:.2f}")
                elif pcr < 0.8: opt_state = "BEARISH"
                elif options_data.get("call_oi_near_resistance"): opt_state = "CALL_RESISTANCE"; add_evidence("POSITIONING", "call OI near resistance", is_supporting=False)
        else:
            # BTCUSD — evaluate funding / long-short instead
            if funding and funding.get("rate") is not None:
                fr = funding["rate"]
                if abs(fr) > 0.001: add_evidence("POSITIONING", "elevated funding", f"funding {fr:.4f}", is_supporting=False)

        # ── VOLATILITY / LIQUIDITY / REGIME ───────────────────────────
        vol_regime = "UNKNOWN"
        if volatility:
            vol_ch = volatility.get("volatility_change", 0)
            if vol_ch > 0.2: vol_regime = "EXPANDING"; add_evidence("VOLATILITY", "volatility expanding", is_supporting=True)
            elif vol_ch < -0.2: vol_regime = "CONTRACTING"
            else: vol_regime = "STABLE"

        liq_state = "UNKNOWN"
        if liquidity:
            liq_state = liquidity.get("state", "UNKNOWN")
            if liq_state == "THIN": add_evidence("LIQUIDITY", "thin liquidity", is_supporting=False)

        # Regime
        regime: MarketRegime = "RANGING"
        if trend == "BULLISH" and vol_regime == "EXPANDING": regime = "TRENDING_BULLISH"
        elif trend == "BEARISH" and vol_regime == "EXPANDING": regime = "TRENDING_BEARISH"
        elif vol_regime == "EXPANDING" and trend == "NEUTRAL": regime = "VOLATILE"

        # ── LEVELS ────────────────────────────────────────────────────
        levels: dict[str, list] = {"support": [], "resistance": []}
        if support_resistance:
            levels = {"support": support_resistance.get("support", []), "resistance": support_resistance.get("resistance", [])}
            if spot_price and levels["resistance"]:
                nearest_res = min(levels["resistance"], key=lambda x: abs(D(x) - spot_price)) if levels["resistance"] else None
                if nearest_res and abs(D(nearest_res) - spot_price) / spot_price < D("0.003"):
                    location = "NEAR_RESISTANCE"; add_evidence("PRICE_ACTION", "near resistance", f"res {nearest_res}", is_supporting=False)
                elif nearest_res and spot_price < D(nearest_res):
                    location = "BELOW_RESISTANCE"

        # ── SCORES (independent dimensions, not simple average — §26) ──
        # Evidence-fused scores per dimension
        # Do NOT do Price 20% + Volume 20% + OI 20% when correlated — organize into independent dimensions
        bullish = 50
        bearish = 50
        breakout_pressure = 50
        breakdown_pressure = 50
        false_breakout_risk = 30

        if trend == "BULLISH": bullish += 15; bearish -= 10
        if trend == "BEARISH": bearish += 15; bullish -= 10
        if vol_state == "STRONG" and trend == "BULLISH": breakout_pressure += 15; bullish += 7
        if vol_state == "STRONG" and trend == "BEARISH": breakdown_pressure += 15; bearish += 7
        if vwap_rel == "ABOVE" and trend == "BULLISH": bullish += 8; breakout_pressure += 8
        if vwap_rel == "BELOW" and trend == "BEARISH": bearish += 8; breakdown_pressure += 8
        if opt_state == "CALL_RESISTANCE": false_breakout_risk += 20; bullish -= 5
        if liq_state == "THIN": false_breakout_risk += 25
        if regime == "VOLATILE": false_breakout_risk += 15
        # Clamp
        def _clamp(v): return max(0, min(100, int(v)))
        scores = {
            "bullish_score": _clamp(bullish),
            "bearish_score": _clamp(bearish),
            "breakout_pressure": _clamp(breakout_pressure),
            "breakdown_pressure": _clamp(breakdown_pressure),
            "false_breakout_risk": _clamp(false_breakout_risk),
        }

        # Cross-market confirmation where valid
        cross: dict[str, Any] = {}
        sync_status = "UNKNOWN"
        if synchronized_snapshot:
            # support passed-in SynchronizedSnapshot
            sync_status = getattr(synchronized_snapshot, "status", "UNKNOWN")
            if sync_status == "SYNCHRONIZED":
                add_evidence("MARKET_REGIME", "cross-market synchronized", detail=f"Δt {getattr(synchronized_snapshot, 'delta_ms', '?')}ms")
                cross["confirmation"] = "VALID"
            elif sync_status == "CROSS_MARKET_DATA_NOT_SYNCHRONIZED":
                add_evidence("MARKET_REGIME", "cross-market unsynced", detail=str(getattr(synchronized_snapshot, "reason", "")), is_supporting=False)
                invalid.append("CROSS_MARKET_DATA_NOT_SYNCHRONIZED")
                cross["confirmation"] = "INVALID"
            elif sync_status in ("STALE_INSTRUMENT", "MISSING_INSTRUMENT"):
                stale.append(f"cross_market:{sync_status}")
                cross["confirmation"] = "STALE"

        price_action = {"structure": structure, "trend": trend, "momentum": momentum, "location": location}
        participation = {"volume": vol_state, "breadth": breadth_state}
        positioning = {"futures": fut_state, "options": opt_state, "oi": vol_state}
        technical = {"vwap": vwap_rel, "volatility": vol_regime, "regime": regime}

        ctx = MarketContext(
            instrument=instrument_id.upper(),
            timestamp_utc=canonical_ts_ms,
            asset_class=asset_class,
            market_session=market_session,
            data_quality="VALID" if data_health == "LIVE" else ("STALE" if "STALE" in data_health else "VALID") if feed_health == "HEALTHY" else "INVALID",
            data_freshness=data_health,
            price_action=price_action,
            levels=levels,
            participation=participation,
            positioning=positioning,
            technical=technical,
            scores=scores,
            supporting_evidence=supporting,
            conflicting_evidence=conflicting,
            missing_evidence=missing,
            stale_evidence=stale,
            invalid_evidence=invalid,
            cross_market=cross,
            synchronization_status=sync_status,
        )
        return ctx

    def explain(self, ctx: MarketContext) -> str:
        """§69 explainability — textual dump"""
        lines = [
            f"MARKET INTELLIGENCE — {ctx.instrument} @ {ctx.timestamp_utc}",
            f"Regime: {ctx.technical.get('regime')} | Trend: {ctx.price_action.get('trend')} | Structure: {ctx.price_action.get('structure')}",
            f"Bullish {ctx.scores.get('bullish_score')} / Bearish {ctx.scores.get('bearish_score')} | Breakout pressure {ctx.scores.get('breakout_pressure')} | False-breakout risk {ctx.scores.get('false_breakout_risk')}",
            "Supporting: " + ", ".join(e.signal for e in ctx.supporting_evidence) if ctx.supporting_evidence else "Supporting: —",
            "Conflicts: " + ", ".join(e.signal for e in ctx.conflicting_evidence) if ctx.conflicting_evidence else "Conflicts: —",
            f"Cross-market: {ctx.synchronization_status} {ctx.cross_market}",
        ]
        return "\n".join(lines)


market_intelligence_engine = MarketIntelligenceEngine()
