"""
Sector / Asset Relative Strength Engine for Swing Trading (v6.0 Options Overhaul).
Provides relative strength context across index assets (NIFTY, BANKNIFTY, SENSEX).
"""
from __future__ import annotations

from typing import Any
from app.swing.models import SectorClassification, SectorStatusType
from app.swing.universe import SWING_OPTIONS_UNIVERSE, get_all_sectors


def compute_sector_strengths(
    stock_candles_map: dict[str, list[dict[str, Any]]],
    nifty_return_20d: float = 0.0,
) -> dict[str, SectorClassification]:
    """
    Computes asset momentum across indices vs benchmark.
    """
    results: dict[str, SectorClassification] = {}
    for symbol, candles in stock_candles_map.items():
        if not candles or len(candles) < 20:
            continue
        c_now = float(candles[-1]["close"])
        c_20 = float(candles[-20]["close"])
        ret_20d = ((c_now - c_20) / c_20) * 100.0 if c_20 > 0 else 0.0
        excess_ret = ret_20d - nifty_return_20d
        rs = max(0.0, min(100.0, 50.0 + excess_ret * 5.0))

        status: SectorStatusType = "NEUTRAL"
        if excess_ret >= 2.0:
            status = "LEADING"
        elif excess_ret >= 0.5:
            status = "IMPROVING"
        elif excess_ret <= -2.0:
            status = "LAGGING"
        elif excess_ret <= -0.5:
            status = "WEAKENING"

        results[symbol] = SectorClassification(
            sector="INDEX",
            trend=status,
            relative_strength=round(rs, 1),
            return_20d_pct=round(ret_20d, 2),
            leading_stocks=[symbol],
        )

    if not results:
        results["INDEX"] = SectorClassification(
            sector="INDEX",
            trend="NEUTRAL",
            relative_strength=50.0,
            return_20d_pct=0.0,
            leading_stocks=[],
        )

    return results

