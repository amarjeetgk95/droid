"""
Curated Swing Trading Universe (v6.0 Options Overhaul).
Index options universe: NIFTY, BANKNIFTY, SENSEX.
"""
from __future__ import annotations
from app.swing.models import UniverseItem

SWING_OPTIONS_UNIVERSE: dict[str, UniverseItem] = {
    "NIFTY": UniverseItem(
        symbol="NIFTY",
        display_name="NIFTY 50",
        exchange="NSE",
        fyers_symbol="NSE:NIFTY50-INDEX",
        fno_eligible=True,
        lot_size=75,
        strike_interval=50.0,
        tick_size=0.05,
    ),
    "BANKNIFTY": UniverseItem(
        symbol="BANKNIFTY",
        display_name="NIFTY Bank",
        exchange="NSE",
        fyers_symbol="NSE:NIFTYBANK-INDEX",
        fno_eligible=True,
        lot_size=30,
        strike_interval=100.0,
        tick_size=0.05,
    ),
    "SENSEX": UniverseItem(
        symbol="SENSEX",
        display_name="BSE SENSEX",
        exchange="BSE",
        fyers_symbol="BSE:SENSEX-INDEX",
        fno_eligible=True,
        lot_size=20,
        strike_interval=100.0,
        tick_size=0.05,
    ),
}

BENCHMARKS: dict[str, UniverseItem] = {"NIFTY": SWING_OPTIONS_UNIVERSE["NIFTY"]}
ALL_SWING_UNIVERSE: dict[str, UniverseItem] = SWING_OPTIONS_UNIVERSE


def get_swing_universe() -> list[UniverseItem]:
    """Return all active items in the swing options universe."""
    return list(SWING_OPTIONS_UNIVERSE.values())


def get_all_universe() -> list[UniverseItem]:
    """Return all universe items including benchmarks."""
    return list(ALL_SWING_UNIVERSE.values())


def get_universe_item(symbol: str) -> UniverseItem | None:
    """Case-insensitive lookup of universe item."""
    if not symbol:
        return None
    cleaned = (
        symbol.strip()
        .upper()
        .replace("NSE:", "")
        .replace("BSE:", "")
        .replace("-EQ", "")
        .replace("-INDEX", "")
        .replace("50", "")
    )
    if cleaned in ALL_SWING_UNIVERSE:
        return ALL_SWING_UNIVERSE[cleaned]
    # Fallback partial matching
    for k, item in ALL_SWING_UNIVERSE.items():
        if k in cleaned or cleaned in k:
            return item
    return None


def get_all_sectors() -> list[str]:
    """Return index categories."""
    return ["INDEX"]


def get_universe_by_sector(sector: str) -> list[UniverseItem]:
    """Filter by sector/category."""
    return list(SWING_OPTIONS_UNIVERSE.values())

