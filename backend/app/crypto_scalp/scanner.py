"""
Crypto Scalp Scanner — Core Engine
Fetches Binance market data, constructs analysis context, evaluates all 5 strategies,
filters through risk engine, persists to Supabase, and dispatches Telegram notifications.
"""
from __future__ import annotations

import asyncio
import time
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
    """Production 24/7 Scalp Scanner for Bitcoin and Ethereum with strict throttling."""

    # 30-minute cooldown per symbol before another scalp signal can be emitted
    SYMBOL_COOLDOWN_SECONDS: float = 1800.0
    # Strict maximum concurrent active signals across the entire system
    GLOBAL_MAX_ACTIVE_SIGNALS: int = 2

    def __init__(self):
        self._active_signals: dict[str, CryptoScalpSignal] = {}
        self._last_signal_time: dict[str, float] = {}
        self._last_scan_time: datetime | None = None
        self._last_scan_duration_ms: float = 0.0
        self._last_diagnostics: CryptoScalpDiagnostics | None = None
        self._cache_ttl_seconds: float = 5.0
        self._last_cache_time: float = 0.0
        self._cached_response: CryptoScalpSignalsResponse | None = None
        self._lock = asyncio.Lock()
        self._total_persisted_count: int = 0

    async def build_context(self, symbol: str) -> CryptoScalpContext | None:
        """Fetch market data and build CryptoScalpContext for a symbol with fail-closed checks."""
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

            # Fail-closed if live market feed is insufficient
            if not candles_1m or len(candles_1m) < 15:
                logger.warning("insufficient_1m_candles", symbol=clean_sym, count=len(candles_1m) if candles_1m else 0)
                return None

            if not orderbook or orderbook.spread_percent is None:
                logger.warning("orderbook_unavailable", symbol=clean_sym)
                return None

            current_price = candles_1m[-1].close
            if current_price <= 0:
                return None

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
        """
        Scan a single symbol across all strategies with strict 1-signal cap & cooldown.
        Returns active signal(s) for the symbol.
        """
        ctx = await self.build_context(symbol)
        if not ctx:
            return []

        # 1. Check if this symbol already has an ACTIVE signal
        existing_active = [
            s for s in self._active_signals.values()
            if s.symbol == ctx.symbol and s.status == CryptoSignalStatus.ACTIVE
        ]
        if existing_active:
            # Update current price on active signal without generating a new one
            for s in existing_active:
                s.current_price = ctx.current_price
            return existing_active

        # 2. Check 30-minute cooldown for this symbol
        now = time.time()
        last_time = self._last_signal_time.get(ctx.symbol, 0.0)
        time_since_last = now - last_time
        if time_since_last < self.SYMBOL_COOLDOWN_SECONDS:
            remaining_min = (self.SYMBOL_COOLDOWN_SECONDS - time_since_last) / 60.0
            logger.debug(
                "crypto_scalp_symbol_in_cooldown",
                symbol=ctx.symbol,
                cooldown_remaining_min=round(remaining_min, 1),
            )
            return []

        # 3. Check global concurrency cap
        total_active = len([s for s in self._active_signals.values() if s.status == CryptoSignalStatus.ACTIVE])
        if total_active >= self.GLOBAL_MAX_ACTIVE_SIGNALS:
            logger.debug("crypto_scalp_global_cap_reached", total_active=total_active)
            return []

        # 4. Evaluate all strategies and collect valid candidates
        candidates = []
        for strat_code, strategy in CRYPTO_SCALP_STRATEGIES.items():
            try:
                cand = strategy.detect(ctx)
                if not cand:
                    continue

                is_valid, reason = crypto_scalp_risk_filter.validate(cand)
                if not is_valid:
                    logger.debug("crypto_scalp_candidate_rejected", strategy=strat_code, reason=reason)
                    continue

                candidates.append(cand)
            except Exception as e:
                logger.warning("crypto_scalp_strategy_error", strategy=strat_code, symbol=symbol, error=str(e))

        if not candidates:
            return []

        # 5. Pick ONLY the single highest-confidence candidate
        best_candidate = max(candidates, key=lambda c: c.confidence)

        # 6. Generate deterministic signal ID based on last candle timestamp
        last_candle = ctx.candles_1m[-1]
        candle_ts = int(last_candle.timestamp.timestamp()) if hasattr(last_candle.timestamp, "timestamp") else int(time.time())
        signal_id = f"SCALP-{ctx.symbol}-{best_candidate.strategy}-{best_candidate.direction.value}-{candle_ts}"

        # Double check if this exact setup was already created
        if signal_id in self._active_signals:
            existing = self._active_signals[signal_id]
            existing.current_price = ctx.current_price
            return [existing]

        # 7. Create new high-conviction signal
        new_signal = CryptoScalpSignal(
            id=signal_id,
            symbol=best_candidate.symbol,
            asset=best_candidate.asset,
            direction=best_candidate.direction,
            strategy=best_candidate.strategy,
            strategy_name=best_candidate.strategy_name,
            entry_price=best_candidate.entry_price,
            stop_loss=best_candidate.stop_loss,
            target_1=best_candidate.target_1,
            target_2=best_candidate.target_2,
            current_price=ctx.current_price,
            risk_points=best_candidate.risk_points,
            risk_percent=best_candidate.risk_percent,
            risk_reward_ratio=best_candidate.risk_reward_ratio,
            confidence=best_candidate.confidence,
            timeframe=best_candidate.timeframe,
            status=CryptoSignalStatus.ACTIVE,
            confluence_factors=best_candidate.confluence_factors,
            rationale=best_candidate.rationale,
            atr_value=best_candidate.atr_value,
            volume_ratio=best_candidate.volume_ratio,
            funding_rate=best_candidate.funding_rate,
            depth_imbalance=best_candidate.depth_imbalance,
            is_scalp=True,
            created_at_utc=int(time.time() * 1000),
        )

        # Persist and notify
        await persist_scalp_signal(new_signal)
        self._total_persisted_count += 1
        self._last_signal_time[ctx.symbol] = now
        self._active_signals[signal_id] = new_signal

        # Register with outcome tracker for deterministic paper execution & track record
        spread_usd = (ctx.orderbook.best_ask - ctx.orderbook.best_bid) if ctx.orderbook and ctx.orderbook.best_ask and ctx.orderbook.best_bid else 0.0
        try:
            from app.crypto_scalp.outcome_tracker import crypto_scalp_outcome_tracker
            asyncio.create_task(crypto_scalp_outcome_tracker.register_signal(new_signal, spread=spread_usd))
        except Exception as reg_err:
            logger.warning("register_signal_outcome_tracker_failed", error=str(reg_err)[:200])

        if settings.crypto_scalp_telegram_enabled:
            asyncio.create_task(dispatch_crypto_scalp_telegram(new_signal))

        logger.info(
            "crypto_scalp_signal_generated",
            signal_id=signal_id,
            symbol=new_signal.symbol,
            direction=new_signal.direction.value,
            strategy=new_signal.strategy,
            confidence=new_signal.confidence,
        )

        return [new_signal]

    async def scan_all(self, force_refresh: bool = False) -> CryptoScalpSignalsResponse:
        """Scan all monitored symbols and return active signals with diagnostics."""
        now = time.time()
        if not force_refresh and self._cached_response and (now - self._last_cache_time) < self._cache_ttl_seconds:
            return self._cached_response

        async with self._lock:
            if not force_refresh and self._cached_response and (time.time() - self._last_cache_time) < self._cache_ttl_seconds:
                return self._cached_response

            start_t = time.perf_counter()
            all_signals: list[CryptoScalpSignal] = []
            errors: list[str] = []
            candle_counts: dict[str, int] = {}

            # Sweep expired active signals (older than 30 minutes)
            expire_threshold_ms = int((time.time() - self.SYMBOL_COOLDOWN_SECONDS) * 1000)
            for sid, sig in list(self._active_signals.items()):
                if sig.created_at_utc < expire_threshold_ms:
                    self._active_signals.pop(sid, None)

            # Scan each default symbol (strictly 1 active signal per symbol)
            for sym in DEFAULT_SCALP_SYMBOLS:
                try:
                    signals = await self.scan_symbol(sym)
                    all_signals.extend(signals)
                    candle_counts[sym] = 60
                except Exception as e:
                    errors.append(f"{sym}: {str(e)}")

            # If no active signals discovered in this cycle, restore at most 1 recent active signal per symbol from persistence
            if not all_signals:
                recent_persisted = await fetch_persisted_scalp_signals(limit=10)
                symbols_seen: set[str] = set()
                for s in recent_persisted:
                    # Only accept signals that are still within the 30-minute freshness window
                    if s.created_at_utc >= expire_threshold_ms and s.symbol not in symbols_seen:
                        symbols_seen.add(s.symbol)
                        if s.id not in self._active_signals:
                            self._active_signals[s.id] = s

                all_signals = [s for s in self._active_signals.values() if s.created_at_utc >= expire_threshold_ms]

            # Enforce strict 1-signal-per-symbol cap on final list
            deduped_signals: list[CryptoScalpSignal] = []
            seen_symbols: set[str] = set()
            # Sort by created_at_utc descending, then confidence
            all_signals.sort(key=lambda s: (s.created_at_utc, s.confidence), reverse=True)
            for s in all_signals:
                if s.symbol not in seen_symbols:
                    seen_symbols.add(s.symbol)
                    deduped_signals.append(s)

            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            self._last_scan_time = datetime.now(timezone.utc)
            self._last_scan_duration_ms = duration_ms

            btc_count = sum(1 for s in deduped_signals if "BTC" in s.symbol)
            eth_count = sum(1 for s in deduped_signals if "ETH" in s.symbol)

            from app.crypto_scalp.worker import crypto_scalp_worker

            diagnostics = CryptoScalpDiagnostics(
                data_quality=DataStatus.LIVE if not errors else DataStatus.DEGRADED,
                candles_count=candle_counts,
                strategies_evaluated=len(CRYPTO_SCALP_STRATEGIES),
                candidates_found=len(deduped_signals),
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
                signals=deduped_signals,
                total_active=len(deduped_signals),
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
