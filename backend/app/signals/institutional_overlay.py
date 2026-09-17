"""Institutional overlay: regime-conditioned flow interpretation + divergence guard.

Pure functions (no I/O) so they are unit-testable and auditable.

Design (honest, capped):
- Flow snapshot is DAILY (T+1 available). It must NEVER flip an intraday
  signal by itself. Max adjustment is +-5 fused points, applied inside
  confluence.fuse() AFTER the linear blend, and only when pit_ok and
  fno not degraded-beyond-use.
- Regime conditioning: same FII print means different things:
    TREND_DOWN + FII selling (z<0) + futures net short -> bearish confirm (+ toward SHORT)
    RANGE/COMPRESSION + same selling -> muted (x0.25), never full bearish
    VOLATILE/EVENT -> capped further, needs stronger evidence
- P1: scalp flow weight is 0 (intraday tape owns scalps); flow older than 24h
  carries 0 weight. Buildup is read off chain OI/PCR/wall distance — never
  string-matched labels. 0DTE divergence SUPPRESSES (no new risk into pin
  noise), longer-dated divergence forces VALIDATED (watch-only).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple


def _regime_family(regime: Any) -> str:
    r = str(regime or "").upper()
    if "TREND_DOWN" in r or "BEAR" in r:
        return "TREND_DOWN"
    if "TREND_UP" in r or "BULL" in r:
        return "TREND_UP"
    if "VOLAT" in r or "EVENT" in r or "HIGH_VOL" in r:
        return "VOLATILE"
    if "COMPRESS" in r or "RANGE" in r or "SIDEWAYS" in r:
        return "RANGE"
    if "TREND" in r:
        return "TREND"
    return "UNKNOWN"


def _flow_age_hours(flow: Any, now: Any = None) -> float | None:
    """Hours since the flow snapshot event (None when unparseable)."""
    try:
        evt = getattr(flow, "event_date", None)
        if evt is None:
            return None
        ref = now or datetime.now(timezone.utc)
        if isinstance(evt, (int, float)):
            # epoch ms or s?
            ts = float(evt)
            evt_dt = datetime.fromtimestamp(ts / 1000.0 if ts > 1e12 else ts, tz=timezone.utc)
        elif isinstance(evt, datetime):
            evt_dt = evt if evt.tzinfo else evt.replace(tzinfo=timezone.utc)
        elif isinstance(evt, str):
            evt_dt = datetime.fromisoformat(evt.replace("Z", "+00:00"))
        else:
            return None
        return max(0.0, (ref - evt_dt).total_seconds() / 3600.0)
    except Exception:
        return None


def _chain_buildup_state(fno: Dict[str, Any] | None) -> Dict[str, Any]:
    """Quantitative buildup off chain OI/PCR/wall distance (no string match).

    Returns {put_writing, call_writing, pcr_oi, call_wall_dist_pct,
    put_wall_dist_pct, oi_imbalance} where walls are max-OI strikes when the
    fno snapshot carries them.
    """
    fno = fno or {}
    out: Dict[str, Any] = {
        "put_writing": False, "call_writing": False, "short_covering": False,
        "pcr_oi": None, "call_wall_dist_pct": None, "put_wall_dist_pct": None,
        "oi_imbalance": 0.0,
    }
    try:
        def _f(key: str, default: Any = None) -> Any:
            for k in (key, key.lower(), key.upper()):
                if k in fno and fno[k] is not None:
                    return fno[k]
            return default

        call_oi = _f("total_call_oi")
        put_oi = _f("total_put_oi")
        pcr = _f("pcr_oi", _f("pcr"))
        try:
            if pcr is not None:
                out["pcr_oi"] = float(pcr)
            elif call_oi and put_oi and float(call_oi) > 0:
                out["pcr_oi"] = float(put_oi) / float(call_oi)
        except Exception:
            pass
        try:
            if call_oi is not None and put_oi is not None:
                tot = float(call_oi) + float(put_oi)
                if tot > 0:
                    out["oi_imbalance"] = (float(put_oi) - float(call_oi)) / tot
        except Exception:
            pass
        # Walls: explicit max-OI strikes when provided.
        try:
            spot = _f("spot", _f("spot_price"))
            cw = _f("call_wall_strike", _f("max_call_oi_strike"))
            pw = _f("put_wall_strike", _f("max_put_oi_strike"))
            if spot and cw:
                out["call_wall_dist_pct"] = (float(cw) - float(spot)) / float(spot) * 100.0
            if spot and pw:
                out["put_wall_dist_pct"] = (float(spot) - float(pw)) / float(spot) * 100.0
        except Exception:
            pass
        # Writing regimes off PCR + imbalance (not label substrings).
        try:
            p = out["pcr_oi"]
            imb = out["oi_imbalance"]
            if p is not None and float(p) >= 1.2 and imb > 0.05:
                out["put_writing"] = True
            if p is not None and float(p) <= 0.8 and imb < -0.05:
                out["call_writing"] = True
            chg = _f("oi_change_pct", _f("oi_change"))
            px = _f("price_change_pct", _f("price_change"))
            if chg is not None and px is not None and float(chg) < 0 and abs(float(px)) > 0.2:
                out["short_covering"] = True
        except Exception:
            pass
    except Exception:
        pass
    return out


def compute_institutional_adjustment(
    direction: str,
    regime: Any,
    flow: Any,
    fno: Dict[str, Any] | None = None,
    participation: Dict[str, Any] | None = None,
    is_scalp: bool = False,
    now: Any = None,
) -> Tuple[float, Dict[str, Any]]:
    """Return (delta_points in [-5,+5], info dict).

    Positive delta = supports candidate direction; negative = contradicts.
    Downgrade flag forces VALIDATED when divergence is detected; on 0DTE the
    same divergence SUPPRESSES instead (info["action"]="SUPPRESS").
    Scalp or >24h-stale flow carries zero weight.
    """
    info: Dict[str, Any] = {
        "applied": False,
        "delta": 0.0,
        "reasons": [],
        "downgrade_to_validated": False,
        "suppress": False,
        "action": "NONE",
        "regime_family": _regime_family(regime),
        "flow_event_date": None,
        "flow_age_hours": None,
        "weight": 0.0,
    }
    if flow is None or getattr(flow, "pit_ok", False) is not True:
        info["reasons"].append("no-pit-safe-flow")
        return 0.0, info
    info["flow_event_date"] = getattr(flow, "event_date", None)

    # P1: scalp tape owns scalps; stale daily prints carry no weight.
    age_h = _flow_age_hours(flow, now)
    info["flow_age_hours"] = age_h
    if is_scalp:
        info["reasons"].append("scalp-zero-weight")
        return 0.0, info
    if age_h is not None and age_h > 24.0:
        info["reasons"].append(f"flow-stale-{age_h:.1f}h-zero-weight")
        return 0.0, info

    is_call = "CALL" in str(direction or "").upper()
    fam = info["regime_family"]
    fno = fno or {}
    participation = participation or {}

    fii_z = getattr(flow, "fii_cash_5d_z", None)
    dii_z = getattr(flow, "dii_cash_5d_z", None)
    fii_net = getattr(flow, "fii_fut_net", None)
    lsr = getattr(flow, "fii_lsr", None)

    # Base institutional bias from daily flow: +1 bullish .. -1 bearish.
    bias = 0.0
    if isinstance(fii_z, (int, float)):
        bias += max(-1.0, min(1.0, float(fii_z) / 2.0)) * 0.6
    if isinstance(dii_z, (int, float)):
        bias += max(-1.0, min(1.0, float(dii_z) / 2.0)) * 0.4
    if isinstance(lsr, (int, float)):
        try:
            if float(lsr) > 1.05:
                bias += 0.25
            elif float(lsr) < 0.95:
                bias -= 0.25
        except Exception:
            pass
    if isinstance(fii_net, (int, float)):
        try:
            if float(fii_net) > 0:
                bias += 0.15
            elif float(fii_net) < 0:
                bias -= 0.15
        except Exception:
            pass
    bias = max(-1.0, min(1.0, bias))

    # Alignment with candidate: +1 aligned, -1 opposed.
    align = 0.0
    if bias > 0.15 and is_call:
        align = 1.0
    elif bias < -0.15 and not is_call:
        align = 1.0
    elif bias > 0.15 and not is_call:
        align = -1.0
    elif bias < -0.15 and is_call:
        align = -1.0
    else:
        info["reasons"].append(f"flow-neutral-bias-{bias:.2f}")
        return 0.0, info

    # Regime-conditioned weight (same print, different meaning).
    if fam in ("TREND_DOWN", "TREND_UP", "TREND"):
        w = 5.0
    elif fam == "RANGE":
        w = 1.25  # muted in sideways: 5 * 0.25
    elif fam == "VOLATILE":
        w = 2.5
    else:
        w = 2.0
    # Expiry/DTE guard: options weight halves on DTE<=1 (mirror forecast gate).
    is_0dte = False
    try:
        dte = fno.get("distance_to_expiry_days", fno.get("days_to_expiry"))
        if dte is not None and float(dte) <= 1.0:
            w *= 0.5
            is_0dte = float(dte) <= 0.5
            info["reasons"].append("dte<=1-halved")
    except Exception:
        pass
    info["weight"] = w

    delta = round(align * w, 2)
    delta = max(-5.0, min(5.0, delta))
    info["applied"] = True
    info["delta"] = delta
    info["reasons"].append(f"flow-bias-{bias:.2f}-align-{align:.0f}-regime-{fam}-w-{w}")

    # Divergence guard: institutional selling BUT intraday structure shows
    # absorption (support hold + chain put-writing / short-covering).
    # Buildup comes from CHAIN OI/PCR/wall distance — never label substrings.
    try:
        chain = _chain_buildup_state(fno)
        info["chain_buildup"] = chain
        part = participation or {}
        support_hold = bool(part.get("support_hold", False))
        put_writing = bool(chain.get("put_writing")) or bool(part.get("put_writing", False))
        call_writing = bool(chain.get("call_writing"))
        short_cover = bool(chain.get("short_covering"))
        # Legacy label fallback only when the chain snapshot is absent.
        chain_absent = (chain.get("pcr_oi") is None and not put_writing and not call_writing and not short_cover)
        if chain_absent:
            try:
                pl = str(part.get("label", part.get("positioning", ""))).upper()
                if "SHORT_COVER" in pl or " COVER" in pl:
                    short_cover = True
            except Exception:
                pass
        fii_selling = isinstance(fii_z, (int, float)) and float(fii_z) < -0.5
        fii_buying = isinstance(fii_z, (int, float)) and float(fii_z) > 0.5
        div_bear = (not is_call) and fii_selling and (support_hold or short_cover or put_writing)
        div_bull = is_call and fii_buying and (support_hold is False and call_writing)
        if div_bear or div_bull:
            tag = "bearish-divergence-absorption" if div_bear else "bullish-divergence-supply"
            if is_0dte:
                # 0DTE: pin noise — do not trade into divergence at all.
                info["suppress"] = True
                info["action"] = "SUPPRESS"
                info["applied"] = False
                info["delta"] = 0.0
                info["reasons"].append(f"{tag}-0DTE-SUPPRESS")
                return 0.0, info
            info["downgrade_to_validated"] = True
            info["action"] = "VALIDATED"
            info["reasons"].append(f"{tag}-force-VALIDATED")
    except Exception as e:
        info["reasons"].append(f"divergence-check-skipped:{e}")

    return delta, info
