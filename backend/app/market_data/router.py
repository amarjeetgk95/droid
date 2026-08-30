from datetime import datetime, timezone
from app.services.market_service import MarketService
from app.instruments.registry import get_by_symbol_exact, get_instrument
from app.market_data.timeframes import TIMEFRAME_CONFIG

class MarketDataRouter:
    def __init__(self, service: MarketService | None = None):
        self.service = service or MarketService()

    async def get_candles(self, symbol: str, timeframe: str):
        # validate instrument
        cfg = get_by_symbol_exact(symbol.upper()) or get_instrument(symbol)
        if cfg and timeframe not in cfg.supported_timeframes:
            raise ValueError(f"Timeframe {timeframe} not supported for {symbol}")
        if timeframe not in TIMEFRAME_CONFIG:
            raise ValueError(f"Unsupported timeframe {timeframe}")
        # delegate to service (which maps symbol to provider symbol)
        # For crypto, pass through directly
        return await self.service.get_candles(symbol, timeframe)

    async def get_quote(self, symbol: str):
        return await self.service.get_quote(symbol)

router = MarketDataRouter()
