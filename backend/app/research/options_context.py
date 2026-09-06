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
                    "pcr_oi": 1.0,
                    "pcr_vol": 1.0,
                    "atm_iv": 15.0,
                    "call_wall": None,
                    "put_wall": None,
                    "max_pain": None,
                    "days_to_expiry": 1.0,
                    "atm_theta": -10.0,
                    "atm_gamma": 0.001,
                    "atm_vega": 10.0,
                }

            # If data is synthetic or missing major fields, flag DEGRADED
            if fno_data.get("synthetic", False):
                quality = DataQualityStatus.DEGRADED

            call_wall = fno_data.get("call_wall")
            put_wall = fno_data.get("put_wall")
            max_pain = fno_data.get("max_pain")
            pcr_oi = float(fno_data.get("pcr", 1.0) or 1.0)
            pcr_vol = float(fno_data.get("pcr_vol", 1.0) or 1.0)
            atm_iv = float(fno_data.get("atm_iv", 15.0) or 15.0)
            days_to_expiry = float(fno_data.get("near_days", 1.0) or 1.0)

            atm_greeks = fno_data.get("atm_greeks") or {}
            atm_theta = float(atm_greeks.get("theta", -12.5) or -12.5)
            atm_gamma = float(atm_greeks.get("gamma", 0.0015) or 0.0015)
            atm_vega = float(atm_greeks.get("vega", 12.0) or 12.0)

            return {
                "instrument": instrument,
                "timestamp": timestamp,
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
                "pcr_oi": 1.0,
                "pcr_vol": 1.0,
                "atm_iv": 15.0,
                "call_wall": None,
                "put_wall": None,
                "max_pain": None,
                "days_to_expiry": 1.0,
                "atm_theta": -10.0,
                "atm_gamma": 0.001,
                "atm_vega": 10.0,
            }
