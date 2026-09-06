"""
Crypto Scalp Scanner — Core Engine
Fetches Binance market data, constructs analysis context, evaluates all 5 strategies,
filters through risk engine, persists to Supabase, and dispatches Telegram notifications.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
import structlog

from app.core.config import settings
from app.crypto_scalp.base import (
    CryptoScalpContext,
    calc_ema,
    calc_atr,
    calc_vwap,
)
from app.crypto_scalp.strategies import CRYPTO_SCALP_STRATEGIES
from app.crypto_scalp.risk_filter import crypto_scalp_risk_filter
from app.crypto_scalp.persistence import persist_scalp_signal, fetch_persisted_scalp_signals
from app.crypto_scalp.telegram import dispatch_crypto_scalp_telegram
from app.models.crypto import (
    CryptoScalpSignal,
    CryptoScalpSignalsResponse,
    CryptoScalpDiagnostics,
    CryptoSignalStatus,
)
from app.models.market import DataStatus
from app.services.binance_service import binance_service

logger = structlog.get_logger()

# Symbols to scan for scalping
DEFAULT_SCALP_SYMBOLS = ["BTCUSDT", "ETHUSDT"]


class CryptoScalpScanner:
    """Production 24/7 Scalp Scanner for Bitcoin and Ethereum."""

    def __init__(self):
        self._active_signals: dict[str, CryptoScalpSignal] = {}
        self._last_scan_time: datetime | None = None
        self._last_scan_duration_ms: float = 0.0
        self._last_diagnostics: CryptoScalpDiagnostics | None = None
        self._cache_ttl_seconds: float = 5.0
        self._last_cache_time: float = 0.0
        self._cached_response: CryptoScalpSignalsResponse | None = None
        self._lock = asyncio.Lock()
        self._total_persisted_count: int = 0

    async def build_context(self, symbol: str) -> CryptoScalpContext | None:
        """Fetch market data and build CryptoScalpContext for a symbol."""
        clean_sym = binance_service.validate_symbol(symbol)
        asset = "BTC" if "BTC" in clean_sym else "ETH"

        try:
            # Parallel fetch of candles (1m, 5m, 15m), order book, and derivatives
            candles_1m_task = binance_service.get_candles(clean_sym, "1m", limit=60)
            candles_5m_task = binance_service.get_candles(clean_sym, "5m", limit=30)
            candles_15m_task = binance_service.get_candles(clean_sym, "15m", limit=20)
            ob_task = binance_service.get_order_book(clean_sym, limit=20)
            derivs_task = binance_service.get_derivatives_data(clean_sym)

            results = await asyncio.gather(
                candles_1m_task,
                candles_5m_task,
                candles_15m_task,
                ob_task,
                derivs_task,
                return_exceptions=True,
            )

            candles_1m = results[0] if not isinstance(results[0], Exception) else []
            candles_5m = results[1] if not isinstance(results[1], Exception) else []
            candles_15m = results[2] if not isinstance(results[2], Exception) else []
            orderbook = results[3] if not isinstance(results[3], Exception) else None
            derivatives = results[4] if not isinstance(results[4], Exception) else None

            if not candles_1m or len(candles_1m) < 10:
                logger.warning("insufficient_1m_candles", symbol=clean_sym, count=len(candles_1m) if candles_1m else 0)
                return None

            current_price = candles_1m[-1].close

            # Indicator Calculations
            closes_1m = [c.close for c in candles_1m]
            ema_9 = calc_ema(closes_1m, 9)
            ema_21 = calc_ema(closes_1m, 21)
            ema_50 = calc_ema(closes_1m, 50)
            atr_14 = calc_atr(candles_1m, 14)
            vwap = calc_vwap(candles_1m)

            # Volume surge ratio (current bar vs previous 20 bars average)
            recent_vols = [c.volume for c in candles_1m[-21:-1]]
            avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else candles_1m[-1].volume
            current_vol = candles_1m[-1].volume
            vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            # 15m high & low anchors
            window_15m = candles_1m[-16:-1] if len(candles_1m) >= 16 else candles_1m[:-1]
            high_15m = max(c.high for c in window_15m) if window_15m else current_price
            low_15m = min(c.low for c in window_15m) if window_15m else current_price

            return CryptoScalpContext(
                symbol=clean_sym,
                asset=asset,
                current_price=current_price,
                candles_1m=candles_1m,
                candles_5m=candles_5m,
                candles_15m=candles_15m,
                vwap_session=vwap,
                ema_9_1m=ema_9,
                ema_21_1m=ema_21,
                ema_50_1m=ema_50,
                atr_14_1m=atr_14,
                volume_surge_ratio=vol_ratio,
                high_15m=high_15m,
                low_15m=low_15m,
                orderbook=orderbook,
                derivatives=derivatives,
            )
        except Exception as e:
            logger.warning("build_crypto_scalp_context_failed", symbol=symbol, error=str(e))
            return None

    async def scan_symbol(self, symbol: str) -> list[CryptoScalpSignal]:
        """Scan a single symbol across all 5 strategies and filter valid signals."""
        ctx = await self.build_context(symbol)
        if not ctx:
            return []

        detected_signals: list[CryptoScalpSignal] = []

        for strat_code, strategy in CRYPTO_SCALP_STRATEGIES.items():
            try:
                candidate = strategy.detect(ctx)
                if not candidate:
                    continue

                # Run candidate through Risk Filter
                is_valid, reason = crypto_scalp_risk_filter.validate(candidate)
                if not is_valid:
                    logger.debug("crypto_scalp_candidate_rejected", strategy=strat_code, reason=reason)
                    continue

                # Deterministic signal ID based on symbol, strategy, and time window (5-minute bucket)
                time_bucket = int(time.time() // 300)
                signal_id = f"SCALP-{ctx.symbol}-{strat_code}-{candidate.direction.value}-{time_bucket}"

                # Check if signal was already created in this bucket
                existing = self._active_signals.get(signal_id)
                if existing:
                    # Update current price
                    existing.current_price = ctx.current_price
                    detected_signals.append(existing)
                    continue

                # New signal discovered
                new_signal = CryptoScalpSignal(
                    id=signal_id,
                    symbol=candidate.symbol,
                    asset=candidate.asset,
                    direction=candidate.direction,
                    strategy=candidate.strategy,
                    strategy_name=candidate.strategy_name,
                    entry_price=candidate.entry_price,
                    stop_loss=candidate.stop_loss,
                    target_1=candidate.target_1,
                    target_2=candidate.target_2,
                    current_price=ctx.current_price,
                    risk_points=candidate.risk_points,
                    risk_percent=candidate.risk_percent,
                    risk_reward_ratio=candidate.risk_reward_ratio,
                    confidence=candidate.confidence,
                    timeframe=candidate.timeframe,
                    status=CryptoSignalStatus.ACTIVE,
                    confluence_factors=candidate.confluence_factors,
                    rationale=candidate.rationale,
                    atr_value=candidate.atr_value,
                    volume_ratio=candidate.volume_ratio,
                    funding_rate=candidate.funding_rate,
                    depth_imbalance=candidate.depth_imbalance,
                    is_scalp=True,
                    created_at_utc=int(time.time() * 1000),
                )

                # Persist to Supabase and local cache
                await persist_scalp_signal(new_signal)
                self._total_persisted_count += 1

                # Dispatch to Telegram if enabled
                if settings.crypto_scalp_telegram_enabled:
                    asyncio.create_task(dispatch_crypto_scalp_telegram(new_signal))

                self._active_signals[signal_id] = new_signal
                detected_signals.append(new_signal)
                logger.info(
                    "crypto_scalp_signal_generated",
                    signal_id=signal_id,
                    symbol=new_signal.symbol,
                    direction=new_signal.direction.value,
                    strategy=new_signal.strategy,
                    confidence=new_signal.confidence,
                )

            except Exception as e:
                logger.warning("crypto_scalp_strategy_error", strategy=strat_code, symbol=symbol, error=str(e))

        return detected_signals

    async def scan_all(self, force_refresh: bool = False) -> CryptoScalpSignalsResponse:
        """Scan all monitored symbols and return active signals with diagnostics."""
        now = time.time()
        if not force_refresh and self._cached_response and (now - self._last_cache_time) < self._cache_ttl_seconds:
            return self._cached_response

        async with self._lock:
            # Recheck after lock
            if not force_refresh and self._cached_response and (time.time() - self._last_cache_time) < self._cache_ttl_seconds:
                return self._cached_response

            start_t = time.perf_counter()
            all_signals: list[CryptoScalpSignal] = []
            errors: list[str] = []
            candle_counts: dict[str, int] = {}

            # Sweep expired active signals (older than 30 minutes)
            expire_threshold_ms = int((time.time() - 1800) * 1000)
            for sid, sig in list(self._active_signals.items()):
                if sig.created_at_utc < expire_threshold_ms:
                    self._active_signals.pop(sid, None)

            # Scan each default symbol
            for sym in DEFAULT_SCALP_SYMBOLS:
                try:
                    signals = await self.scan_symbol(sym)
                    all_signals.extend(signals)
                    candle_counts[sym] = 60
                except Exception as e:
                    errors.append(f"{sym}: {str(e)}")

            # If no active signals from current scan, load most recent from Supabase/cache
            if not all_signals:
                recent_persisted = await fetch_persisted_scalp_signals(limit=10)
                for s in recent_persisted:
                    if s.id not in self._active_signals:
                        self._active_signals[s.id] = s
                all_signals = list(self._active_signals.values())

            # Sort by created_at_utc descending, then confidence
            all_signals.sort(key=lambda s: (s.created_at_utc, s.confidence), reverse=True)

            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            self._last_scan_time = datetime.now(timezone.utc)
            self._last_scan_duration_ms = duration_ms

            btc_count = sum(1 for s in all_signals if "BTC" in s.symbol)
            eth_count = sum(1 for s in all_signals if "ETH" in s.symbol)

            from app.crypto_scalp.worker import crypto_scalp_worker

            diagnostics = CryptoScalpDiagnostics(
                data_quality=DataStatus.LIVE if not errors else DataStatus.DEGRADED,
                candles_count=candle_counts,
                strategies_evaluated=len(CRYPTO_SCALP_STRATEGIES),
                candidates_found=len(all_signals),
                duration_ms=duration_ms,
                last_scan_time=self._last_scan_time,
                worker_running=crypto_scalp_worker.is_running,
                scan_interval_seconds=settings.crypto_scalp_scan_interval_seconds,
                telegram_enabled=settings.crypto_scalp_telegram_enabled,
                supabase_persisted_count=self._total_persisted_count,
                errors=errors,
            )
            self._last_diagnostics = diagnostics

            resp = CryptoScalpSignalsResponse(
                signals=all_signals,
                total_active=len(all_signals),
                btc_signals=btc_count,
                eth_signals=eth_count,
                diagnostics=diagnostics,
                timestamp=datetime.now(timezone.utc),
            )

            self._cached_response = resp
            self._last_cache_time = time.time()
            return resp

    def get_diagnostics(self) -> CryptoScalpDiagnostics:
        """Return the latest scanner diagnostics snapshot."""
        if self._last_diagnostics:
            return self._last_diagnostics
        return CryptoScalpDiagnostics(
            data_quality=DataStatus.LIVE,
            candles_count={"BTCUSDT": 60, "ETHUSDT": 60},
            strategies_evaluated=len(CRYPTO_SCALP_STRATEGIES),
            candidates_found=len(self._active_signals),
            duration_ms=self._last_scan_duration_ms,
            last_scan_time=self._last_scan_time,
            worker_running=False,
            scan_interval_seconds=settings.crypto_scalp_scan_interval_seconds,
            telegram_enabled=settings.crypto_scalp_telegram_enabled,
            supabase_persisted_count=self._total_persisted_count,
            errors=[],
        )


crypto_scalp_scanner = CryptoScalpScanner()
