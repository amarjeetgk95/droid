from app.instruments.resolver import search_instruments
from app.instruments.schemas import InstrumentSearchResult

def to_search_result(cfg) -> InstrumentSearchResult:
    return InstrumentSearchResult(
        display_name=cfg.display_name,
        symbol=cfg.symbol,
        asset_class=cfg.asset_class,
        exchange=cfg.exchange,
        instrument_type=cfg.instrument_type,
        fno_available=cfg.fno_available,
        options_available=cfg.options_available,
        futures_available=cfg.futures_available,
        supported_timeframes=cfg.supported_timeframes,
        data_provider_symbol=cfg.data_provider_symbol,
        current_status="ACTIVE",
    )

def search(query: str, asset_class=None, exchange=None, instrument_type=None, fno_only=False, limit=20):
    cfgs = search_instruments(query, asset_class, exchange, instrument_type, fno_only, limit)
    return [to_search_result(c) for c in cfgs]
