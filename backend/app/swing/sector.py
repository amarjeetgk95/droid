"""
Sector Relative Strength Engine for Swing Trading (v5.0 §10).
Classifies sectors into:
  - LEADING
  - IMPROVING
  - NEUTRAL
  - WEAKENING
  - LAGGING
Calculates 20-day returns and relative outperformance vs NIFTY.
"""
from __future__ import annotations

from typing import Any
from app.swing.models import SectorClassification, SectorStatusType
from app.swing.universe import SWING_EQUITY_UNIVERSE, get_all_sectors


def compute_sector_strengths(
    stock_candles_map: dict[str, list[dict[str, Any]]],
    nifty_return_20d: float = 0.0,
) -> dict[str, SectorClassification]:
    """
    Computes sector momentum by aggregating 20-day returns of constituent stocks.
    stock_candles_map: dict symbol -> list of daily candles.
    """
    sector_stocks: dict[str, list[tuple[str, float]]] = {}
    for symbol, candles in stock_candles_map.items():
        item = SWING_EQUITY_UNIVERSE.get(symbol.upper())
        if not item or not candles or len(candles) < 20:
            continue

        c_now = float(candles[-1]["close"])
        c_20 = float(candles[-20]["close"])
        ret_20d = ((c_now - c_20) / c_20) * 100.0 if c_20 > 0 else 0.0

        sector_stocks.setdefault(item.sector, []).append((symbol, ret_20d))

    results: dict[str, SectorClassification] = {}
    all_sectors = get_all_sectors()

    for sec in all_sectors:
        stocks = sector_stocks.get(sec, [])
        if not stocks:
            results[sec] = SectorClassification(
                sector=sec,
                trend="NEUTRAL",
                relative_strength=50.0,
                return_20d_pct=0.0,
                leading_stocks=[],
            )
            continue

        # Sort constituent stocks by 20d return
        stocks.sort(key=lambda x: x[1], reverse=True)
        avg_sec_ret = sum(s[1] for s in stocks) / len(stocks)
        top_stocks = [s[0] for s in stocks[:3]]

        # Relative strength vs Nifty (normalized 0-100)
        excess_ret = avg_sec_ret - nifty_return_20d
        # e.g. +5% excess -> RS 75, -5% excess -> RS 25
        rs = max(0.0, min(100.0, 50.0 + excess_ret * 5.0))

        status: SectorStatusType
        if excess_ret >= 3.0 and avg_sec_ret > 0:
            status = "LEADING"
        elif excess_ret >= 0.5:
            status = "IMPROVING"
        elif excess_ret <= -3.0:
            status = "LAGGING"
        elif excess_ret <= -0.5:
            status = "WEAKENING"
        else:
            status = "NEUTRAL"

        results[sec] = SectorClassification(
            sector=sec,
            trend=status,
            relative_strength=round(rs, 1),
            return_20d_pct=round(avg_sec_ret, 2),
            leading_stocks=top_stocks,
        )

    return results
