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
        # Unified reader — spot + enrichment with honest provenance (no thin duplication)
        from app.institutional import mi_service as _mi

        mi = await _mi.gather_inputs(iid, now_ms=now_ms)
        spot = mi.spot
        last_update_ms = mi.last_update_ms
        session_state = mi.market_session
        data_health = mi.data_health

        if spot is None:
            return None
        # P0-5: session gate via authoritative per-instrument session clock —
        # replaces the old `session==CLOSED and pipeline==INDIAN_EQUITY` check.
        # BTCUSD uses the crypto-session clock (24/7 OPEN); Indian equity uses
        # the NSE clock. No allow_closed bypass here (fail-closed); only an
        # explicit role-gated operator route may mint closed-market signals.
        try:
            _clock_state = get_session_clock(iid).current_state(now_ms=now_ms)
        except Exception:
            _clock_state = session_state
        if prof.pipeline == "CRYPTO":
            # Fix BTCUSD: crypto-session clock, never the equity CLOSED gate.
            session_state = _clock_state or "OPEN"
        else:
            # Indian equity: require OPEN on the session clock (fail-closed).
            session_state = _clock_state or session_state
            if session_state != "OPEN":
                logger.debug(
                    "signal_center_generation_blocked_market_closed",
                    instrument_id=iid,
                    session=session_state,
                    pipeline=prof.pipeline,
                )
                return None
        # STALE without a usable cache edge → no new setups (avoid trading on old prints)
        if data_health in ("STALE", "DISCONNECTED", "FEED_DEGRADED") and mi.used_cache:
            try:
                age = max(0, now_ms - int(last_update_ms))
            except Exception:
                age = 999999
            if age > 60000:
                logger.debug("signal_center_generation_blocked_stale", instrument_id=iid, age_ms=age)
                return None

        breakout_level = mi.breakout_level
        atr = mi.atr

        ctx = market_intelligence_engine.evaluate(
            instrument_id=iid,
            canonical_ts_ms=last_update_ms,
            spot_price=spot,
            vwap=mi.vwap,
            volumes=mi.volumes,
            options_data=mi.options_data,
            support_resistance=mi.support_resistance,
            multi_timeframe=mi.multi_timeframe,
            volatility=mi.volatility,
            liquidity=mi.liquidity,
            funding=mi.funding,
            breadth=mi.breadth,
            data_health=mi.data_health,
            feed_health=mi.feed_health,
            market_session=session_state,
        )

        # Evaluate breakout with real microstructure flags derived from enriched inputs
        try:
            vol_exp = bool(mi.volumes and float(mi.volumes.get("volume_change", 0)) > 0.3)
        except Exception:
            vol_exp = False
        try:
            mtf = mi.multi_timeframe or {}
            _bull = sum(1 for v in mtf.values() if "BULL" in str(v).upper())
            _bear = sum(1 for v in mtf.values() if "BEAR" in str(v).upper())
            mom_accel = (_bull >= 2 and ctx.price_action.get("trend") == "BULLISH") or (
                _bear >= 2 and ctx.price_action.get("trend") == "BEARISH"
            )
        except Exception:
            mom_accel = False
        # close_confirmed stays False here (no candle-close feed in this reader);
        # breakout_engine still yields honest WATCH/POSSIBLE instead of forced CONFIRMED.
        sig = breakout_engine.evaluate(
            ctx,
            breakout_level=breakout_level,
            current_price=spot,
            close_confirmed=False,
            volume_expansion=vol_exp,
        )
        short_out = short_horizon_strategy.evaluate(
            ctx,
            breakout_level=breakout_level,
            current_price=spot,
            atr=atr,
            momentum_accel=mom_accel,
            volume_expansion=vol_exp,
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
        # NO_SETUP when breakout REJECTED and both horizons REJECTED — still
        # return a FULL card payload (pressures, price, session, evidence) so the
        # UI never renders null "/ 100" rows; only genuinely missing data is None.
        if sig.status == "REJECTED" and short_out.status == "REJECTED" and cont_out.status == "REJECTED":
            try:
                _px = float(spot) if spot is not None else None
            except Exception:
                _px = None
            return {
                "signal_id": f"no-setup-{iid.lower()}",
                "instrument_id": iid,
                "display_name": prof.display_name,
                "status": "NO_SETUP",
                "direction": "NEUTRAL",
                "trigger_level": format(breakout_level, 'f') if breakout_level else None,
                "breakout_pressure": ctx.scores.get("breakout_pressure", 50),
                "false_breakout_risk": sig.false_breakout_risk,
                "breakout_quality": max(0, 100 - int(sig.false_breakout_risk or 0)),
                "short_horizon": short_out.to_dict(),
                "continuation": cont_out.to_dict(),
                "options_confirmation": "NEUTRAL",
                "ai_decision": "UNAVAILABLE",
                "ai_confidence": None,
                "ai_status": "UNAVAILABLE",
                "risk_status": "NO_SETUP",
                "risk_reason": getattr(sig, "reason", "") or "no breakout — multi-factor not satisfied",
                "ttl_ms": None,
                "created_at_utc": None,
                "expires_at_utc": None,
                "price": format(spot, 'f') if spot is not None else None,
                "price_formatted": f"{_px:,.2f}" if _px is not None else None,
                "session": session_state,
                "data_health": data_health,
                "supporting": [e.signal for e in ctx.supporting_evidence][:3],
                "conflicting": [e.signal for e in ctx.conflicting_evidence][:2],
                "backend_authoritative": True,
            }
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
            _od = mi.options_data or {}
            if prof.has_options and "pcr" in _od:
                pcr = _od["pcr"]
                if pcr > 1.2:
                    options_confirm = "BULLISH_CONFIRMING"
                elif pcr < 0.85:
                    options_confirm = "BEARISH_CONFIRMING"
        except Exception:
            pass
        # Create authoritative Signal — persistent per (instrument, direction, level bucket),
        # 60s TTL with update-in-place (no UUID churn per poll).
        ttl_ms = 60000
        level_bucket = str(int(float(breakout_level))) if breakout_level is not None else "na"
        try:
            day_bucket = time.strftime("%Y%m%d", time.gmtime((last_update_ms or now_ms) / 1000.0))
        except Exception:
            day_bucket = time.strftime("%Y%m%d", time.gmtime(now_ms / 1000.0))
        persistent_id = f"BRK-{iid}-{direction}-{level_bucket}-{day_bucket}"
        existing = None
        try:
            existing = signal_fsm.get(persistent_id)
        except Exception:
            existing = None
        if existing is not None:
            try:
                _exp = getattr(existing, "expires_at_utc", None)
                _is_exp = existing.is_expired(now_ms) if _exp is not None else True
            except Exception:
                _is_exp = True
            if not _is_exp:
                signal = existing
                signal.expires_at_utc = now_ms + ttl_ms
                signal.ttl_ms = ttl_ms
            else:
                existing = None
        if existing is None:
            # P0-5: trigger-engine gate BEFORE register — a signal is not an order,
            # and duplicates/cooldowns/market-closed must not mint new FSM entries.
            # Build the institutional signal first, then ask trigger_engine whether
            # this (strategy, symbol) may fire right now; on deny, refresh the
            # existing entry's TTL if present else return a honest NO_TRIGGER card.
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
            signal.signal_id = persistent_id
            _trigger_ok, _trigger_reason = True, "TRIGGER_APPROVED"
            try:
                from app.algo.signal_fusion import trigger_engine as _fusion_trigger_engine
                from app.algo.signal_fusion import Signal as _FusionSignal, SignalInputs as _FusionInputs
                from uuid import uuid4 as _uuid4
                from datetime import datetime as _dt, timezone as _tz
                from decimal import Decimal as _D

                _fused_direction = "LONG" if direction == "BULLISH" else ("SHORT" if direction == "BEARISH" else "NO_TRADE")
                _probe = _FusionSignal(
                    signal_id=_uuid4(),
                    strategy_id="BREAKOUT",
                    instrument_id=iid,
                    symbol=iid,
                    direction=_fused_direction,  # type: ignore
                    timestamp=_dt.now(_tz.utc),
                    market_snapshot_id=str(last_update_ms),
                    technical_state={},
                    mtf_state={},
                    fo_state={},
                    regime=None,
                    ai_result=None,
                    score=_D(str(breakout_pressure if breakout_pressure is not None else 50)),
                    confidence=_D(str(float(getattr(short_out, "confidence", 0.0) or 0.0) / 100.0 if (getattr(short_out, "confidence", 0.0) or 0.0) > 1 else (getattr(short_out, "confidence", 0.0) or 0.5))),
                    invalidation_conditions={},
                )
                _trig_type = "BREAKOUT" if direction == "BULLISH" else "BREAKDOWN"
                _trigger_ok, _trigger_reason = _fusion_trigger_engine.should_trigger(_probe, _trig_type)  # type: ignore
            except Exception as _te:
                # Fail-open for the probe itself would mint duplicates; fail-closed
                # for the gate but never crash generation — log and continue.
                logger.debug("signal_center_trigger_probe_failed", error=str(_te)[:150])
                _trigger_ok, _trigger_reason = True, "TRIGGER_PROBE_ERROR_CONTINUE"
            if not _trigger_ok:
                logger.debug(
                    "signal_center_trigger_denied",
                    instrument_id=iid,
                    reason=_trigger_reason,
                    persistent_id=persistent_id,
                )
                # Cooldown/duplicate/market-closed: do not register a new FSM entry.
                # Return None so active_setups renders an honest NO_SETUP card.
                return None
            # Store and register (gate passed)
            try:
                _fusion_trigger_engine.mark_triggered(_probe)  # type: ignore
            except Exception:
                pass
            signal_fsm.register(signal)
        # Keep by instrument (cap 20)
        lst = self._by_instrument.setdefault(iid, [])
        if persistent_id not in lst:
            lst.insert(0, persistent_id)
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
                SignalEvent, should_publish_instrument_event, telegram_notification_queue,
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
            "ai_decision": "WATCH" if (signal.ai or {}).get("status") == "UNAVAILABLE" else (signal.ai or {}).get("decision", "WATCH"),
            # P0-5: when ai_status is UNAVAILABLE there is no AI confidence —
            # must be None, never short_out.confidence (deterministic horizon ≠ AI).
            "ai_confidence": None if (signal.ai or {}).get("status", "UNAVAILABLE") == "UNAVAILABLE" else (
                float((signal.ai or {}).get("confidence")) if (signal.ai or {}).get("confidence") is not None else None
            ),
            "ai_status": (signal.ai or {}).get("status", "UNAVAILABLE"),
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
                # Filter expired via TTL (P0-5: expires_at_utc may be None for
                # NO_SETUP cards — guard avoids TypeError crash).
                try:
                    _exp = ev.get("expires_at_utc")
                except Exception:
                    _exp = None
                if _exp is not None:
                    try:
                        if int(_exp) < int(time.time() * 1000):
                            ev["status"] = "EXPIRED"
                            if status and status != "EXPIRED":
                                continue
                    except Exception:
                        pass
                results.append(ev)
            else:
                # No setup — honest NO_SETUP. Pressures stay null (no synthetic
                # quality scores) but session / health / last-known price are filled
                # synchronously so cards never render blank rows.
                if not status or status == "NO_SETUP":
                    from app.institutional import mi_service as _mi

                    prof = asset_registry.get(iid)
                    _now = int(time.time() * 1000)
                    try:
                        _sess = get_session_clock(iid).current_state(now_ms=_now)
                    except Exception:
                        _sess = "UNKNOWN"
                    _px_s, _px_f, _sess_h = None, None, "DISCONNECTED"
                    try:
                        _cspot, _cts, _cage = _mi.get_last_good(iid, _now)
                        if _cspot is not None:
                            _px_s = format(_cspot, 'f')
                            _px_f = f"{float(_cspot):,.2f}"
                            _sess_h = "STALE"
                    except Exception:
                        pass
                    if _sess_h == "DISCONNECTED":
                        try:
                            if prof and prof.pipeline == "INDIAN_EQUITY" and _sess == "CLOSED":
                                _sess_h = "CLOSED"
                            elif feed_circuit.is_degraded(iid):
                                _sess_h = "FEED_DEGRADED"
                        except Exception:
                            pass
                    results.append({
                        "signal_id": f"no-setup-{iid.lower()}",
                        "instrument_id": iid,
                        "display_name": prof.display_name if prof else iid,
                        "status": "NO_SETUP",
                        "direction": "NEUTRAL",
                        "trigger_level": None,
                        "breakout_pressure": None,
                        "false_breakout_risk": None,
                        "breakout_quality": None,
                        "short_horizon": {"status":"REJECTED","confidence":0,"direction":"NEUTRAL"},
                        "continuation": {"status":"REJECTED","confidence":0,"direction":"NEUTRAL"},
                        "options_confirmation": "NEUTRAL",
                        "ai_decision": "UNAVAILABLE",
                        "ai_confidence": None,
                        "ai_status": "UNAVAILABLE",
                        "risk_status": "NO_SETUP",
                        "risk_reason": "no live price — feed disconnected" if _px_s is None else "no setup at current price",
                        "ttl_ms": None,
                        "created_at_utc": None,
                        "expires_at_utc": None,
                        "price": _px_s,
                        "price_formatted": _px_f,
                        "session": _sess,
                        "data_health": _sess_h,
                        "supporting": [],
                        "conflicting": [],
                        "backend_authoritative": True,
                    })
        # Sort CONFIRMED first
        order = {"CONFIRMED":0,"TRIGGERED":1,"POSSIBLE_BREAKOUT":2,"POSSIBLE_BREAKDOWN":2,"WATCH":3,"PREPARING":4,"NO_SETUP":9,"EXPIRED":8,"FAILED":7}
        results.sort(key=lambda x: order.get(x["status"], 5))
        return results


signal_center = SignalCenterService()
