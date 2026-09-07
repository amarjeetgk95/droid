"""
Crypto Scalp Scanner — Core Institutional Engine
Dual-cadence quantitative scanner for Bitcoin and Ethereum across 5 Quant Strategies.
Enforces:
  1. Trigger Integrity Gate (Anti born-triggered, minimum gap, dust stops)
  2. Central Risk Engine (Asset envelopes, no structural stop clamping, fractional sizing)
  3. Multi-Domain Confluence Fusion (Technical, MTF, Derivatives/Funding, Regime, Sentiment)
  4. 11-State Finite State Machine (FSM) Registration & Two-Clock Lifecycle
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Any
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
from app.crypto_scalp.trigger_gate import check_crypto_trigger_integrity
from app.crypto_scalp.risk_engine import crypto_risk_engine, CryptoStrategySetup
from app.crypto_scalp.confluence import crypto_confluence_engine
from app.crypto_scalp.fsm import crypto_signal_fsm, CryptoSignalInstance
from app.crypto_scalp.sse import crypto_sse_hub
from app.crypto_scalp.persistence import persist_scalp_signal, fetch_persisted_scalp_signals
from app.crypto_scalp.telegram import dispatch_crypto_scalp_telegram
from app.models.crypto import (
    CryptoScalpSignal,
    CryptoScalpSignalsResponse,
    CryptoScalpDiagnostics,
    CryptoSignalStatus,
    SignalDirection,
)
from app.models.market import DataStatus
from app.services.binance_service import binance_service

logger = structlog.get_logger()

DEFAULT_SCALP_SYMBOLS = ["BTCUSDT", "ETHUSDT"]


class CryptoScalpScanner:
    """Production 24/7 Scalp Scanner for Bitcoin and Ethereum with institutional risk gating."""

    # 3-minute cooldown per symbol before another scalp signal can be emitted
    SYMBOL_COOLDOWN_SECONDS: float = 180.0
    GLOBAL_MAX_ACTIVE_SIGNALS: int = 4

    @staticmethod
    def _infer_regime(ctx: CryptoScalpContext) -> str:
        """Infer market regime from actual candles so confluence scoring is direction-neutral."""
        candles = ctx.candles_15m or ctx.candles_5m or ctx.candles_1m
        if candles and len(candles) >= 5:
            closes = [c.close for c in candles[-10:]]
            first = closes[0]
            last = closes[-1]
            if first > 0:
                move_pct = (last - first) / first * 100.0
                if move_pct >= 0.15:
                    return "TREND_UP"
                if move_pct <= -0.15:
                    return "TREND_DOWN"
        return "RANGE"

    def __init__(self):
        self._active_signals: dict[str, CryptoScalpSignal] = {}
        self._last_signal_time: dict[str, float] = {}
        self._last_scan_time: datetime | None = None
        self._last_scan_duration_ms: float = 0.0
        self._last_diagnostics: CryptoScalpDiagnostics | None = None
        self._cache_ttl_seconds: float = 5.0
        self._last_cache_time: float = 0.0
        # Response cache keyed by (timeframe, desk) so the 1m scalp and 5m intraday
        # cadences never clobber each other's responses.
        self._cached_responses: dict[tuple[str, str], CryptoScalpSignalsResponse] = {}
        self._lock = asyncio.Lock()
        self._total_persisted_count: int = 0

    async def build_context(self, symbol: str, timeframe: str = "1m") -> CryptoScalpContext | None:
        """Fetch market data and build rich CryptoScalpContext for a symbol."""
        clean_sym = binance_service.validate_symbol(symbol)
        asset = "BTC" if "BTC" in clean_sym else "ETH"

        try:
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

            if not candles_1m or len(candles_1m) < 15:
                logger.warning("insufficient_1m_candles", symbol=clean_sym, count=len(candles_1m) if candles_1m else 0)
                return None

            current_price = candles_1m[-1].close
            if current_price <= 0:
                return None

            closes_1m = [c.close for c in candles_1m]
            ema_9 = calc_ema(closes_1m, 9)
            ema_21 = calc_ema(closes_1m, 21)
            ema_50 = calc_ema(closes_1m, 50)
            atr_14 = calc_atr(candles_1m, 14)
            vwap = calc_vwap(candles_1m)

            recent_vols = [c.volume for c in candles_1m[-21:-1]]
            avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else candles_1m[-1].volume
            current_vol = candles_1m[-1].volume
            vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0

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

    async def scan_symbol(
        self,
        symbol: str,
        timeframe: str = "1m",
        desk: str = "SCALP",
    ) -> list[CryptoScalpSignal]:
        """
        Scan a single symbol with full institutional gating pipeline:
          Trigger Integrity -> Central Risk Envelopes -> Confluence Fusion -> FSM Registration.
        """
        ctx = await self.build_context(symbol, timeframe=timeframe)
        if not ctx:
            return []

        # Check existing non-terminal FSM signals for this symbol first: never
        # double-scan while a signal is already armed/confirmed/open for the symbol.
        in_flight = crypto_signal_fsm.list_active(symbol=ctx.symbol)
        terminal_states = {"TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"}
        non_terminal = [s for s in in_flight if s.fsm_state not in terminal_states]
        if non_terminal:
            # Update current price on active FSM instances
            for s in in_flight:
                s.spot_price = Decimal(str(ctx.current_price))
            return [s for s in self._active_signals.values() if s.symbol == ctx.symbol and s.status == CryptoSignalStatus.ACTIVE]

        now = time.time()
        last_time = self._last_signal_time.get(ctx.symbol, 0.0)
        if (now - last_time) < self.SYMBOL_COOLDOWN_SECONDS:
            return []

        # Check global concurrency cap
        total_open = len([s for s in crypto_signal_fsm.list_active() if s.fsm_state in ("CONFIRMED", "TARGET_1_HIT")])
        if total_open >= self.GLOBAL_MAX_ACTIVE_SIGNALS:
            return []

        spot_d = Decimal(str(ctx.current_price))
        is_scalp = desk == "SCALP" or timeframe in ("1m", "3m")

        # Evaluate strategy candidates
        valid_candidates = []
        for strat_code, strategy in CRYPTO_SCALP_STRATEGIES.items():
            try:
                cand = strategy.detect(ctx)
                if not cand:
                    continue

                # ── 1. Pre-risk sanity filter (SL %, R:R, confidence) ──
                filter_ok, filter_reason = crypto_scalp_risk_filter.validate(cand)
                if not filter_ok:
                    logger.debug("crypto_candidate_rejected_risk_filter", strategy=strat_code, reason=filter_reason)
                    continue

                # ── 2. Trigger level resolution ──
                raw_trig = cand.entry_price
                dir_str = cand.direction.value.upper()
                is_short = "SHORT" in dir_str
                entry_style = str(getattr(strategy, "entry_style", "BREAKOUT")).upper()

                if entry_style in ("MARKET", "REVERSION"):
                    # Mean-reversion / momentum strategies execute at spot — do NOT
                    # displace the trigger onto the breakout side (that turned every
                    # VWAP bounce into a breakout chase).
                    raw_trig = ctx.current_price
                else:
                    # Breakout entries: ensure trigger sits on breakout side
                    gap_floor = float(spot_d * Decimal("0.0004"))  # 0.04% breakout gap
                    if not is_short and raw_trig <= ctx.current_price:
                        raw_trig = ctx.current_price + max(gap_floor, float(cand.risk_points or 20.0) * 0.1)
                    elif is_short and raw_trig >= ctx.current_price:
                        raw_trig = ctx.current_price - max(gap_floor, float(cand.risk_points or 20.0) * 0.1)

                trig_d = Decimal(str(round(raw_trig, 2)))
                sl_d = Decimal(str(round(cand.stop_loss, 2)))

                # Project targets cleanly from the trigger level (1.5R and 2.5R)
                risk_pts_val = max(Decimal("1.0"), abs(trig_d - sl_d))
                if not is_short:
                    t1_d = trig_d + (risk_pts_val * Decimal("1.5"))
                    t2_d = trig_d + (risk_pts_val * Decimal("2.5"))
                else:
                    t1_d = trig_d - (risk_pts_val * Decimal("1.5"))
                    t2_d = trig_d - (risk_pts_val * Decimal("2.5"))

                # ── 3. Trigger Integrity Gate ──
                gate_res = check_crypto_trigger_integrity(
                    symbol=ctx.symbol,
                    strategy=strat_code,
                    direction=dir_str,
                    spot_price=spot_d,
                    trigger=trig_d,
                    stop_loss=sl_d,
                    target_1=t1_d,
                    target_2=t2_d,
                    is_scalp=is_scalp,
                    timeframe=timeframe,
                    entry_style=entry_style,
                )
                if not gate_res.passed:
                    logger.debug("crypto_candidate_rejected_trigger_gate", strategy=strat_code, reason=gate_res.reason_code)
                    continue

                # ── 4. Central Risk Engine Validation & Envelopes ──
                setup = CryptoStrategySetup(
                    strategy_name=strat_code,
                    symbol=ctx.symbol,
                    direction="SHORT" if is_short else "LONG",
                    timeframe=timeframe,  # type: ignore
                    is_scalp=is_scalp,
                    spot_price=spot_d,
                    entry_trigger=trig_d,
                    raw_structural_stop=sl_d,
                    structural_target_candidates=[t1_d, t2_d],
                    atr_val=Decimal(str(round(ctx.atr_14_1m or 50.0, 2))),
                    confidence=cand.confidence,
                )
                risk_decision = crypto_risk_engine.evaluate(setup)
                if not risk_decision.accepted:
                    logger.debug("crypto_candidate_rejected_risk_engine", strategy=strat_code, reason=risk_decision.rejection_reason)
                    continue

                # ── 5. Multi-Domain Confluence Fusion (direction-neutral regime) ──
                fused_conf, conf_breakdown = crypto_confluence_engine.fuse(
                    symbol=ctx.symbol,
                    direction="SHORT" if is_short else "LONG",
                    strategy=strat_code,
                    ctx=ctx,
                    regime=self._infer_regime(ctx),
                )

                if fused_conf < 70.0:
                    logger.debug("crypto_candidate_insufficient_confluence", strategy=strat_code, score=fused_conf)
                    continue

                cand.entry_price = float(risk_decision.entry_price)
                cand.stop_loss = float(risk_decision.stop_loss)
                cand.target_1 = float(risk_decision.target_1)
                cand.target_2 = float(risk_decision.target_2)
                cand.risk_points = risk_decision.risk_points
                cand.confidence = fused_conf

                valid_candidates.append((cand, risk_decision, conf_breakdown))
            except Exception as e:
                logger.warning("crypto_scalp_strategy_eval_failed", strategy=strat_code, symbol=symbol, error=str(e))

        if not valid_candidates:
            return []

        # Select highest-confidence candidate
        best_cand, best_risk, best_breakdown = max(valid_candidates, key=lambda x: x[0].confidence)

        # Generate deterministic Signal ID (includes desk timeframe so 1m scalp and
        # 5m intraday desks can never collide on the same candle timestamp)
        last_candle = ctx.candles_1m[-1]
        candle_ts = int(last_candle.timestamp.timestamp()) if hasattr(last_candle.timestamp, "timestamp") else int(time.time())
        signal_id = f"SCALP-{ctx.symbol}-{best_cand.strategy}-{best_cand.direction.value}-{timeframe}-{candle_ts}"

        # ── 5. Register with Deterministic Crypto FSM ──
        fsm_instance = CryptoSignalInstance(
            signal_id=signal_id,
            symbol=ctx.symbol,
            asset=best_cand.asset,
            direction="SHORT" if "SHORT" in best_cand.direction.value.upper() else "LONG",
            strategy=best_cand.strategy,
            strategy_name=best_cand.strategy_name,
            timeframe=timeframe,
            is_scalp=is_scalp,
            spot_price=spot_d,
            trigger=Decimal(str(best_cand.entry_price)),
            stop_loss=Decimal(str(best_cand.stop_loss)),
            target_1=Decimal(str(best_cand.target_1)),
            target_2=Decimal(str(best_cand.target_2)),
            risk_points=Decimal(str(best_risk.risk_points)),
            risk_reward_t1=best_risk.risk_reward_t1,
            risk_reward_t2=best_risk.risk_reward_t2,
            confidence=best_cand.confidence,
            confluence_breakdown=best_breakdown,
            rationale=[best_cand.rationale],
            ttl_seconds=best_risk.trigger_ttl_seconds,
            time_stop_seconds=best_risk.active_time_stop_seconds,
            runner_ttl_seconds=best_risk.runner_ttl_seconds,
            quantity=best_risk.quantity,
            notional_usd=best_risk.notional_usd,
            max_usd_loss=best_risk.max_usd_loss,
            fsm_state="ARMED" if best_cand.confidence >= 70.0 else "VALIDATED",
        )
        crypto_signal_fsm.register(fsm_instance)

        # ── 6. Create Frontend Compatibility Signal ──
        new_signal = CryptoScalpSignal(
            id=signal_id,
            symbol=best_cand.symbol,
            asset=best_cand.asset,
            direction=best_cand.direction,
            strategy=best_cand.strategy,
            strategy_name=best_cand.strategy_name,
            entry_price=best_cand.entry_price,
            stop_loss=best_cand.stop_loss,
            target_1=best_cand.target_1,
            target_2=best_cand.target_2,
            current_price=ctx.current_price,
            risk_points=best_cand.risk_points,
            risk_percent=best_cand.risk_percent,
            risk_reward_ratio=best_cand.risk_reward_ratio,
            confidence=best_cand.confidence,
            timeframe=timeframe,
            status=CryptoSignalStatus.ACTIVE,
            confluence_factors=best_cand.confluence_factors,
            rationale=best_cand.rationale,
            atr_value=best_cand.atr_value,
            volume_ratio=best_cand.volume_ratio,
            funding_rate=best_cand.funding_rate,
            depth_imbalance=best_cand.depth_imbalance,
            is_scalp=is_scalp,
            fsm_state=fsm_instance.fsm_state,
            created_at_utc=fsm_instance.created_at_utc,
            created_at_str=fsm_instance.created_at_str,
            ttl_seconds=fsm_instance.ttl_seconds,
            time_stop_seconds=fsm_instance.time_stop_seconds or 900,
        )

        await persist_scalp_signal(new_signal)
        self._total_persisted_count += 1
        self._last_signal_time[ctx.symbol] = now
        self._active_signals[signal_id] = new_signal

        # Broadcast via Crypto SSE Hub (Priority 0: Signal Created)
        try:
            await crypto_sse_hub.broadcast("signal_created", fsm_instance.model_dump(), priority="P0")
        except Exception:
            pass

        # Optional Telegram Alert
        if settings.crypto_scalp_telegram_enabled:
            asyncio.create_task(dispatch_crypto_scalp_telegram(new_signal))

        logger.info(
            "crypto_scalp_signal_generated_institutional",
            signal_id=signal_id,
            symbol=new_signal.symbol,
            direction=new_signal.direction.value,
            strategy=new_signal.strategy,
            confidence=new_signal.confidence,
            trigger=float(fsm_instance.trigger),
            sl=float(fsm_instance.stop_loss),
            t1=float(fsm_instance.target_1),
        )
        return [new_signal]

    async def scan_scalp(self) -> CryptoScalpSignalsResponse:
        """Scan 1M timeframe for High-Frequency Crypto Scalps."""
        return await self.scan_all(timeframe="1m", desk="SCALP")

    async def scan_intraday(self) -> CryptoScalpSignalsResponse:
        """Scan 5M timeframe for Core Intraday Crypto setups."""
        return await self.scan_all(timeframe="5m", desk="INTRADAY")

    async def scan_all(
        self,
        force_refresh: bool = False,
        timeframe: str = "1m",
        desk: str = "SCALP",
    ) -> CryptoScalpSignalsResponse:
        """Scan all monitored crypto pairs across requested desk."""
        now = time.time()
        cache_key = (timeframe, desk)
        cached = self._cached_responses.get(cache_key)
        if not force_refresh and cached and (now - self._last_cache_time) < self._cache_ttl_seconds:
            return cached

        async with self._lock:
            cached = self._cached_responses.get(cache_key)
            if not force_refresh and cached and (time.time() - self._last_cache_time) < self._cache_ttl_seconds:
                return cached

            start_t = time.perf_counter()
            all_signals: list[CryptoScalpSignal] = []
            errors: list[str] = []
            candle_counts: dict[str, int] = {}

            # Sweep expired active signals
            crypto_signal_fsm.sweep_expired()

            expire_threshold_ms = int((time.time() - self.SYMBOL_COOLDOWN_SECONDS) * 1000)
            for sid, sig in list(self._active_signals.items()):
                if sig.created_at_utc < expire_threshold_ms:
                    self._active_signals.pop(sid, None)

            # Scan each symbol in universe
            for sym in DEFAULT_SCALP_SYMBOLS:
                try:
                    signals = await self.scan_symbol(sym, timeframe=timeframe, desk=desk)
                    all_signals.extend(signals)
                    candle_counts[sym] = 60
                except Exception as e:
                    errors.append(f"{sym}: {str(e)}")

            if not all_signals:
                recent_persisted = await fetch_persisted_scalp_signals(limit=10)
                symbols_seen: set[str] = set()
                for s in recent_persisted:
                    if s.created_at_utc >= expire_threshold_ms and s.symbol not in symbols_seen:
                        symbols_seen.add(s.symbol)
                        if s.id not in self._active_signals:
                            self._active_signals[s.id] = s

                all_signals = [s for s in self._active_signals.values() if s.created_at_utc >= expire_threshold_ms]

            # Also surface active non-terminal signals directly from Crypto FSM Manager
            fsm_active = crypto_signal_fsm.list_active(include_terminal=False)
            existing_ids = {s.id for s in all_signals}
            for fs in fsm_active:
                if fs.signal_id not in existing_ids:
                    all_signals.append(
                        CryptoScalpSignal(
                            id=fs.signal_id,
                            symbol=fs.symbol,
                            asset=fs.asset,
                            direction=SignalDirection.LONG if fs.direction == "LONG" else SignalDirection.SHORT,
                            strategy=fs.strategy,
                            strategy_name=fs.strategy_name or fs.strategy,
                            entry_price=float(fs.trigger),
                            stop_loss=float(fs.current_stop_loss or fs.stop_loss),
                            target_1=float(fs.t1_price or fs.target_1),
                            target_2=float(fs.t2_price or fs.target_2),
                            current_price=float(fs.spot_price),
                            risk_points=float(fs.risk_points),
                            risk_percent=float(round(abs(fs.trigger - fs.stop_loss) / max(Decimal("1"), fs.spot_price) * Decimal("100"), 2)),
                            risk_reward_ratio=float(fs.risk_reward_t1),
                            confidence=float(fs.confidence),
                            timeframe=fs.timeframe,
                            status=CryptoSignalStatus.ACTIVE,
                            confluence_factors=[f"{k}: {v:.0f}%" for k, v in fs.confluence_breakdown.items() if isinstance(v, (int, float))],
                            rationale=fs.rationale[0] if fs.rationale else f"{fs.symbol} {fs.fsm_state}",
                            is_scalp=fs.is_scalp,
                            created_at_utc=fs.created_at_utc,
                        )
                    )

            deduped_signals: list[CryptoScalpSignal] = []
            seen_symbols: set[str] = set()
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
                scan_interval_seconds=crypto_scalp_worker.interval_seconds,
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

            self._cached_responses[cache_key] = resp
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
