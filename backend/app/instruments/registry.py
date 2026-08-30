from app.instruments.schemas import InstrumentConfig

# Centralized registry — single source of truth for all searchable instruments
INSTRUMENT_REGISTRY: dict[str, InstrumentConfig] = {}

def _reg(cfg: InstrumentConfig):
    INSTRUMENT_REGISTRY[cfg.symbol.upper()] = cfg
    return cfg

# Indices (NSE/BSE)
_reg(InstrumentConfig(
    symbol="NIFTY",
    display_name="NIFTY 50",
    aliases=["nifty", "nifty 50", "nifty50", "cnx nifty"],
    asset_class="INDEX",
    exchange="NSE",
    data_provider_symbol="NSE:NIFTY",
    instrument_type="INDEX",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
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
    supported_timeframes=["1m","5m","15m","1h"],
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
    supported_timeframes=["1m","5m","15m","1h"],
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
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=True, options_available=True, futures_available=True,
))

_reg(InstrumentConfig(
    symbol="MIDCPNIFTY",
    display_name="NIFTY Midcap Select",
    aliases=["midcpnifty", "midcap nifty"],
    asset_class="INDEX",
    exchange="NSE",
    data_provider_symbol="NSE:MIDCPNIFTY",
    instrument_type="INDEX",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=True, options_available=True, futures_available=True,
))

# Equities
_reg(InstrumentConfig(
    symbol="RELIANCE",
    display_name="Reliance Industries Ltd",
    aliases=["reliance", "ril"],
    asset_class="EQUITY",
    exchange="NSE",
    data_provider_symbol="NSE:RELIANCE",
    instrument_type="EQUITY",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=True, options_available=True, futures_available=True,
))

_reg(InstrumentConfig(
    symbol="TCS",
    display_name="Tata Consultancy Services",
    aliases=["tcs"],
    asset_class="EQUITY",
    exchange="NSE",
    data_provider_symbol="NSE:TCS",
    instrument_type="EQUITY",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=True, options_available=True, futures_available=True,
))

_reg(InstrumentConfig(
    symbol="INFY",
    display_name="Infosys Ltd",
    aliases=["infy", "infosys"],
    asset_class="EQUITY",
    exchange="NSE",
    data_provider_symbol="NSE:INFY",
    instrument_type="EQUITY",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=True, options_available=True, futures_available=True,
))

_reg(InstrumentConfig(
    symbol="HDFCBANK",
    display_name="HDFC Bank Ltd",
    aliases=["hdfcbank", "hdfc bank"],
    asset_class="EQUITY",
    exchange="NSE",
    data_provider_symbol="NSE:HDFCBANK",
    instrument_type="EQUITY",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=True, options_available=True, futures_available=True,
))

# Crypto
_reg(InstrumentConfig(
    symbol="BTCUSD",
    display_name="Bitcoin / US Dollar",
    aliases=["bitcoin", "btc", "btc usd", "btc-usd", "btcusd", "xbt"],
    asset_class="CRYPTO",
    exchange="CONFIGURED_PROVIDER",
    data_provider_symbol="BTCUSD",
    instrument_type="SPOT",
    currency="USD",
    price_precision=2,
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

_reg(InstrumentConfig(
    symbol="BTCUSDT",
    display_name="Bitcoin / Tether",
    aliases=["btcusdt", "btc usdt", "btc-usdt"],
    asset_class="CRYPTO",
    exchange="BINANCE",
    data_provider_symbol="BINANCE:BTCUSDT",
    instrument_type="SPOT",
    currency="USDT",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

_reg(InstrumentConfig(
    symbol="ETHUSD",
    display_name="Ethereum / US Dollar",
    aliases=["ethereum", "eth", "eth usd", "eth-usd"],
    asset_class="CRYPTO",
    exchange="CONFIGURED_PROVIDER",
    data_provider_symbol="ETHUSD",
    instrument_type="SPOT",
    currency="USD",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

_reg(InstrumentConfig(
    symbol="ETHUSDT",
    display_name="Ethereum / Tether",
    aliases=["ethusdt", "eth usdt"],
    asset_class="CRYPTO",
    exchange="BINANCE",
    data_provider_symbol="BINANCE:ETHUSDT",
    instrument_type="SPOT",
    currency="USDT",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=False, options_available=False, futures_available=True,
    trading_session="24x7", timezone="UTC",
))

# Commodities / FX placeholder
_reg(InstrumentConfig(
    symbol="GOLD",
    display_name="Gold Spot",
    aliases=["gold", "xau", "xauusd"],
    asset_class="COMMODITY",
    exchange="MCX",
    data_provider_symbol="MCX:GOLD",
    instrument_type="SPOT",
    currency="INR",
    supported_timeframes=["1m","5m","15m","1h"],
    fno_available=False, options_available=False, futures_available=True,
))

def get_all_instruments() -> list[InstrumentConfig]:
    return list(INSTRUMENT_REGISTRY.values())

def get_instrument(symbol: str) -> InstrumentConfig | None:
    if not symbol:
        return None
    return INSTRUMENT_REGISTRY.get(symbol.strip().upper().replace(" ", "").replace("-", "").replace("/", "")) or INSTRUMENT_REGISTRY.get(symbol.strip().upper())

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
