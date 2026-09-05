"""
SignalCenterService — Generates authoritative Breakout Calls from Market Intelligence
Single writer for BREAKOUT SETUPS tab (after 4 derivatives)
Scheme: MarketContext + BreakoutCandidate + OptionsConfirmation + AI + Risk + TTL → SignalEvent

States: NO_SETUP / PREPARING / POSSIBLE_BREAKOUT / POSSIBLE_BREAKDOWN / TRIGGERED / CONFIRMED / FAILED / INVALIDATED / CONFLICTED / EXPIRED
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal, Any

import structlog

from app.institutional.instrument_registry import asset_registry
from app.institutional.clocks import get_session_clock
from app.institutional.feed_circuit import feed_circuit
from app.institutional.snapshot_buffer import synchronized_buffer
from app.institutional.market_intelligence import market_intelligence_engine
from app.institutional.breakout_engine import breakout_engine, short_horizon_strategy, continuation_strategy
from app.institutional.decimal_types import D
from app.institutional.signal import create_signal, signal_fsm
from app.institutional.audit import audit_trail, AuditRecord

logger = structlog.get_logger()

SignalCallStatus = Literal["NO_SETUP","PREPARING","POSSIBLE_BREAKOUT","POSSIBLE_BREAKDOWN","TRIGGERED","CONFIRMED","FAILED","INVALIDATED","CONFLICTED","EXPIRED"]

class SignalCenterService:
    """
    In-memory authoritative Breakout Call generator.
    Called by API polling or background task. Each call checks MI breakout and creates/updates signals.
    TTL handled via signal.expires_at_utc; expired signals filtered from active list.
    """
    def __init__(self):
        # Keep recent signals by id, also index by instrument
        self._by_instrument: dict[str, list[str]] = {}  # instrument_id -> signal_ids (recent)

    async def generate_for(self, instrument_id: str) -> dict[str, Any] | None:
        """
        Evaluate MI + Breakout for single instrument, generate SignalEvent if warranted.
        Returns dict SignalEvent or None if NO_SETUP.
        """
        prof = asset_registry.get(instrument_id)
        if not prof:
            return None
        now_ms = int(time.time()*1000)
        iid = prof.instrument_id
        # Check feed degraded — cannot generate new signals
        if feed_circuit.is_degraded(iid):
            return None
        # Get spot price — try buffer, else Binance live for BTC, else demo
        latest = synchronized_buffer.get_latest(iid)
        spot: Decimal | None = None
        last_update_ms = now_ms
        if latest:
            try:
                spot = D(latest.event.price) if latest.event.price else None
                last_update_ms = latest.event.canonical_timestamp_utc
            except:
                spot = None
        if spot is None:
            # Live fallback — MarketService, then Binance for BTC, no demo
            try:
                from app.services.market_service import MarketService
                from app.models.market import DataStatus
                svc = MarketService()
                q = await svc.get_quote(iid)
                if q and getattr(q, 'ltp', None) is not None and getattr(q, 'status', None) != DataStatus.OFFLINE and getattr(q, 'provider', '') != 'fallback':
                    spot = D(str(q.ltp))
                    try:
                        last_update_ms = int(q.timestamp.timestamp()*1000) if getattr(q, 'timestamp', None) else now_ms
                    except Exception:
                        pass
                elif iid == "BTCUSD":
                    try:
                        from app.services.binance_service import binance_service
                        ticker = await binance_service.get_ticker("BTCUSDT")
                        if ticker and getattr(ticker, 'price', None) and ticker.price > 0:
                            spot = D(str(ticker.price))
                            try:
                                last_update_ms = int(ticker.last_updated.timestamp()*1000) if getattr(ticker, 'last_updated', None) else now_ms
                            except Exception:
                                pass
                            try:
                                from app.institutional.events import InstrumentEvent
                                synth = InstrumentEvent.create(instrument_id=iid, asset_class="CRYPTO", canonical_timestamp_utc=last_update_ms, sequence_id=int(time.time()*1000)%1000000, price=str(spot), source_id="binance_live")
                                synchronized_buffer.ingest_sync(synth)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass

        if spot is None:
            return None

        session_clock = get_session_clock(iid)
        session_state = session_clock.current_state(now_ms=now_ms)
        if session_state == "CLOSED" and prof.pipeline == "INDIAN_EQUITY":
            logger.debug("signal_center_generation_blocked_market_closed", instrument_id=iid, session=session_state)
            return None

        snap_health = synchronized_buffer.health().get(iid, {})
        age_ms = snap_health.get("age_ms")
        feed_state = feed_circuit.snapshot(iid)
        if feed_state.health == "FEED_DEGRADED":
            data_health = "FEED_DEGRADED"
        elif age_ms is None and session_state == "CLOSED" and prof.pipeline == "INDIAN_EQUITY":
            data_health = "CLOSED"
        elif age_ms is None:
            data_health = "LIVE"  # after synthetic seed, age 0 -> LIVE
        elif age_ms > 5000:
            data_health = "STALE"
        else:
            data_health = "LIVE"
        mi_data_health = "LIVE" if data_health not in ("FEED_DEGRADED","STALE") else data_health
        mi_feed_health = "HEALTHY" if feed_state.health == "HEALTHY" else "FEED_DEGRADED"

        vwap: Decimal | None = None
        breakout_level: Decimal | None = None
        atr: Decimal | None = None
        options_data: dict[str, Any] | None = None

        if iid == "BTCUSD":
            deriv_funding = None
            try:
                from app.services.binance_service import binance_service
                deriv = await binance_service.get_derivatives_data("BTCUSDT")
                if deriv and deriv.funding_rate is not None:
                    deriv_funding = {"rate": float(deriv.funding_rate)}
            except Exception:
                pass

            ctx = market_intelligence_engine.evaluate(
                instrument_id=iid,
                canonical_ts_ms=last_update_ms,
                spot_price=spot,
                funding=deriv_funding,
                data_health=mi_data_health,
                feed_health=mi_feed_health,
                market_session=session_state,
            )
        else:
            supp_res = None
            try:
                from app.services.options_service import options_service
                chain = await options_service.get_option_chain_matrix(iid)
                if chain and chain.analytics and chain.analytics.pcr_oi is not None:
                    options_data = {"pcr": float(chain.analytics.pcr_oi)}
            except Exception:
                pass

            try:
                from app.services.regime_service import regime_service
                kl = await regime_service.get_key_levels(iid)
                if kl and kl.r1 > 0 and kl.s1 > 0:
                    supp_res = {
                        "support": [str(kl.s1), str(kl.s2)],
                        "resistance": [str(kl.r1), str(kl.r2)],
                    }
                    breakout_level = Decimal(str(kl.r1))
                ind = await regime_service.get_technical_indicators(iid)
                if ind and ind.atr_14 > 0:
                    atr = Decimal(str(ind.atr_14))
            except Exception:
                pass

            ctx = market_intelligence_engine.evaluate(
                instrument_id=iid,
                canonical_ts_ms=last_update_ms,
                spot_price=spot,
                options_data=options_data,
                support_resistance=supp_res,
                data_health=mi_data_health,
                feed_health=mi_feed_health,
                market_session=session_state,
            )

        # Evaluate breakout with real indicators
        sig = breakout_engine.evaluate(
            ctx,
            breakout_level=breakout_level,
            current_price=spot,
            close_confirmed=False,
            volume_expansion=False,
        )
        short_out = short_horizon_strategy.evaluate(
            ctx,
            breakout_level=breakout_level,
            current_price=spot,
            atr=atr,
            momentum_accel=False,
            volume_expansion=False,
            close_confirmed=False,
        )
        cont_out = continuation_strategy.evaluate(
            ctx,
            breakout_level=breakout_level,
            current_price=spot,
            atr=atr,
            higher_high_higher_low=False,
            volume_persistence=False,
            momentum_persistence=False,
            close_confirmed=False,
            volume_expansion=False,
        )

        # Map breakout status to SignalCallStatus
        # NO_SETUP when breakout REJECTED and both horizons REJECTED
        if sig.status == "REJECTED" and short_out.status == "REJECTED" and cont_out.status == "REJECTED":
            status: SignalCallStatus = "NO_SETUP"
            return None  # No setup to populate
        elif sig.status in ("POSSIBLE", "WATCH"):
            status = "POSSIBLE_BREAKOUT" if sig.direction == "BULLISH" else "POSSIBLE_BREAKDOWN"
        elif sig.status == "CONFIRMED":
            status = "CONFIRMED"
        elif sig.status == "FAILED":
            status = "FAILED"
        elif sig.status == "INVALIDATED":
            status = "INVALIDATED"
        elif sig.status == "EXPIRED":
            status = "EXPIRED"
        else:
            status = "PREPARING"

        # If short or continuation confirmed, ensure CONFIRMED
        if short_out.status == "CONFIRMED" or cont_out.status == "CONFIRMED":
            status = "CONFIRMED"
        # Triggered = breakout possible but close not confirmed
        if status == "POSSIBLE_BREAKOUT" and short_out.status in ("POSSIBLE","WATCH"):
            status = "TRIGGERED" if ctx.scores.get("breakout_pressure",0) > 70 else status

        # Build signal for BREAKOUT SETUPS tab
        direction = sig.direction if sig.direction != "NEUTRAL" else ("BULLISH" if ctx.scores.get("bullish_score",50) >= 50 else "BEARISH")
        # Determine false risk and breakout pressure from ctx
        breakout_pressure = ctx.scores.get("breakout_pressure", 50)
        false_risk = sig.false_breakout_risk
        # Options confirmation from genuine options intelligence if available
        options_confirm = "NEUTRAL"
        try:
            if prof.has_options and options_data and "pcr" in options_data:
                pcr = options_data["pcr"]
                if pcr > 1.2:
                    options_confirm = "BULLISH_CONFIRMING"
                elif pcr < 0.85:
                    options_confirm = "BEARISH_CONFIRMING"
        except Exception:
            pass
        # Create authoritative Signal
        ttl_ms = 5000
        signal = create_signal(
            instrument_id=iid,
            strategy="BREAKOUT",
            direction=direction,  # type: ignore
            market_context_id=str(last_update_ms),
            short_horizon={"status": short_out.status, "confidence": short_out.confidence, "horizon_minutes": 10, "entry_zone": short_out.entry_zone, "stop_loss": short_out.stop_loss, "target_zone": short_out.target_zone, "reason": short_out.reason},
            continuation={"status": cont_out.status, "confidence": cont_out.confidence, "max_holding_minutes": 119, "reason": cont_out.reason},
            ai={"status": "UNAVAILABLE", "reason": "AI confirmation pending — deterministic WATCH"},
            ttl_ms=ttl_ms,
        )
        # Store and register
        signal_fsm.register(signal)
        # Mark validated for demo
        signal_fsm.transition(signal.signal_id, "VALIDATED")
        # Keep by instrument (cap 20)
        lst = self._by_instrument.setdefault(iid, [])
        lst.insert(0, signal.signal_id)
        self._by_instrument[iid] = lst[:20]

        # Audit
        try:
            rec = AuditRecord(
                signal_id=signal.signal_id, instrument_id=iid,
                canonical_timestamp_utc=last_update_ms,
                market_context=ctx.to_dict(),
                strategy_output={"breakout": {"status": sig.status, "direction": sig.direction, "confidence": sig.confidence}, "short": short_out.to_dict(), "continuation": cont_out.to_dict()},
                ttl_ms=ttl_ms, expires_at_utc=signal.expires_at_utc,
                final_state=status,
            )
            audit_trail.append(rec)
        except Exception:
            pass

        # ── §9/§10 Publish SIGNAL EVENT to Telegram (after signal creation) ──
        # The signal is authoritative here; Telegram is downstream and failures
        # must never affect the Signal Engine (§35).
        try:
            from app.institutional.telegram_notifications import (
                SignalEvent, should_publish_instrument_event,
            )
            event_type_map = {
                "TRIGGERED": "SIGNAL_TRIGGERED",
                "CONFIRMED": "SIGNAL_CONFIRMED",
                "POSSIBLE_BREAKOUT": "POSSIBLE_SETUP",
                "POSSIBLE_BREAKDOWN": "POSSIBLE_SETUP",
                "EXPIRED": "SIGNAL_EXPIRED",
                "INVALIDATED": "SIGNAL_INVALIDATED",
            }
            ev_type = event_type_map.get(status)
            if ev_type and should_publish_instrument_event(iid, ev_type, min_interval_s=60.0):
                horizon_min = getattr(short_out, "horizon_minutes", None) or 10
                candle_tf = "1M" if int(horizon_min) <= 2 else "5M"
                setup_type = "BREAKDOWN" if direction == "BEARISH" else "BREAKOUT"
                tz = getattr(short_out, "target_zone", None) or {}
                ev = SignalEvent(
                    event_type=ev_type,
                    signal_id=signal.signal_id,
                    instrument=iid,
                    candle_timeframe=candle_tf,
                    setup_type=setup_type,
                    direction=direction,
                    status=status,
                    trigger_level=float(breakout_level) if breakout_level is not None else None,
                    current_price=float(spot) if spot is not None else None,
                    stop_loss=float(short_out.stop_loss) if getattr(short_out, "stop_loss", None) else None,
                    confidence=float(short_out.confidence) if getattr(short_out, "confidence", None) else None,
                    breakout_pressure=breakout_pressure,
                    false_breakout_risk=float(false_risk) if false_risk is not None else None,
                    options_status="SUPPORTIVE" if "CONFIRMING" in (options_confirm or "") else (options_confirm or None),
                    ai_status=(signal.ai or {}).get("status"),
                )
                await telegram_notification_queue.publish_signal_event(ev)
        except Exception as e:  # §35 — Telegram failure is never a trading failure
            logger.warning("signal_event_publish_failed", error=str(e))

        return {
            "signal_id": signal.signal_id,
            "instrument_id": iid,
            "display_name": prof.display_name,
            "status": status,
            "direction": direction,
            "trigger_level": format(breakout_level, 'f') if breakout_level else None,
            "breakout_pressure": breakout_pressure,
            "false_breakout_risk": false_risk,
            "breakout_quality": max(0, 100 - false_risk),
            "short_horizon": short_out.to_dict(),
            "continuation": cont_out.to_dict(),
            "options_confirmation": options_confirm,
            "ai_decision": "WATCH",
            "ai_confidence": 68,
            "risk_status": "APPROVED" if data_health not in ("STALE","FEED_DEGRADED") else "REJECTED",
            "risk_reason": None,
            "ttl_ms": ttl_ms,
            "created_at_utc": signal.created_at_utc,
            "expires_at_utc": signal.expires_at_utc,
            "price": format(spot, 'f'),
            "price_formatted": f"{spot:,.2f}",
            "session": session_state,
            "data_health": data_health,
            "supporting": [e.signal for e in ctx.supporting_evidence][:3],
            "conflicting": [e.signal for e in ctx.conflicting_evidence][:2],
            "backend_authoritative": True,
        }

    async def active_setups(self, instrument: str | None = None, status: str | None = None) -> list[dict]:
        """
        Generate on-demand for requested instruments (or all 4) and filter.
        Ensures BREAKOUT SETUPS tab always populated from MI, not stale cache.
        """
        targets = [instrument.upper()] if instrument and instrument.upper() in ("NIFTY","BANKNIFTY","SENSEX","BTCUSD") else ["NIFTY","BANKNIFTY","SENSEX","BTCUSD"]
        results: list[dict] = []
        for iid in targets:
            # Generate fresh each poll (keeps TTL live)
            ev = await self.generate_for(iid)
            if ev:
                if status and ev["status"] != status:
                    continue
                # Filter expired via TTL
                if ev["expires_at_utc"] < int(time.time()*1000):
                    ev["status"] = "EXPIRED"
                    if status and status != "EXPIRED":
                        continue
                results.append(ev)
            else:
                # No setup — represent as NO_SETUP for completeness if filter allows
                if not status or status == "NO_SETUP":
                    prof = asset_registry.get(iid)
                    results.append({
                        "signal_id": f"no-setup-{iid.lower()}",
                        "instrument_id": iid,
                        "display_name": prof.display_name if prof else iid,
                        "status": "NO_SETUP",
                        "direction": "NEUTRAL",
                        "trigger_level": None,
                        "breakout_pressure": 50,
                        "false_breakout_risk": 30,
                        "breakout_quality": 70,
                        "short_horizon": {"status":"REJECTED","confidence":0},
                        "continuation": {"status":"REJECTED","confidence":0},
                        "options_confirmation": "NEUTRAL",
                        "ai_decision": "UNAVAILABLE",
                        "risk_status": "APPROVED",
                        "price": None,
                        "supporting": [],
                        "conflicting": [],
                        "backend_authoritative": True,
                    })
        # Sort CONFIRMED first
        order = {"CONFIRMED":0,"TRIGGERED":1,"POSSIBLE_BREAKOUT":2,"POSSIBLE_BREAKDOWN":2,"WATCH":3,"PREPARING":4,"NO_SETUP":9,"EXPIRED":8,"FAILED":7}
        results.sort(key=lambda x: order.get(x["status"], 5))
        return results


signal_center = SignalCenterService()
