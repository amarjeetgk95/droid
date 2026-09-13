"""
Curated Swing Trading Universe (v5.0).
Top 50 liquid Indian F&O equities + benchmark indices with sector mapping.
"""
from __future__ import annotations
from app.swing.models import UniverseItem

BENCHMARKS: dict[str, UniverseItem] = {
    "NIFTY": UniverseItem(
        symbol="NIFTY",
        display_name="NIFTY 50",
        sector="BENCHMARK",
        industry="Index",
        fno_eligible=True,
        lot_size=65,
        avg_volume_20d=25000000,
        avg_turnover_cr=3500.0,
        beta=1.0,
    ),
    "BANKNIFTY": UniverseItem(
        symbol="BANKNIFTY",
        display_name="NIFTY Bank",
        sector="BENCHMARK",
        industry="Index",
        fno_eligible=True,
        lot_size=30,
        avg_volume_20d=15000000,
        avg_turnover_cr=2800.0,
        beta=1.15,
    ),
}

SWING_EQUITY_UNIVERSE: dict[str, UniverseItem] = {
    # --- Banking & Financials ---
    "HDFCBANK": UniverseItem(symbol="HDFCBANK", display_name="HDFC Bank", sector="Banking", industry="Private Bank", lot_size=550, beta=1.05),
    "ICICIBANK": UniverseItem(symbol="ICICIBANK", display_name="ICICI Bank", sector="Banking", industry="Private Bank", lot_size=700, beta=1.12),
    "SBIN": UniverseItem(symbol="SBIN", display_name="State Bank of India", sector="Banking", industry="PSU Bank", lot_size=750, beta=1.20),
    "KOTAKBANK": UniverseItem(symbol="KOTAKBANK", display_name="Kotak Mahindra Bank", sector="Banking", industry="Private Bank", lot_size=400, beta=0.95),
    "AXISBANK": UniverseItem(symbol="AXISBANK", display_name="Axis Bank", sector="Banking", industry="Private Bank", lot_size=625, beta=1.15),
    "BAJFINANCE": UniverseItem(symbol="BAJFINANCE", display_name="Bajaj Finance", sector="Financials", industry="NBFC", lot_size=125, beta=1.25),
    "BAJAJFINSV": UniverseItem(symbol="BAJAJFINSV", display_name="Bajaj Finserv", sector="Financials", industry="Financial Services", lot_size=500, beta=1.20),
    "CHOLAFIN": UniverseItem(symbol="CHOLAFIN", display_name="Cholamandalam Investment", sector="Financials", industry="NBFC", lot_size=625, beta=1.10),

    # --- Information Technology ---
    "TCS": UniverseItem(symbol="TCS", display_name="Tata Consultancy Services", sector="IT", industry="IT Services", lot_size=175, beta=0.85),
    "INFY": UniverseItem(symbol="INFY", display_name="Infosys", sector="IT", industry="IT Services", lot_size=400, beta=0.92),
    "HCLTECH": UniverseItem(symbol="HCLTECH", display_name="HCL Technologies", sector="IT", industry="IT Services", lot_size=350, beta=0.90),
    "WIPRO": UniverseItem(symbol="WIPRO", display_name="Wipro", sector="IT", industry="IT Services", lot_size=1500, beta=0.95),
    "TECHM": UniverseItem(symbol="TECHM", display_name="Tech Mahindra", sector="IT", industry="IT Services", lot_size=600, beta=1.05),
    "PERSISTENT": UniverseItem(symbol="PERSISTENT", display_name="Persistent Systems", sector="IT", industry="Midcap IT", lot_size=150, beta=1.30),
    "COFORGE": UniverseItem(symbol="COFORGE", display_name="Coforge", sector="IT", industry="Midcap IT", lot_size=150, beta=1.35),

    # --- Energy, Oil & Gas ---
    "RELIANCE": UniverseItem(symbol="RELIANCE", display_name="Reliance Industries", sector="Energy", industry="Oil & Gas / Conglomerate", lot_size=250, beta=1.00),
    "ONGC": UniverseItem(symbol="ONGC", display_name="Oil & Natural Gas Corp", sector="Energy", industry="Oil Exploration", lot_size=3850, beta=1.10),
    "BPCL": UniverseItem(symbol="BPCL", display_name="Bharat Petroleum", sector="Energy", industry="Refineries", lot_size=1800, beta=1.05),
    "NTPC": UniverseItem(symbol="NTPC", display_name="NTPC Ltd", sector="Energy", industry="Power Generation", lot_size=1500, beta=0.95),
    "POWERGRID": UniverseItem(symbol="POWERGRID", display_name="Power Grid Corp", sector="Energy", industry="Power Transmission", lot_size=1800, beta=0.80),
    "COALINDIA": UniverseItem(symbol="COALINDIA", display_name="Coal India", sector="Energy", industry="Mining", lot_size=2100, beta=0.90),

    # --- Auto & Ancillaries ---
    "TATAMOTORS": UniverseItem(symbol="TATAMOTORS", display_name="Tata Motors", sector="Auto", industry="Automobiles", lot_size=550, beta=1.35),
    "M&M": UniverseItem(symbol="M&M", display_name="Mahindra & Mahindra", sector="Auto", industry="Automobiles", lot_size=350, beta=1.15),
    "MARUTI": UniverseItem(symbol="MARUTI", display_name="Maruti Suzuki", sector="Auto", industry="Automobiles", lot_size=50, beta=0.90),
    "BAJAJ-AUTO": UniverseItem(symbol="BAJAJ-AUTO", display_name="Bajaj Auto", sector="Auto", industry="2-Wheelers", lot_size=75, beta=0.85),
    "HEROMOTOCO": UniverseItem(symbol="HEROMOTOCO", display_name="Hero MotoCorp", sector="Auto", industry="2-Wheelers", lot_size=150, beta=0.95),
    "EICHERMOT": UniverseItem(symbol="EICHERMOT", display_name="Eicher Motors", sector="Auto", industry="2-Wheelers", lot_size=150, beta=0.95),
    "BHARATFORG": UniverseItem(symbol="BHARATFORG", display_name="Bharat Forge", sector="Auto", industry="Auto Ancillaries", lot_size=500, beta=1.20),

    # --- Metals & Mining ---
    "TATASTEEL": UniverseItem(symbol="TATASTEEL", display_name="Tata Steel", sector="Metals", industry="Steel", lot_size=5500, beta=1.40),
    "JSWSTEEL": UniverseItem(symbol="JSWSTEEL", display_name="JSW Steel", sector="Metals", industry="Steel", lot_size=675, beta=1.30),
    "HINDALCO": UniverseItem(symbol="HINDALCO", display_name="Hindalco Industries", sector="Metals", industry="Aluminium", lot_size=1400, beta=1.35),
    "JINDALSTEL": UniverseItem(symbol="JINDALSTEL", display_name="Jindal Steel & Power", sector="Metals", industry="Steel", lot_size=625, beta=1.45),
    "VEDL": UniverseItem(symbol="VEDL", display_name="Vedanta", sector="Metals", industry="Diversified Mining", lot_size=2000, beta=1.40),

    # --- Pharma & Healthcare ---
    "SUNPHARMA": UniverseItem(symbol="SUNPHARMA", display_name="Sun Pharma", sector="Pharma", industry="Pharmaceuticals", lot_size=350, beta=0.75),
    "DRREDDY": UniverseItem(symbol="DRREDDY", display_name="Dr Reddy's Laboratories", sector="Pharma", industry="Pharmaceuticals", lot_size=125, beta=0.80),
    "CIPLA": UniverseItem(symbol="CIPLA", display_name="Cipla", sector="Pharma", industry="Pharmaceuticals", lot_size=650, beta=0.70),
    "DIVISLAB": UniverseItem(symbol="DIVISLAB", display_name="Divi's Laboratories", sector="Pharma", industry="API / Pharma", lot_size=150, beta=0.95),
    "APOLLOHOSP": UniverseItem(symbol="APOLLOHOSP", display_name="Apollo Hospitals", sector="Pharma", industry="Healthcare Facilities", lot_size=125, beta=0.90),
    "LUPIN": UniverseItem(symbol="LUPIN", display_name="Lupin", sector="Pharma", industry="Pharmaceuticals", lot_size=425, beta=0.85),

    # --- FMCG & Consumption ---
    "ITC": UniverseItem(symbol="ITC", display_name="ITC Ltd", sector="FMCG", industry="Diversified FMCG", lot_size=1600, beta=0.65),
    "HINDUNILVR": UniverseItem(symbol="HINDUNILVR", display_name="Hindustan Unilever", sector="FMCG", industry="FMCG", lot_size=300, beta=0.60),
    "NESTLEIND": UniverseItem(symbol="NESTLEIND", display_name="Nestle India", sector="FMCG", industry="Food & Beverages", lot_size=25, beta=0.55),
    "BRITANNIA": UniverseItem(symbol="BRITANNIA", display_name="Britannia Industries", sector="FMCG", industry="Food & Beverages", lot_size=200, beta=0.65),
    "TATACONSUM": UniverseItem(symbol="TATACONSUM", display_name="Tata Consumer Products", sector="FMCG", industry="Consumer Products", lot_size=900, beta=0.80),
    "TITAN": UniverseItem(symbol="TITAN", display_name="Titan Company", sector="Consumption", industry="Jewellery & Watches", lot_size=175, beta=1.05),

    # --- Capital Goods, Infrastructure & Telecom ---
    "LT": UniverseItem(symbol="LT", display_name="Larsen & Toubro", sector="Infra", industry="Engineering & Construction", lot_size=150, beta=1.05),
    "BHARTIARTL": UniverseItem(symbol="BHARTIARTL", display_name="Bharti Airtel", sector="Telecom", industry="Telecom Services", lot_size=475, beta=0.85),
    "SIEMENS": UniverseItem(symbol="SIEMENS", display_name="Siemens India", sector="Capital Goods", industry="Electrical Equipment", lot_size=125, beta=1.20),
    "ABB": UniverseItem(symbol="ABB", display_name="ABB India", sector="Capital Goods", industry="Automation & Heavy Elec", lot_size=125, beta=1.25),
    "HAL": UniverseItem(symbol="HAL", display_name="Hindustan Aeronautics", sector="Defense", industry="Aerospace & Defense", lot_size=150, beta=1.30),
    "BEL": UniverseItem(symbol="BEL", display_name="Bharat Electronics", sector="Defense", industry="Defense Electronics", lot_size=2850, beta=1.25),
}

ALL_SWING_UNIVERSE: dict[str, UniverseItem] = {**BENCHMARKS, **SWING_EQUITY_UNIVERSE}


def get_swing_universe() -> list[UniverseItem]:
    """Return all active equity items in the swing universe."""
    return list(SWING_EQUITY_UNIVERSE.values())


def get_all_universe() -> list[UniverseItem]:
    """Return all universe items including benchmarks."""
    return list(ALL_SWING_UNIVERSE.values())


def get_universe_item(symbol: str) -> UniverseItem | None:
    """Case-insensitive lookup of universe item."""
    if not symbol:
        return None
    cleaned = symbol.strip().upper().replace("NSE:", "").replace("-EQ", "").replace("-INDEX", "")
    return ALL_SWING_UNIVERSE.get(cleaned)


def get_all_sectors() -> list[str]:
    """Return unique sector list."""
    sectors = {item.sector for item in SWING_EQUITY_UNIVERSE.values()}
    return sorted(list(sectors))


def get_universe_by_sector(sector: str) -> list[UniverseItem]:
    """Filter stocks by sector."""
    return [item for item in SWING_EQUITY_UNIVERSE.values() if item.sector.lower() == sector.lower()]
