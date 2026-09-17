"""
Unified Feed Health Monitor
Evaluates the full market-data pipeline:
1. Exchange Calendar Session (NSE 09:15 - 15:30 IST)
2. Broker Authentication & Token Usability (FYERS)
3. Central Spot Feed Ticks (NIFTY, BANKNIFTY, SENSEX)
4. Option Chain Freshness & Mark Provenance (Live Bids/Asks)

Rule: "No data is better than fake data."
Status is 'LIVE' ONLY when the market is open, the broker is authenticated,
spot ticks are actively streaming (< 15s age), and option contracts are actively priced.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Literal
import structlog

logger = structlog.get_logger()

FeedStatus = Literal[
    "LIVE",
    "SYNCING",
    "STALE",
    "CHAIN_UNAVAILABLE",
    "DOWN",
    "CLOSED",
    "AUTH_REQUIRED",
]

# 1s shared cache + 3-poll hysteresis: flapping ticks must not flap status.
_TELEMETRY_CACHE: dict[str, Any] = {"ts_ns": 0, "payload": None}
_TELEMETRY_TTL_NS: int = 1_000_000_000
_HYSTERESIS_N: int = 3
_last_raw: str | None = None
_stable_status: str | None = None
_stable_count: int = 0


class FeedHealthMonitor:
    def get_telemetry(self, _use_cache: bool = True) -> dict[str, Any]:
        """Compute the current honest feed health across all subsystems.

        Shared 1s cache + 3-poll hysteresis: identical calls within 1s return
        the cached payload; raw status flaps are only published after 3
        consecutive polls agree.
        """
        global _last_raw, _stable_status, _stable_count
        now_ns = time.monotonic_ns()
        if _use_cache and _TELEMETRY_CACHE.get("payload") is not None:
            if now_ns - int(_TELEMETRY_CACHE.get("ts_ns") or 0) < _TELEMETRY_TTL_NS:
                return dict(_TELEMETRY_CACHE["payload"])
        payload = self._compute_telemetry()
        raw = str(payload.get("status") or "")
        # Hysteresis: require 3 consecutive identical raw statuses before
        # publishing a change (prevents tick-edge flapping LIVE<->STALE).
        if _stable_status is None:
            _stable_status = raw
            _stable_count = 1
            _last_raw = raw
        elif raw == _last_raw:
            _stable_count += 1
            if _stable_count >= _HYSTERESIS_N:
                _stable_status = raw
        else:
            _last_raw = raw
            _stable_count = 1
            # Hold previous stable status until confirmed
            payload = dict(payload)
            payload["status"] = _stable_status  # type: ignore[assignment]
            payload["is_healthy_for_trading"] = (_stable_status == "LIVE")
            payload["hysteresis_pending"] = raw
        _TELEMETRY_CACHE["ts_ns"] = now_ns
        _TELEMETRY_CACHE["payload"] = dict(payload)
        # Wire auto-kill: DOWN or STALE>60s activates the global kill switch.
        try:
            from app.signals.safety.kill_switch import kill_switch
            st = str(payload.get("status") or "")
            age = None
            try:
                age = payload.get("spot_feed", {}).get("tick_age_seconds")
            except Exception:
                age = None
            kill_switch.auto_activate_from_monitor(st, age)
        except Exception:
            pass
        return payload

    def _compute_telemetry(self) -> dict[str, Any]:
        from app.services.calendar_service import calendar_service
        from app.services.central_feed import central_feed
        from app.core.broker_runtime import get_config, is_usable_access_token
        from app.signals.live_contract_cache import live_contract_cache
        from app.signals.option_marks import option_mark_registry

        # 1. Market Calendar Session
        mkt_perm = calendar_service.can_trade_now()
        is_market_open = bool(mkt_perm.allowed)
        session_reason = mkt_perm.reason
        timestamp_ist = mkt_perm.timestamp_ist

        # 2. Broker Config & Token Status
        cfg = get_config()
        broker_app_id = bool(cfg.credentials.get("app_id"))
        raw_token = cfg.credentials.get("access_token") or ""
        usable_token = False
        try:
            usable_token = is_usable_access_token(raw_token)
        except Exception:
            usable_token = bool(raw_token)

        token_status = (
            "present" if usable_token else ("placeholder" if raw_token else "missing")
        )

        # 3. Spot Feed Health (CentralMarketDataFeed)
        cf_health = central_feed.get_feed_health()
        last_tick_at = cf_health.get("last_tick_at")
        tick_age_s = cf_health.get("tick_age_seconds")
        is_ticking = bool(cf_health.get("is_ticking", False))
        symbols_cached = int(cf_health.get("symbols_cached", 0))

        # 4. Option Chain & Marks Health
        chain_stats = live_contract_cache.stats()
        strikes = int(chain_stats.get("strikes", 0) or 0)
        chain_age_ms = int(chain_stats.get("age_ms", -1))
        chain_status = (
            "FRESH"
            if strikes and 0 <= chain_age_ms <= 180_000
            else ("STALE" if strikes else "UNAVAILABLE")
        )

        mark_stats = option_mark_registry.stats()
        by_source = dict(mark_stats.get("by_source", {}) or {})
        option_marks = int(mark_stats.get("marks", 0) or 0)
        chain_mark_status = (
            "LIVE"
            if (by_source.get("CHAIN_BIDASK", 0) + by_source.get("CHAIN_LTP", 0)) > 0
            else ("MODEL_ONLY" if by_source.get("MODEL_BLACK76", 0) > 0 else "NONE")
        )

        # 5. Composite Honest Status Derivation
        status: FeedStatus = "CLOSED"
        message: str = "Market session closed"
        display_label: str = "CLOSED · NSE 15:30 IST"
        display_tone: str = "idle"

        if not is_market_open:
            status = "CLOSED"
            message = f"Exchange closed ({session_reason}). Regular trading hours 09:15 - 15:30 IST."
            display_label = f"CLOSED · {session_reason.replace('_', ' ').title()}"
            display_tone = "idle"
        elif not usable_token:
            status = "AUTH_REQUIRED"
            message = "Market is open, but FYERS token is missing or expired. Re-authentication required."
            display_label = "AUTH REQUIRED · FYERS"
            display_tone = "down"
        elif not cf_health.get("is_running", False):
            status = "DOWN"
            message = "Central market data worker is stopped."
            display_label = "FEED DOWN · WORKER STOPPED"
            display_tone = "down"
        elif tick_age_s is None or tick_age_s > 60:
            status = "DOWN"
            age_txt = f"{int(tick_age_s)}s ago" if tick_age_s is not None else "no ticks"
            message = f"Market is open, but broker feed has produced no ticks ({age_txt})."
            display_label = f"FEED DOWN · {age_txt.upper()}"
            display_tone = "down"
        elif tick_age_s > 15:
            status = "STALE"
            message = f"Market feed delayed — last broker tick was {int(tick_age_s)}s ago."
            display_label = f"STALE · {int(tick_age_s)}S AGO"
            display_tone = "warn"
        elif strikes == 0 or chain_status == "UNAVAILABLE":
            status = "CHAIN_UNAVAILABLE"
            message = "Spot feed is ticking, but option chain is unavailable. Options trading is halted."
            display_label = "NO OPTION CHAIN"
            display_tone = "warn"
        elif chain_status == "STALE":
            status = "STALE"
            message = "Option chain quotes are older than 3 minutes."
            display_label = "CHAIN STALE"
            display_tone = "warn"
        elif chain_mark_status == "MODEL_ONLY":
            # MODEL_ONLY is never LIVE: a Black-76 estimate is not a market.
            status = "STALE"
            message = "Option marks are model-only (no live chain bid/ask). Trading halted."
            display_label = "STALE · MODEL ONLY"
            display_tone = "warn"
        else:
            status = "LIVE"
            age_int = max(0, int(tick_age_s)) if tick_age_s is not None else 0
            message = f"Live market feed active — broker ticks {age_int}s ago, {strikes} strikes priced."
            display_label = f"LIVE · {age_int}S AGO"
            display_tone = "on"

        is_healthy_for_trading = status == "LIVE"

        return {
            "status": status,
            "is_healthy_for_trading": is_healthy_for_trading,
            "display_label": display_label,
            "display_tone": display_tone,
            "message": message,
            "market_session": {
                "is_open": is_market_open,
                "reason": session_reason,
                "session": mkt_perm.session,
                "timestamp_ist": timestamp_ist.isoformat() if timestamp_ist else None,
                "market_open_ist": mkt_perm.market_open.isoformat() if mkt_perm.market_open else None,
                "market_close_ist": mkt_perm.market_close.isoformat() if mkt_perm.market_close else None,
            },
            "broker": {
                "provider": "fyers",
                "configured": broker_app_id,
                "token_status": token_status,
                "token_usable": usable_token,
            },
            "spot_feed": {
                "is_running": cf_health.get("is_running", False),
                "is_ticking": is_ticking,
                "last_tick_at": last_tick_at,
                "tick_age_seconds": tick_age_s,
                "symbols_cached": symbols_cached,
            },
            "option_chain": {
                "chain_status": chain_status,
                "strikes": strikes,
                "chain_age_ms": chain_age_ms,
                "option_marks": option_marks,
                "chain_mark_status": chain_mark_status,
                "by_source": by_source,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


feed_health_monitor = FeedHealthMonitor()
