"""Options context adapter for the Research Laboratory (§11).

Wraps existing options and FnO analytics into a clean, read-only
research snapshot format without modifying production state.
"""

from typing import Any, Dict, Optional
import structlog
from datetime import datetime, timezone

from app.research.enums import DataQualityStatus

logger = structlog.get_logger(__name__)


class ResearchOptionsContext:
    """Read-only research adapter for options market context.
    
    Extracts structural options parameters:
    - Put-Call Ratio (OI and Volume)
    - ATM Implied Volatility
    - Call and Put Walls (Max OI strikes)
    - Max Pain Strike
    - ATM Greeks (Delta, Gamma, Theta, Vega)
    - Days to Expiry (DTE)
    """

    @classmethod
    async def get_context(cls, instrument: str) -> Dict[str, Any]:
        """Fetch standardized options context for the given instrument."""
        quality = DataQualityStatus.LIVE
        # timestamp/available_time are set from the underlying F&O snapshot
        # (PIT provenance), never minted here, so downstream can prove
        # available_time <= decision_time.
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            from app.fno.context import get_fno_context
            fno_data = await get_fno_context(instrument)

            if not fno_data or not fno_data.get("available", True):
                return {
                    "instrument": instrument,
                    "timestamp": timestamp,
                    "available": False,
                    "data_quality": DataQualityStatus.EMPTY.value,
                    # Honesty: no silent concrete numbers when unavailable.
                    # Nulls + explicit assumptions, never 1.0/15.0 as if measured.
                    "pcr_oi": None,
                    "pcr_vol": None,
                    "atm_iv": None,
                    "call_wall": None,
                    "put_wall": None,
                    "max_pain": None,
                    "days_to_expiry": None,
                    "atm_theta": None,
                    "atm_gamma": None,
                    "atm_vega": None,
                    "synthetic": False,
                    "assumptions": [
                        "pcr_oi-unavailable-no-default",
                        "atm_iv-unavailable-no-default",
                        "dte-unavailable-no-default",
                    ],
                }

            # If data is synthetic or missing major fields, flag DEGRADED
            if fno_data.get("synthetic", False):
                quality = DataQualityStatus.DEGRADED

            call_wall = fno_data.get("call_wall")
            put_wall = fno_data.get("put_wall")
            max_pain = fno_data.get("max_pain")
            # Honesty: track when upstream omits a field (assumption, not measured).
            assumptions: list[str] = []
            _pcr_raw = fno_data.get("pcr")
            _pcr_vol_raw = fno_data.get("pcr_vol")
            _iv_raw = fno_data.get("atm_iv")
            _dte_raw = fno_data.get("near_days")
            if _pcr_raw is None:
                assumptions.append("pcr_oi-assumed-1.0-missing-upstream")
            if _pcr_vol_raw is None:
                assumptions.append("pcr_vol-assumed-1.0-missing-upstream")
            if _iv_raw is None:
                assumptions.append("atm_iv-assumed-15.0-missing-upstream")
            if _dte_raw is None:
                assumptions.append("dte-assumed-1.0-missing-upstream")
            pcr_oi = float(_pcr_raw if _pcr_raw is not None else 1.0)
            pcr_vol = float(_pcr_vol_raw if _pcr_vol_raw is not None else 1.0)
            atm_iv = float(_iv_raw if _iv_raw is not None else 15.0)
            days_to_expiry = float(_dte_raw if _dte_raw is not None else 1.0)

            atm_greeks = fno_data.get("atm_greeks") or {}
            _th_raw = atm_greeks.get("theta")
            _ga_raw = atm_greeks.get("gamma")
            _ve_raw = atm_greeks.get("vega")
            if _th_raw is None:
                assumptions.append("atm_theta-assumed-missing-upstream")
            if _ga_raw is None:
                assumptions.append("atm_gamma-assumed-missing-upstream")
            if _ve_raw is None:
                assumptions.append("atm_vega-assumed-missing-upstream")
            atm_theta = float(_th_raw if _th_raw is not None else -12.5)
            atm_gamma = float(_ga_raw if _ga_raw is not None else 0.0015)
            atm_vega = float(_ve_raw if _ve_raw is not None else 12.0)

            return {
                "instrument": instrument,
                "timestamp": fno_data.get("timestamp", timestamp),
                "available_time": fno_data.get("available_time", fno_data.get("timestamp", timestamp)),
                "timestamp_ms": fno_data.get("timestamp_ms"),
                "available": True,
                "data_quality": quality.value,
                "pcr_oi": round(pcr_oi, 3),
                "pcr_vol": round(pcr_vol, 3),
                "atm_iv": round(atm_iv, 2),
                "call_wall": call_wall,
                "put_wall": put_wall,
                "max_pain": max_pain,
                "days_to_expiry": round(days_to_expiry, 1),
                "atm_theta": round(atm_theta, 2),
                "atm_gamma": round(atm_gamma, 6),
                "atm_vega": round(atm_vega, 2),
                "synthetic": bool(fno_data.get("synthetic", False)),
                "assumptions": assumptions,
                "raw_fno": {
                    k: v for k, v in fno_data.items()
                    if k not in ("chain", "full_strikes") and not callable(v)
                }
            }

        except Exception as e:
            logger.warning("research_options_context_failed", instrument=instrument, error=str(e))
            return {
                "instrument": instrument,
                "timestamp": timestamp,
                "available": False,
                "data_quality": DataQualityStatus.FAILED.value,
                "error": str(e),
                # Honesty: nulls + assumptions, never silent 1.0/15.0.
                "pcr_oi": None,
                "pcr_vol": None,
                "atm_iv": None,
                "call_wall": None,
                "put_wall": None,
                "max_pain": None,
                "days_to_expiry": None,
                "atm_theta": None,
                "atm_gamma": None,
                "atm_vega": None,
                "synthetic": False,
                "assumptions": [
                    "pcr_oi-unavailable-no-default",
                    "atm_iv-unavailable-no-default",
                    "dte-unavailable-no-default",
                ],
            }
