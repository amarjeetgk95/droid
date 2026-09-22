"""
Signal Fusion, Trigger Engine, Strategy Conflict Resolution — §26-31
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4
import structlog

from app.algo.money import D
from app.core.json_config import load_json_config

logger = structlog.get_logger()

# §26 default weights — single source of truth: backend/config/scoring_weights.json (v2).
# Kept inline as fallback if config file is missing (tests, minimal installs).
# required=False is intentional (fusion must stay non-fatal), but the shared
# loader logs json_config_fallback_default at WARNING so the fallback is never silent.
def _load_scoring_config() -> dict:
    return load_json_config("scoring_weights.json", required=False, default={})


_SCORING_CONFIG = _load_scoring_config()


def _load_scoring_weights_percent(config: dict | None = None) -> dict:
    w = ((config if config is not None else _SCORING_CONFIG).get("weights_percent", {}) or {})
    if w:
        try:
            return {k: Decimal(str(v)) for k, v in w.items() if k != "ml_max"}
        except Exception:
            pass
    return {
        "technical": Decimal("40"),
        "mtf": Decimal("20"),
        "fno": Decimal("15"),
        "regime": Decimal("10"),
        "ai": Decimal("10"),
        "event_risk": Decimal("5"),
    }


DEFAULT_WEIGHTS = _load_scoring_weights_percent()

# weights_version: single source = scoring_weights.json `version` (int). Exposed on
# every fused output so downstream (explain, audit, AI) can prove which bundle scored.
WEIGHTS_VERSION: int | str = _SCORING_CONFIG.get("version", 2)

# Unified thresholds (scoring_weights.json: fusion_long 62 / fusion_short 38 / armed 78).
# Armed threshold lives ONLY in scoring_weights.json thresholds.armed (78.0).
_TH = _SCORING_CONFIG.get("thresholds", {}) or {}
try:
    FUSION_LONG_THRESHOLD = Decimal(str(_TH.get("fusion_long", 62)))
except Exception:
    FUSION_LONG_THRESHOLD = Decimal("62")
try:
    FUSION_SHORT_THRESHOLD = Decimal(str(_TH.get("fusion_short", 38)))
except Exception:
    FUSION_SHORT_THRESHOLD = Decimal("38")
try:
    ARMED_THRESHOLD = Decimal(str(_TH.get("armed", 78.0)))
except Exception:
    ARMED_THRESHOLD = Decimal("78.0")


@dataclass
class SignalInputs:
    technical: dict = field(default_factory=dict)      # includes score etc
    mtf: dict = field(default_factory=dict)
    fno: dict = field(default_factory=dict)
    regime: dict = field(default_factory=dict)
    ai: dict = field(default_factory=dict)
    event_risk: dict = field(default_factory=dict)
    # per-strategy configurable weights
    weights: dict = field(default_factory=dict)


@dataclass
class Signal:
    signal_id: UUID
    strategy_id: str
    instrument_id: str | None
    symbol: str
    direction: Literal["LONG", "SHORT", "NO_TRADE"]
    timestamp: datetime
    market_snapshot_id: str | None
    technical_state: dict
    mtf_state: dict
    fo_state: dict
    regime: str | None
    ai_result: dict | None
    score: Decimal | None
    confidence: Decimal | None
    invalidation_conditions: dict
    # P0-5: decorrelation + version provenance. Defaults keep old call sites working.
    weights_version: int | str = 2
    correlation_penalty: Decimal = Decimal("0")
    subscores: dict = field(default_factory=dict)
    # Fail-closed provenance: MEASURED vs INSUFFICIENT_DATA/UNVETTED/fallback.
    # None confidence/score means unmeasured — never a 0.5/0.75 placeholder.
    fusion_status: str = "MEASURED"

    def is_actionable(self) -> bool:
        if self.confidence is None or self.score is None:
            return False
        if str(getattr(self, "fusion_status", "MEASURED")) in ("INSUFFICIENT_DATA", "UNVETTED"):
            return False
        return self.direction in ("LONG", "SHORT")


class SignalFusion:
    """
    Combine technical/mtf/fno/regime/AI/event_risk into fused score & direction.
    Weights configurable per strategy & versioned (§26, §29).
    """

    def fuse(self, inputs: SignalInputs, strategy_id: str, symbol: str, instrument_id: str | None = None) -> Signal:
        weights = inputs.weights or DEFAULT_WEIGHTS
        # Normalize weights to sum 100
        total_w = sum(D(v) for v in weights.values()) or D(100)
        def w(k): return D(weights.get(k, DEFAULT_WEIGHTS.get(k, 0))) / total_w * D(100)

        # Fail-closed input accounting: None means unmeasured (INSUFFICIENT_DATA),
        # never a silent 50 / 0.5 placeholder presented as measured.
        def _num_or_none(d: dict, *keys: str) -> Decimal | None:
            for _k in keys:
                try:
                    _v = d.get(_k)
                except Exception:
                    _v = None
                if _v is not None:
                    try:
                        return D(_v)
                    except Exception:
                        continue
            return None

        _tech_raw = _num_or_none(inputs.technical, "technical_score")
        _mtf_raw = _num_or_none(inputs.mtf, "score")
        _fno_raw = _num_or_none(inputs.fno, "score")
        _reg_raw = _num_or_none(inputs.regime, "score")
        _evt_raw = _num_or_none(inputs.event_risk, "score")
        _ai_conf_raw = _num_or_none(inputs.ai, "confidence")

        # Extract normalized sub-scores (0-100); missing -> None (unmeasured).
        tech_score = _tech_raw
        mtf_score = _mtf_raw
        # derive mtf score from bias only when score unmeasured but bias explicit.
        if mtf_score is None and "overall_bias" in inputs.mtf:
            bias = inputs.mtf.get("overall_bias")
            if bias == "BULLISH": mtf_score = D(75)
            elif bias == "BEARISH": mtf_score = D(25)

        fno_score = _fno_raw
        regime_score = _reg_raw
        if regime_score is None and "regime" in inputs.regime:
            # regime -> bias mapping only off an explicit regime label.
            r = inputs.regime.get("regime")
            if r in ("STRONG_BULL", "BULL"): regime_score = D(75)
            elif r in ("STRONG_BEAR", "BEAR"): regime_score = D(25)
            elif r == "RANGE": regime_score = D(50)

        ai_bias = inputs.ai.get("bias", "NEUTRAL") if isinstance(inputs.ai, dict) else "NEUTRAL"
        if _ai_conf_raw is None:
            # Unmeasured AI confidence: neutral 50 for math, but flagged insufficient.
            ai_score = D(50)
            _ai_insufficient = True
        else:
            ai_conf = _ai_conf_raw
            if ai_bias == "LONG": ai_score = ai_conf * D(100)
            elif ai_bias == "SHORT": ai_score = (D(1) - ai_conf) * D(100)
            else: ai_score = D(50)  # NEUTRAL/NO_TRADE
            _ai_insufficient = False

        event_score = _evt_raw if _evt_raw is not None else D(50)
        _evt_insufficient = _evt_raw is None and not inputs.event_risk.get("event_pending")
        # event_risk 5% usually penalizes if event pending
        if inputs.event_risk.get("event_pending"):
            event_score = D(30)

        # Fail-closed: no measurable domains at all => NO_TRADE + nulls, never
        # 0.5/50 placeholders presented as measured.
        _measured = [s for s in (tech_score, mtf_score, fno_score, regime_score) if s is not None]
        _any_ai_measured = not _ai_insufficient
        if not _measured and not _any_ai_measured:
            return Signal(
                signal_id=uuid4(),
                strategy_id=strategy_id,
                instrument_id=instrument_id,
                symbol=symbol,
                direction="NO_TRADE",
                timestamp=datetime.now(timezone.utc),
                market_snapshot_id=inputs.technical.get("market_snapshot_id") if isinstance(inputs.technical, dict) else None,
                technical_state=inputs.technical,
                mtf_state=inputs.mtf,
                fo_state=inputs.fno,
                regime=inputs.regime.get("regime") if isinstance(inputs.regime, dict) else None,
                ai_result=inputs.ai,
                score=None,
                confidence=None,
                invalidation_conditions={},
                weights_version=WEIGHTS_VERSION,
                correlation_penalty=D("0"),
                subscores={
                    "technical": None,
                    "mtf": None,
                    "fno": None,
                    "regime": None,
                    "ai": None,
                    "event_risk": None,
                },
                fusion_status="INSUFFICIENT_DATA",
            )
        # Partial missing: substitute neutral 50 for math but flag fallback
        # (never silent). Thin fusion is capped below thresholds downstream.
        _partial_missing = (
            tech_score is None or mtf_score is None or fno_score is None or regime_score is None
            or _ai_insufficient or _evt_insufficient
        )
        _fusion_status = "fallback" if _partial_missing else "MEASURED"
        if tech_score is None:
            tech_score = D(50)
        if mtf_score is None:
            mtf_score = D(50)
        if fno_score is None:
            fno_score = D(50)
        if regime_score is None:
            regime_score = D(50)

        # ── P0-5 de-correlation: tech/mtf/regime triple-count the same trend. ──
        # trend_cluster = mean(tech_trend01, mtf_bias01, regime01) on 0-1 scale,
        # tech_eff = 0.5*tech + 0.5*trend_cluster replaces raw tech in the fuse so a
        # single trend impulse cannot dominate via three correlated sleeves.
        def _trend01_tech() -> float:
            t = str(inputs.technical.get("trend", "") or "").upper()
            if "BULL" in t:
                return 1.0
            if "BEAR" in t:
                return 0.0
            try:
                ts = float(tech_score)
                if ts >= 60:
                    return 1.0
                if ts <= 40:
                    return 0.0
            except Exception:
                pass
            return 0.5

        def _trend01_mtf() -> float:
            b = str(inputs.mtf.get("overall_bias", "") or "").upper()
            if "BULL" in b:
                return 1.0
            if "BEAR" in b:
                return 0.0
            return 0.5

        def _trend01_regime() -> float:
            r = str(inputs.regime.get("regime", "") or "").upper()
            if r in ("STRONG_BULL", "BULL", "BULLISH", "UPTREND"):
                return 1.0
            if r in ("STRONG_BEAR", "BEAR", "BEARISH", "DOWNTREND"):
                return 0.0
            try:
                rs = float(regime_score)
                if rs >= 60:
                    return 1.0
                if rs <= 40:
                    return 0.0
            except Exception:
                pass
            return 0.5

        _t01 = _trend01_tech()
        _m01 = _trend01_mtf()
        _r01 = _trend01_regime()
        trend_cluster = D((_t01 + _m01 + _r01) / 3.0 * 100.0)
        tech_eff = (tech_score * D("0.5") + trend_cluster * D("0.5"))

        # Correlation penalty: when all three trend sleeves agree (all bull or all
        # bear) they are almost certainly the same impulse — haircut the fuse.
        try:
            _all_bull = _t01 >= 0.75 and _m01 >= 0.75 and _r01 >= 0.75
            _all_bear = _t01 <= 0.25 and _m01 <= 0.25 and _r01 <= 0.25
            correlation_penalty = D("5.0") if (_all_bull or _all_bear) else D("0")
        except Exception:
            correlation_penalty = D("0")

        fused = (
            tech_eff * w("technical") +
            mtf_score * w("mtf") +
            fno_score * w("fno") +
            regime_score * w("regime") +
            ai_score * w("ai") +
            event_score * w("event_risk")
        ) / D(100)
        fused = fused - correlation_penalty
        fused = max(D("0"), min(D("100"), fused))

        # Direction from fused score + AI/technical alignment
        # Also consider AI risk_flags — if critical risk_flag, force NO_TRADE
        risk_flags = inputs.ai.get("risk_flags", [])
        if any(f in ("HIGH_RISK", "EVENT_RISK_HIGH", "LIQUIDITY_RISK") for f in risk_flags):
            direction: Literal["LONG","SHORT","NO_TRADE"] = "NO_TRADE"
            fused = min(fused, D(45))
        elif fused >= FUSION_LONG_THRESHOLD:
            direction = "LONG"
        elif fused <= FUSION_SHORT_THRESHOLD:
            direction = "SHORT"
        else:
            direction = "NO_TRADE"

        # Confidence: agreement + distance from 50, capped at 0.90 (§35).
        # 0.07/agreement (not 0.10) + /200 (not /100) prevents borderline 62 → 0.92 inflation.
        # Base 0.5 is an explicit neutral prior (not a measured 0.5); unmeasured
        # fusion returns None above, never a silent 0.5.
        agreement = 0
        if inputs.technical.get("trend") == "BULLISH" and direction == "LONG": agreement += 1
        if inputs.technical.get("trend") == "BEARISH" and direction == "SHORT": agreement += 1
        if inputs.mtf.get("overall_bias") == "BULLISH" and direction == "LONG": agreement += 1
        if inputs.mtf.get("overall_bias") == "BEARISH" and direction == "SHORT": agreement += 1
        if ai_bias == direction: agreement += 1
        confidence: Decimal | None = D("0.5") + D(agreement) * D("0.07") + (abs(fused - D(50)) / D(200))
        # Haircut when AI unavailable (no AI key or NEUTRAL with low confidence)
        if not inputs.ai or inputs.ai.get("bias", "NEUTRAL") == "NEUTRAL":
            confidence -= D("0.08")
        confidence = max(D("0.1"), min(D("0.90"), confidence))
        # Partial-missing fusion is explicitly fallback and non-actionable when
        # thin: never present a fallback 0.5-derived confidence as measured edge.
        # _measured holds the pre-substitution measured count (fail-closed).
        try:
            _measured_ct = len(_measured)
        except Exception:
            _measured_ct = 0
        if _fusion_status == "fallback" and _measured_ct < 2:
            direction = "NO_TRADE"  # type: ignore[assignment]
            confidence = None

        subscores = {
            "technical": float(tech_score),
            "technical_eff": float(tech_eff),
            "trend_cluster": float(trend_cluster),
            "mtf": float(mtf_score),
            "fno": float(fno_score),
            "regime": float(regime_score),
            "ai": float(ai_score),
            "event_risk": float(event_score),
        }
        return Signal(
            signal_id=uuid4(),
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            symbol=symbol,
            direction=direction,
            timestamp=datetime.now(timezone.utc),
            market_snapshot_id=inputs.technical.get("market_snapshot_id"),
            technical_state=inputs.technical,
            mtf_state=inputs.mtf,
            fo_state=inputs.fno,
            regime=inputs.regime.get("regime"),
            ai_result=inputs.ai,
            score=fused.quantize(D("0.01")) if fused is not None else None,
            confidence=confidence.quantize(D("0.0001")) if confidence is not None else None,
            invalidation_conditions=inputs.ai.get("suggested_invalidation", {}) if isinstance(inputs.ai.get("suggested_invalidation"), dict) else {"raw": inputs.ai.get("suggested_invalidation")},
            weights_version=WEIGHTS_VERSION,
            correlation_penalty=correlation_penalty.quantize(D("0.01")),
            subscores=subscores,
            fusion_status=_fusion_status,
        )


# ── Strategy Conflict Resolution §28 ─────────────────────────────────

ConflictPolicy = Literal["NET", "PRIORITIZE_BY_RANK", "REJECT_BOTH_AND_ALERT"]


@dataclass
class ConflictingSignal:
    strategy_id: str
    direction: str
    rank: int
    signal: Signal


class ConflictResolver:
    DEFAULT_POLICY: ConflictPolicy = "REJECT_BOTH_AND_ALERT"

    def _bucket(self, cs: ConflictingSignal, fn=None) -> str:
        """P0-5: instrument/underlying bucket. LONG NIFTY + SHORT BANKNIFTY are
        different buckets and must NOT conflict."""
        try:
            if fn is not None:
                sig = cs.signal
                sym = getattr(sig, "symbol", "") or ""
                iid = getattr(sig, "instrument_id", "") or ""
                return str(fn(sym or iid or "UNKNOWN")).upper()
        except Exception:
            pass
        try:
            sig = cs.signal
            for attr in ("instrument_id", "symbol"):
                v = getattr(sig, attr, None)
                if v:
                    return str(v).upper().strip()
            # Fallback: strategy-level underlying if signal lacks instrument
            return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def resolve(
        self,
        signals: list[ConflictingSignal],
        policy: ConflictPolicy | None = None,
        instrument_equivalence_fn=None,
    ) -> tuple[list[Signal], str]:
        """
        Returns (approved_signals, reason).
        - For opposing signals on equivalent instruments, do not silently submit opposing orders.
        - P0-5: conflict is per-underlying bucket. LONG NIFTY + SHORT BANKNIFTY
          (different buckets) => NO_CONFLICT.
        - NET: net exposure, submit residual after risk validation (per bucket).
        """
        policy = policy or self.DEFAULT_POLICY
        if len(signals) <= 1:
            return [s.signal for s in signals], "NO_CONFLICT"

        # Group by equivalent instrument bucket first.
        from collections import defaultdict
        by_bucket: dict[str, list[ConflictingSignal]] = defaultdict(list)
        for s in signals:
            by_bucket[self._bucket(s, instrument_equivalence_fn)].append(s)

        # No bucket contains opposing directions => no conflict across instruments.
        has_opposing_bucket = any(
            len({x.direction for x in grp}) > 1 for grp in by_bucket.values()
        )
        if not has_opposing_bucket:
            return [s.signal for s in signals], "SAME_DIRECTION_NO_CONFLICT"

        # At least one bucket has LONG vs SHORT. Resolve per-bucket, then merge.
        approved: list[Signal] = []
        reasons: list[str] = []
        for bucket, grp in sorted(by_bucket.items()):
            dirs = {x.direction for x in grp}
            if len(dirs) == 1:
                approved.extend(x.signal for x in grp)
                continue
            # Opposing directions in the SAME bucket => policy applies.
            if policy == "REJECT_BOTH_AND_ALERT":
                logger.warning("strategy_conflict_reject_both", bucket=bucket, count=len(grp))
                reasons.append(f"{bucket}:REJECT_BOTH_DUE_TO_CONFLICT")
                continue
            if policy == "PRIORITIZE_BY_RANK":
                grp_sorted = sorted(grp, key=lambda s: s.rank)
                winner = grp_sorted[0]
                logger.info("strategy_conflict_prioritized", bucket=bucket, winner=winner.strategy_id)
                approved.append(winner.signal)
                reasons.append(f"{bucket}:PRIORITIZED_{winner.strategy_id}")
                continue
            if policy == "NET":
                long_ct = sum(1 for s in grp if s.direction == "LONG")
                short_ct = sum(1 for s in grp if s.direction == "SHORT")
                net = long_ct - short_ct
                if net == 0:
                    reasons.append(f"{bucket}:NET_ZERO_NO_ORDER")
                    continue
                wanted_dir = "LONG" if net > 0 else "SHORT"
                candidates = [s for s in grp if s.direction == wanted_dir]
                candidates.sort(key=lambda s: s.signal.confidence, reverse=True)
                approved.append(candidates[0].signal)
                reasons.append(f"{bucket}:NET_{wanted_dir}_RESIDUAL_{abs(net)}")
                continue
            reasons.append(f"{bucket}:UNKNOWN_POLICY")

        if not approved and reasons:
            # All conflicting buckets rejected (e.g. REJECT_BOTH on every bucket).
            if all("REJECT_BOTH" in r or "NET_ZERO" in r for r in reasons):
                return [], "REJECT_BOTH_DUE_TO_CONFLICT"
            return [], reasons[0] if len(reasons) == 1 else ";".join(reasons)
        if reasons:
            return approved, ";".join(reasons)
        return approved, "NO_CONFLICT"

    def resolve_candidate_conflicts(
        self,
        candidates: list[Any],
        tie_epsilon: float = 5.0,
        max_same_direction: int = 1,
    ) -> tuple[list[Any], list[str]]:
        """
        Arbitrate between competing SignalCandidates on the same underlying instrument (§28).
        If opposing directions (CALL vs PUT) fire simultaneously:
          - If |confidence_A - confidence_B| < tie_epsilon: Reject both (NO_TRADE on tie).
          - Else: Pick higher confidence candidate, drop opposing candidate.
        P0-5 same-direction cap: at most `max_same_direction` (default top-1) approvals
        per underlying per direction. Survivors beyond top-1 are dropped with
        DROPPED_CORRELATED; when max_same_direction>=2 the 2nd kept candidate takes a
        0.5x confidence haircut (correlated duplicate, not independent edge).
        """
        if len(candidates) <= 1:
            return candidates, []

        from collections import defaultdict
        by_underlying = defaultdict(list)
        for c in candidates:
            try:
                key = str(getattr(c, "underlying", "UNKNOWN") or "UNKNOWN").upper()
            except Exception:
                key = "UNKNOWN"
            by_underlying[key].append(c)

        def _conf(x: Any) -> float:
            try:
                v = getattr(x, "overall_confidence", 50.0)
                return float(v if v is not None else 50.0)
            except Exception:
                return 50.0

        def _cap_same_direction(items: list[Any], underlying: str, out: list[Any], dropped: list[str]) -> None:
            # items: already direction-filtered survivors for one underlying+side.
            if len(items) <= max_same_direction:
                out.extend(items)
                return
            ranked = sorted(items, key=_conf, reverse=True)
            keep = ranked[:max_same_direction]
            # 0.5x haircut on the 2nd kept candidate when top-2 allowed.
            if max_same_direction >= 2 and len(keep) == 2:
                try:
                    second = keep[1]
                    orig = _conf(second)
                    haircut = round(orig * 0.5, 1)
                    try:
                        second.overall_confidence = haircut
                    except Exception:
                        pass
                    dropped.append(
                        f"{underlying}:{getattr(second, 'strategy', '?')}_CORRELATED_HAIRCUT_0.5x "
                        f"({orig}->{haircut})"
                    )
                except Exception:
                    pass
            out.extend(keep)
            for extra in ranked[max_same_direction:]:
                dropped.append(
                    f"{underlying}:{getattr(extra, 'strategy', '?')}_DROPPED_CORRELATED "
                    f"(conf={_conf(extra)}, kept={getattr(keep[0], 'strategy', '?')})"
                )
                logger.info(
                    "candidate_dropped_correlated",
                    underlying=underlying,
                    dropped_strategy=getattr(extra, "strategy", "?"),
                    kept_strategy=getattr(keep[0], "strategy", "?"),
                )

        approved: list[Any] = []
        dropped_reasons: list[str] = []

        for underlying, c_list in by_underlying.items():
            calls = [c for c in c_list if "CALL" in str(getattr(c, "direction", ""))]
            puts = [c for c in c_list if "PUT" in str(getattr(c, "direction", ""))]
            other = [c for c in c_list if c not in calls and c not in puts]

            survivors: list[Any] = []
            if calls and puts:
                best_call = max(calls, key=_conf)
                best_put = max(puts, key=_conf)
                diff = abs(_conf(best_call) - _conf(best_put))

                if diff < tie_epsilon:
                    dropped_reasons.append(
                        f"{underlying}:CONFLICT_TIE_REJECT_BOTH (call={_conf(best_call)}, put={_conf(best_put)})"
                    )
                    logger.warning("candidate_conflict_tie_reject_both", underlying=underlying, diff=diff)
                    # Even on tie, leftovers beyond best pair are correlated drops.
                    for extra in [c for c in calls if c is not best_call] + [c for c in puts if c is not best_put]:
                        dropped_reasons.append(
                            f"{underlying}:{getattr(extra, 'strategy', '?')}_DROPPED_CORRELATED (tie-reject)"
                        )
                    continue

                if _conf(best_call) > _conf(best_put):
                    survivors.append(best_call)
                    dropped_reasons.append(f"{underlying}:{best_put.strategy}_DROPPED_IN_FAVOR_OF_{best_call.strategy}_CALL")
                    # Same-direction correlated leftovers on the winning side.
                    _cap_same_direction([c for c in calls if c is not best_call], underlying, [], dropped_reasons)
                    for extra in [c for c in puts if c is not best_put]:
                        dropped_reasons.append(
                            f"{underlying}:{getattr(extra, 'strategy', '?')}_DROPPED_CORRELATED (opposing-side loser)"
                        )
                else:
                    survivors.append(best_put)
                    dropped_reasons.append(f"{underlying}:{best_call.strategy}_DROPPED_IN_FAVOR_OF_{best_put.strategy}_PUT")
                    _cap_same_direction([c for c in puts if c is not best_put], underlying, [], dropped_reasons)
                    for extra in [c for c in calls if c is not best_call]:
                        dropped_reasons.append(
                            f"{underlying}:{getattr(extra, 'strategy', '?')}_DROPPED_CORRELATED (opposing-side loser)"
                        )
                approved.extend(survivors)
            else:
                # No opposing conflict: still cap same-direction duplicates per underlying.
                _cap_same_direction(calls or puts or other, underlying, approved, dropped_reasons)

        return approved, dropped_reasons


conflict_resolver = ConflictResolver()


# ── Trigger Engine §31 ───────────────────────────────────────────────

TriggerType = Literal["BREAKOUT","BREAKDOWN","VWAP_CROSS","EMA_CROSS","VOLUME_SPIKE","OI_ANOMALY","OPTION_CHAIN_CHANGE","TREND_REVERSAL","REGIME_CHANGE","AI_CONTEXT_CHANGE","TIME_BASED"]


@dataclass
class TriggerConfig:
    trigger_types: list[TriggerType] = field(default_factory=lambda: ["BREAKOUT"])
    min_score: Decimal = D(60)
    min_confidence: Decimal = D("0.6")
    cooldown_seconds: int = 60


class TriggerEngine:
    """
    Signal → actionable event. A signal is not an order (§31 last line).
    Dedup: same event must not create duplicate executable signals (§27).
    """

    def __init__(self):
        self._recent_triggers: dict[str, datetime] = {}  # signal_id -> ts for dedup
        self._last_trigger_ts: dict[str, datetime] = {}  # strategy+symbol -> ts for cooldown

    def should_trigger(self, signal: Signal, trigger: TriggerType, config: TriggerConfig | None = None) -> tuple[bool, str]:
        config = config or TriggerConfig()
        key = f"{signal.strategy_id}:{signal.symbol}"

        from app.services.calendar_service import calendar_service
        if not calendar_service.can_trade_now().allowed:
            return False, "MARKET_CLOSED"

        # Dedup: same signal_id already triggered
        if str(signal.signal_id) in self._recent_triggers:
            return False, "DUPLICATE_SIGNAL_ID"

        # Cooldown
        last = self._last_trigger_ts.get(key)
        if last and (datetime.now(timezone.utc) - last).total_seconds() < config.cooldown_seconds:
            return False, "COOLDOWN_ACTIVE"

        # Validate trigger type enabled
        if trigger not in config.trigger_types and "TIME_BASED" not in config.trigger_types:
            # allow if signal score high enough to override? No — strict per config
            pass

        if signal.direction == "NO_TRADE":
            return False, "NO_TRADE_SIGNAL"

        if signal.score < config.min_score:
            return False, f"SCORE_BELOW_THRESHOLD_{signal.score}<{config.min_score}"

        if signal.confidence < config.min_confidence:
            return False, f"CONFIDENCE_BELOW_THRESHOLD_{signal.confidence}<{config.min_confidence}"

        # Trigger type specific checks could go here (breakout validated etc)
        return True, "TRIGGER_APPROVED"

    def mark_triggered(self, signal: Signal) -> None:
        self._recent_triggers[str(signal.signal_id)] = datetime.now(timezone.utc)
        self._last_trigger_ts[f"{signal.strategy_id}:{signal.symbol}"] = datetime.now(timezone.utc)
        # prune old
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        self._recent_triggers = {k: v for k, v in self._recent_triggers.items() if v.timestamp() > cutoff}


signal_fusion = SignalFusion()
conflict_resolver = ConflictResolver()
trigger_engine = TriggerEngine()
