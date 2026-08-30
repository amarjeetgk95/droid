# Chart Analysis — Restricted Derivatives Universe
# ---------------------------------------------------------------------------
# This registry is permanently restricted to the seven approved derivatives
# for the Chart Analysis module (see module spec):
#   NIFTY 50 | BANKNIFTY | FINNIFTY | SENSEX | BTC | ETH | SOL
# No other instrument may be added automatically based on liquidity,
# volatility, user activity, or API availability.  Other providers/
# app-wide registries may exist elsewhere, but chart_analysis MUST
# only expose these seven — see CHART_ANALYSIS_UNIVERSE.
# ---------------------------------------------------------------------------

from app.instruments.schemas import InstrumentConfig

# Timeframes required by Chart Analysis: 1m / 5m / 15m / 1h / 4h / Daily
CHART_ANALYSIS_TIMEFRAMES: list[str] = ["1m", "5m", "15m", "1h", "4h", "1D"]

# Centralized registry — single source of truth for all searchable instruments
INSTRUMENT_REGISTRY: dict[str, InstrumentConfig] = {}

def _reg(cfg: InstrumentConfig):
    INSTRUMENT_REGISTRY[cfg.symbol.upper()] = cfg
    return cfg

# ---- Approved Chart-Analysis Universe (7 instruments only) ----
# Indian Index Derivatives
_reg(InstrumentConfig(
    symbol="NIFTY",
    display_name="NIFTY 50",
    aliases=["nifty", "nifty 50", "nifty50", "cnx nifty"],
    asset_class="INDEX",
    exchange="NSE",
    data_provider_symbol="NSE:NIFTY",
    instrument_type="INDEX",
    currency="INR",
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=True, options_available=True, futures_available=True,
    trading_session="NSE_0915_1530", timezone="Asia/Kolkata",
))

_reg(InstrumentConfig(
    symbol="BANKNIFTY",
    display_name="NIFTY Bank",
    aliases=["banknifty", "nifty bank", "bank nifty", "bank index"],
    asset_class="INDEX",
    exchange="NSE",
    data_provider_symbol="NSE:BANKNIFTY",
    instrument_type="INDEX",
    currency="INR",
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=True, options_available=True, futures_available=True,
))

_reg(InstrumentConfig(
    symbol="FINNIFTY",
    display_name="NIFTY Financial Services",
    aliases=["finnifty", "fin nifty"],
    asset_class="INDEX",
    exchange="NSE",
    data_provider_symbol="NSE:FINNIFTY",
    instrument_type="INDEX",
    currency="INR",
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=True, options_available=True, futures_available=True,
))

_reg(InstrumentConfig(
    symbol="SENSEX",
    display_name="BSE SENSEX",
    aliases=["sensex", "bse sensex", "bse30"],
    asset_class="INDEX",
    exchange="BSE",
    data_provider_symbol="BSE:SENSEX",
    instrument_type="INDEX",
    currency="INR",
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=True, options_available=True, futures_available=True,
))

# Crypto Derivatives — canonical symbols are BTC/ETH/SOL (plain).  BTCUSD/BTCUSDT
# etc. are retained as ALIASES only so external feeds can still resolve.
_reg(InstrumentConfig(
    symbol="BTC",
    display_name="Bitcoin",
    aliases=["bitcoin", "btcusd", "btc usd", "btc-usd", "btc-usd", "btcusdt", "btc usdt", "btc-usdt", "xbt", "binance:btcusdt"],
    asset_class="CRYPTO",
    exchange="BINANCE",
    data_provider_symbol="BINANCE:BTCUSDT",
    instrument_type="SPOT",
    currency="USDT",
    price_precision=2,
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

_reg(InstrumentConfig(
    symbol="ETH",
    display_name="Ethereum",
    aliases=["ethereum", "ethusd", "eth usd", "eth-usd", "ethusdt", "eth usdt", "eth-usdt", "binance:ethusdt"],
    asset_class="CRYPTO",
    exchange="BINANCE",
    data_provider_symbol="BINANCE:ETHUSDT",
    instrument_type="SPOT",
    currency="USDT",
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

_reg(InstrumentConfig(
    symbol="SOL",
    display_name="Solana",
    aliases=["solana", "sol", "solusd", "sol usd", "sol-usd", "solusdt", "sol usdt", "sol-usdt", "binance:solusdt"],
    asset_class="CRYPTO",
    exchange="BINANCE",
    data_provider_symbol="BINANCE:SOLUSDT",
    instrument_type="SPOT",
    currency="USDT",
    price_precision=2,
    supported_timeframes=CHART_ANALYSIS_TIMEFRAMES,
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

# Fixed universe constant — chart_analysis must not expose anything else.
CHART_ANALYSIS_UNIVERSE: list[str] = ["NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX", "BTC", "ETH", "SOL"]

def get_all_instruments() -> list[InstrumentConfig]:
    return list(INSTRUMENT_REGISTRY.values())

def get_chart_analysis_universe() -> list[InstrumentConfig]:
    """Return ONLY the seven approved chart-analysis instruments in canonical order."""
    return [INSTRUMENT_REGISTRY[s] for s in CHART_ANALYSIS_UNIVERSE if s in INSTRUMENT_REGISTRY]

def get_instrument(symbol: str) -> InstrumentConfig | None:
    if not symbol:
        return None
    # First try exact/compact lookup in restricted registry
    direct = INSTRUMENT_REGISTRY.get(symbol.strip().upper().replace(" ", "").replace("-", "").replace("/", "")) or INSTRUMENT_REGISTRY.get(symbol.strip().upper())
    if direct:
        return direct
    # Fallback: alias match across restricted universe only
    import re as _re
    compact = _re.sub(r"[^a-z0-9]", "", symbol.strip().lower())
    for cfg in INSTRUMENT_REGISTRY.values():
        for alias in cfg.aliases:
            if _re.sub(r"[^a-z0-9]", "", alias.lower()) == compact:
                return cfg
        if _re.sub(r"[^a-z0-9]", "", cfg.display_name.lower()) == compact:
            return cfg
    return None

def get_by_symbol_exact(symbol: str) -> InstrumentConfig | None:
    return INSTRUMENT_REGISTRY.get(symbol.strip().upper())

def is_supported_timeframe(symbol: str, tf: str) -> bool:
    cfg = get_by_symbol_exact(symbol.upper())
    if not cfg:
        # also try resolver
        cfg = get_instrument(symbol)
    if not cfg:
        return False
    return tf in cfg.supported_timeframes
