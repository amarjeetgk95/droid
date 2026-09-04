"""
Institutional Fast Scalping Confirmation Engine (Version 6.0)

Enforces 6 Deterministic Pre-Execution Gates before any Scalp is ARMED/CONFIRMED:
  1. Event-Driven 1M Candle Close & Stale Data Guard (Clock skew tolerance: 250ms, max candle age: 120s)
  2. Fingerprint Deduplication (Instrument | Strategy | Direction | CandleTimestamp)
  3. Minimum Inter-Signal Cooldown per Instrument/Strategy
  4. Anti-Chase Ceiling (0.50R normal, tightened to 0.35R in High Vol / Event)
  5. Regime Compatibility Matrix (§15)
  6. Liquidity & Bid-Ask Spread Validation (Spread <= 2.0 pts or <= 2.0% of premium, minimum volume)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field
import structlog

from app.signals.strategies.base import SignalCandidate, TradeDirection

logger = structlog.get_logger()

# Scalp strategies covered by confirmation engine
SCALP_STRATEGY_SET = {"VWAP_SCALP", "MICRO_MOMENTUM", "EMA_RIBBON", "GAMMA_SPIKE"}


class ScalpConfirmationResult(BaseModel):
    passed: bool
    candidate: Optional[SignalCandidate] = None
    reason_code: Optional[str] = None  # None if passed, else REJECTED_*
    rejection_message: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class ScalpConfirmationEngine:
    """
    Deterministic gatekeeper for High-Frequency Scalping setups.
    Rejects setups that violate anti-chase, regime compatibility, cooldowns, or liquidity guards.
    """

    def __init__(
        self,
        skew_tolerance_ms: int = 250,
        max_candle_age_ms: int = 120_000,
        default_cooldown_seconds: int = 60,
        max_spread_pts: Decimal = Decimal("2.50"),
        max_spread_pct: Decimal = Decimal("0.025"),
        min_option_volume: int = 250,
    ):
        self.skew_tolerance_ms = skew_tolerance_ms
        self.max_candle_age_ms = max_candle_age_ms
        self.default_cooldown_seconds = default_cooldown_seconds
        self.max_spread_pts = max_spread_pts
        self.max_spread_pct = max_spread_pct
        self.min_option_volume = min_option_volume

        # Deduplication cache: fingerprint -> confirmed_timestamp_ms
        self._confirmed_fingerprints: dict[str, int] = {}
        # Cooldown tracker: f"{underlying}|{strategy}" -> last_confirmed_timestamp_ms
        self._last_signal_time: dict[str, int] = {}

    def compute_fingerprint(
        self,
        underlying: str,
        strategy: str,
        direction: str,
        candle_timestamp_ms: int,
    ) -> str:
        """Deterministic fingerprint: Instrument|Strategy|Direction|CandleTimestamp."""
        return f"{underlying.upper()}|{strategy.upper()}|{direction.upper()}|{candle_timestamp_ms}"

    def is_afternoon_gamma_window(self, now_utc: Optional[datetime] = None) -> bool:
        """Check if current time is within expiry afternoon gamma window: 13:15 - 15:15 IST (07:45 - 09:45 UTC)."""
        dt = now_utc or datetime.now(timezone.utc)
        minute_of_day_utc = dt.hour * 60 + dt.minute
        # 07:45 UTC = 465 min, 15:15 IST = 09:45 UTC = 585 min
        return 465 <= minute_of_day_utc <= 585

    def check_regime_compatibility(
        self,
        strategy: str,
        direction: TradeDirection,
        regime: str,
        now_utc: Optional[datetime] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Validates strategy against Market Regime Matrix (§15).
        Returns (is_compatible, reason_if_incompatible).
        """
        r = regime.upper().strip()

        # Normalize common regime aliases
        is_bull = r in ("TRENDING_BULLISH", "TREND_UP", "BULLISH")
        is_bear = r in ("TRENDING_BEARISH", "TREND_DOWN", "BEARISH")
        is_compression = r in ("COMPRESSION_SQUEEZE", "RANGEBOUND_LOW_VOL", "RANGE", "LOW_VOL")
        is_expansion = r in ("VOLATILE_EXPANSION", "RANGEBOUND_HIGH_VOL", "HIGH_VOL", "BREAKOUT")
        is_event = "EVENT" in r

        if strategy == "VWAP_SCALP":
            if is_event or is_expansion:
                return False, f"VWAP_SCALP incompatible with volatile expansion/event regime ({regime})"
            if is_bull and direction != "LONG_CALL":
                return False, f"VWAP_SCALP counter-trend PUT rejected in bullish regime ({regime})"
            if is_bear and direction != "LONG_PUT":
                return False, f"VWAP_SCALP counter-trend CALL rejected in bearish regime ({regime})"
            return True, None

        elif strategy == "MICRO_MOMENTUM":
            if is_compression:
                return False, f"MICRO_MOMENTUM incompatible with compression/low vol regime ({regime})"
            if is_bull and direction != "LONG_CALL":
                return False, f"MICRO_MOMENTUM PUT rejected in bullish regime ({regime})"
            if is_bear and direction != "LONG_PUT":
                return False, f"MICRO_MOMENTUM CALL rejected in bearish regime ({regime})"
            return True, None

        elif strategy == "EMA_RIBBON":
            if not (is_bull or is_bear):
                return False, f"EMA_RIBBON requires strong trending regime, got ({regime})"
            if is_bull and direction != "LONG_CALL":
                return False, f"EMA_RIBBON PUT rejected in bullish regime ({regime})"
            if is_bear and direction != "LONG_PUT":
                return False, f"EMA_RIBBON CALL rejected in bearish regime ({regime})"
            return True, None

        elif strategy == "GAMMA_SPIKE":
            in_gamma_window = self.is_afternoon_gamma_window(now_utc)
            if in_gamma_window or is_expansion or is_event:
                return True, None
            if is_compression:
                return False, f"GAMMA_SPIKE requires volatile expansion or afternoon expiry window (regime: {regime})"
            return True, None

        # Intraday or unhandled strategies pass through
        return True, None

    def validate(
        self,
        candidate: SignalCandidate,
        current_spot: Decimal,
        regime: str,
        candle_timestamp_ms: Optional[int] = None,
        now_ms: Optional[int] = None,
        option_bid: Optional[Decimal] = None,
        option_ask: Optional[Decimal] = None,
        option_volume: Optional[int] = None,
    ) -> ScalpConfirmationResult:
        """
        Executes all 6 validation gates on a candidate.
        """
        ts_now = now_ms or int(time.time() * 1000)
        c_ts = candle_timestamp_ms or candidate.created_at_utc

        # 1. Clock Skew & Stale Candle Guard
        age_ms = ts_now - c_ts
        if age_ms < -self.skew_tolerance_ms:
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_CLOCK_SKEW",
                rejection_message=f"Candle timestamp is {abs(age_ms)}ms in the future (skew limit: {self.skew_tolerance_ms}ms)",
                metrics={"age_ms": age_ms, "skew_limit": self.skew_tolerance_ms},
            )
        if age_ms > self.max_candle_age_ms:
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_STALE_DATA",
                rejection_message=f"Candle close is stale ({age_ms}ms > {self.max_candle_age_ms}ms)",
                metrics={"age_ms": age_ms, "max_age_ms": self.max_candle_age_ms},
            )

        # 2. Fingerprint Deduplication
        fp = self.compute_fingerprint(candidate.underlying, candidate.strategy, candidate.direction, c_ts)
        if fp in self._confirmed_fingerprints:
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_DEDUPLICATION",
                rejection_message=f"Signal with fingerprint {fp} already processed",
                metrics={"fingerprint": fp},
            )

        # 3. Inter-Signal Cooldown
        cd_key = f"{candidate.underlying.upper()}|{candidate.strategy.upper()}"
        last_ts = self._last_signal_time.get(cd_key, 0)
        elapsed_sec = (ts_now - last_ts) / 1000.0
        cooldown_sec = self.default_cooldown_seconds
        if elapsed_sec < cooldown_sec:
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_COOLDOWN",
                rejection_message=f"Strategy {cd_key} in cooldown ({elapsed_sec:.1f}s < {cooldown_sec}s)",
                metrics={"elapsed_seconds": elapsed_sec, "cooldown_seconds": cooldown_sec},
            )

        # 4. Anti-Chase Ceiling (§16)
        if candidate.direction == "LONG_CALL":
            chase_pts = max(Decimal("0"), current_spot - candidate.trigger)
        else:
            chase_pts = max(Decimal("0"), candidate.trigger - current_spot)

        # Fraction allowed: 0.35 in volatile regimes, otherwise candidate.max_chase_fraction (0.50)
        r_upper = regime.upper()
        is_high_vol = any(k in r_upper for k in ("HIGH_VOL", "VOLATILE", "EVENT"))
        allowed_fraction = 0.35 if is_high_vol else (candidate.max_chase_fraction or 0.50)
        max_allowed_chase_pts = candidate.risk_points * Decimal(str(allowed_fraction))

        if chase_pts > max_allowed_chase_pts:
            chase_fraction = float(chase_pts / candidate.risk_points) if candidate.risk_points > 0 else 999.0
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_CHASE",
                rejection_message=f"Chased {chase_pts} pts ({chase_fraction:.2f}R > {allowed_fraction}R ceiling)",
                metrics={
                    "chase_points": float(chase_pts),
                    "chase_fraction_r": chase_fraction,
                    "max_allowed_r": allowed_fraction,
                    "spot_price": float(current_spot),
                    "trigger_price": float(candidate.trigger),
                },
            )

        # 5. Regime Compatibility Matrix (§15)
        regime_ok, regime_reason = self.check_regime_compatibility(
            candidate.strategy, candidate.direction, regime
        )
        if not regime_ok:
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_REGIME",
                rejection_message=regime_reason or f"Incompatible regime: {regime}",
                metrics={"regime": regime, "strategy": candidate.strategy},
            )

        # 6. Liquidity & Spread Validation
        if option_bid is not None and option_ask is not None:
            spread = option_ask - option_bid
            if spread > self.max_spread_pts:
                # Also check pct
                spread_pct = (spread / option_ask) if option_ask > 0 else Decimal("1.0")
                if spread_pct > self.max_spread_pct:
                    return ScalpConfirmationResult(
                        passed=False,
                        candidate=candidate,
                        reason_code="REJECTED_SPREAD",
                        rejection_message=f"Option spread too wide: {spread} pts ({spread_pct * 100:.2f}%)",
                        metrics={"spread": float(spread), "spread_pct": float(spread_pct)},
                    )

        if option_volume is not None and option_volume < self.min_option_volume:
            return ScalpConfirmationResult(
                passed=False,
                candidate=candidate,
                reason_code="REJECTED_LIQUIDITY",
                rejection_message=f"Option volume too low ({option_volume} < {self.min_option_volume})",
                metrics={"volume": option_volume, "min_volume": self.min_option_volume},
            )

        # All 6 Gates Passed!
        return ScalpConfirmationResult(
            passed=True,
            candidate=candidate,
            reason_code=None,
            rejection_message=None,
            metrics={
                "chase_points": float(chase_pts),
                "allowed_chase_fraction": allowed_fraction,
                "regime": regime,
                "fingerprint": fp,
            },
        )

    def record_confirmed(
        self,
        candidate: SignalCandidate,
        candle_timestamp_ms: Optional[int] = None,
        now_ms: Optional[int] = None,
    ) -> None:
        """Mark fingerprint as active and update cooldown timestamp."""
        ts_now = now_ms or int(time.time() * 1000)
        c_ts = candle_timestamp_ms or candidate.created_at_utc

        fp = self.compute_fingerprint(candidate.underlying, candidate.strategy, candidate.direction, c_ts)
        self._confirmed_fingerprints[fp] = ts_now

        cd_key = f"{candidate.underlying.upper()}|{candidate.strategy.upper()}"
        self._last_signal_time[cd_key] = ts_now

        # Purge old fingerprints older than 10 minutes (600,000 ms)
        cutoff = ts_now - 600_000
        self._confirmed_fingerprints = {
            k: v for k, v in self._confirmed_fingerprints.items() if v > cutoff
        }

    def reset(self) -> None:
        """Reset internal caches (for tests and session initialization)."""
        self._confirmed_fingerprints.clear()
        self._last_signal_time.clear()


scalp_confirmation_engine = ScalpConfirmationEngine()
