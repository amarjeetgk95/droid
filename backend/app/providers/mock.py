import asyncio
import random
import time
from datetime import datetime, timedelta, timezone, time as dt_time, date
from zoneinfo import ZoneInfo
from app.providers.base import MarketDataProvider
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote, IndexCard,
    MarketHealthStatus, MarketStatusResponse, MarketBreadthData,
    SectorBreadth, DataStatus, MarketSession
)
from app.models.contracts import TickEvent, EventPriority, OptionType
from app.core.token_manager import TokenManager, ConnectionState
from app.core.rate_limiter import TokenBucketRateLimiter
from app.services.contract_master import contract_master_service
from app.services.calendar_service import calendar_service
import structlog

logger = structlog.get_logger()
IST = ZoneInfo("Asia/Kolkata")


class MockProvider(MarketDataProvider):
    """Deterministic or random mock data provider with live tick stream simulation.
    
    Adheres to Sections 4, 10, 11, 15, 16, and 85.
    """

    def __init__(self, mode: str = "deterministic", seed: int = 42):
        self.mode = mode
        self.seed = seed
        self.rng = random.Random(seed) if mode == "deterministic" else random.Random()
        
        self.token_manager = TokenManager(provider="mock")
        self.rate_limiter = TokenBucketRateLimiter(requests_per_second=50.0, requests_per_minute=1000.0)

        self._stream_running = False
        self._stream_task: asyncio.Task | None = None
        self._seq_counter = 0

        self.instruments = {
            "NIFTY 50": {"base_price": 25000.0, "volatility": 0.005, "volume_base": 1000000, "underlying": "NIFTY"},
            "BANKNIFTY": {"base_price": 52000.0, "volatility": 0.008, "volume_base": 800000, "underlying": "BANKNIFTY"},
            "FINNIFTY": {"base_price": 24000.0, "volatility": 0.007, "volume_base": 500000, "underlying": "FINNIFTY"},
            "SENSEX": {"base_price": 81500.0, "volatility": 0.006, "volume_base": 700000, "underlying": "SENSEX"},
            "INDIA VIX": {"base_price": 13.0, "volatility": 0.02, "volume_base": 0, "underlying": "VIX"},
        }

    @property
    def provider_name(self) -> str:
        return "mock"

    def get_token_manager(self) -> TokenManager:
        return self.token_manager

    def get_rate_limiter(self) -> TokenBucketRateLimiter:
        return self.rate_limiter
        
    def _get_current_time(self) -> datetime:
        return datetime.now(timezone.utc).astimezone(IST)

    async def get_quote(self, symbol: str) -> NormalizedQuote:
        if symbol not in self.instruments:
            raise ValueError(f"Unknown symbol: {symbol}")
            
        inst = self.instruments[symbol]
        base_price = inst["base_price"]
        volatility = inst["volatility"]
        
        if self.mode == "deterministic":
            now = self._get_current_time()
            self.rng.seed(f"{self.seed}_{symbol}_{now.date()}")
            
        prev_close = base_price
        change_pct = (self.rng.random() - 0.5) * 2 * volatility
        ltp = base_price * (1 + change_pct)
        change = ltp - prev_close
        
        high = max(prev_close, ltp) * (1 + self.rng.random() * volatility * 0.5)
        low = min(prev_close, ltp) * (1 - self.rng.random() * volatility * 0.5)
        open_price = prev_close * (1 + (self.rng.random() - 0.5) * volatility)
        
        volume = int(inst["volume_base"] * (0.5 + self.rng.random())) if inst["volume_base"] > 0 else 0
        oi = int(volume * (0.1 + self.rng.random() * 0.5)) if symbol != "INDIA VIX" else None

        self.token_manager.record_message()

        return NormalizedQuote(
            symbol=symbol,
            display_name=symbol.title() if symbol != "INDIA VIX" else "India VIX",
            timestamp=datetime.now(timezone.utc),
            ltp=round(ltp, 2),
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            previous_close=round(prev_close, 2),
            change=round(change, 2),
            change_percent=round(change_pct * 100, 2),
            volume=volume,
            open_interest=oi,
            status=DataStatus.DEMO,
            provider=self.provider_name
        )

    async def get_quotes(self, symbols: list[str] | None = None) -> list[NormalizedQuote]:
        if symbols is None:
            symbols = list(self.instruments.keys())
        quotes = []
        for sym in symbols:
            if sym in self.instruments:
                quotes.append(await self.get_quote(sym))
        return quotes

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        if symbol not in self.instruments:
            raise ValueError(f"Unknown symbol: {symbol}")
            
        tf_mapping = {
            "1m": (timedelta(minutes=1), 375),
            "5m": (timedelta(minutes=5), 75),
            "15m": (timedelta(minutes=15), 25),
            "1h": (timedelta(hours=1), 6),
            "1D": (timedelta(days=1), 250),
        }
        if timeframe not in tf_mapping:
            raise ValueError(f"Invalid timeframe: {timeframe}")
            
        tdelta, count = tf_mapping[timeframe]
        inst = self.instruments[symbol]
        
        if self.mode == "deterministic":
            self.rng.seed(f"{self.seed}_{symbol}_{timeframe}")
            
        end_time = end
        if end_time is None:
            if self.mode == "deterministic":
                now = self._get_current_time()
                end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
            else:
                end_time = self._get_current_time()
        start_time = end_time - (tdelta * count)
        
        candles = []
        current_time = start_time
        current_price = inst["base_price"]
        volatility = inst["volatility"]
        
        cumulative_volume = 0
        cumulative_typical_volume = 0.0
        
        for _ in range(count):
            open_price = current_price
            move = (self.rng.random() - 0.5) * volatility * current_price
            close = open_price + move
            
            high = max(open_price, close) + self.rng.random() * volatility * current_price * 0.5
            low = min(open_price, close) - self.rng.random() * volatility * current_price * 0.5
            
            volume = int((inst["volume_base"] / count) * (0.5 + self.rng.random())) if inst["volume_base"] > 0 else 0
            
            typical_price = (high + low + close) / 3
            cumulative_volume += volume
            cumulative_typical_volume += (typical_price * volume)
            
            vwap = round(cumulative_typical_volume / cumulative_volume, 2) if cumulative_volume > 0 else None
            
            candles.append(NormalizedCandle(
                timestamp=current_time.astimezone(timezone.utc),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=volume,
                vwap=vwap
            ))
            
            current_time += tdelta
            current_price = close
            
        return candles

    async def get_index_cards(self) -> list[IndexCard]:
        quotes = await self.get_quotes()
        cards = []
        
        for q in quotes:
            if self.mode == "deterministic":
                self.rng.seed(f"{self.seed}_{q.symbol}_sparkline")
            
            sparkline = []
            cp = q.previous_close
            for _ in range(20):
                cp += (self.rng.random() - 0.5) * q.previous_close * 0.005
                sparkline.append(round(cp, 2))
                
            sparkline[-1] = q.ltp
            
            cards.append(IndexCard(
                symbol=q.symbol,
                display_name=q.display_name,
                ltp=q.ltp,
                change=q.change,
                change_percent=q.change_percent,
                open=q.open,
                high=q.high,
                low=q.low,
                previous_close=q.previous_close,
                volume=q.volume,
                open_interest=q.open_interest,
                sparkline=sparkline,
                status=DataStatus.DEMO,
                timestamp=q.timestamp,
                provider=self.provider_name
            ))
        return cards

    async def get_market_status(self) -> MarketStatusResponse:
        now = self._get_current_time()
        time_only = now.time()
        
        is_trading = calendar_service.is_trading_day(now.date())
        if not is_trading:
            session = MarketSession.CLOSED
        elif time_only < dt_time(9, 0):
            session = MarketSession.PRE_OPEN
        elif time_only < dt_time(9, 15):
            session = MarketSession.PRE_OPEN
        elif time_only < dt_time(15, 30):
            session = MarketSession.OPEN
        else:
            session = MarketSession.CLOSED
            
        return MarketStatusResponse(
            session=session,
            market_time=datetime.now(timezone.utc),
            is_trading_day=is_trading,
            data_status=DataStatus.DEMO,
            provider=self.provider_name
        )

    async def get_health(self) -> MarketHealthStatus:
        self.token_manager.record_heartbeat()
        diag = self.token_manager.get_diagnostics()
        
        return MarketHealthStatus(
            status="HEALTHY",
            provider=self.provider_name,
            mode="DEMO",
            last_update=datetime.now(timezone.utc),
            data_age_seconds=0.1,
            latency_ms=None,  # Cannot measure real broker latency with MockProvider
            active_instruments=len(self.instruments),
            reconnect_count=diag["reconnect_count"],
            subscriptions=len(self.instruments),
            buffer_depth=0,
            dropped_events=0,
            circuit_breaker_state="CLOSED",
            last_heartbeat=datetime.now(timezone.utc),
            message="Mock provider running in deterministic mode"
        )

    async def get_market_breadth(self) -> MarketBreadthData:
        if self.mode == "deterministic":
            self.rng.seed(f"{self.seed}_breadth")
            
        total = 500
        adv = int(total * (0.3 + self.rng.random() * 0.4))
        dec = int((total - adv) * (0.8 + self.rng.random() * 0.2))
        unc = total - adv - dec
        
        adr = round(adv / dec, 2) if dec > 0 else float('inf')
        
        sectors_data = [
            ("IT", 50), ("Banking", 40), ("Pharma", 60), 
            ("Auto", 30), ("FMCG", 40), ("Metal", 20), 
            ("Energy", 35), ("Realty", 15)
        ]
        
        sectors = []
        for name, count in sectors_data:
            s_adv = int(count * self.rng.random())
            s_dec = int((count - s_adv) * self.rng.random())
            s_unc = count - s_adv - s_dec
            s_chg = round((self.rng.random() - 0.5) * 5.0, 2)
            
            sectors.append(SectorBreadth(
                name=name,
                change_percent=s_chg,
                advancing=s_adv,
                declining=s_dec,
                unchanged=s_unc
            ))
            
        if adr > 1.5:
            sentiment = "VERY_BULLISH"
            score = 80 + self.rng.random() * 20
        elif adr > 1.1:
            sentiment = "BULLISH"
            score = 60 + self.rng.random() * 20
        elif adr > 0.9:
            sentiment = "NEUTRAL"
            score = 40 + self.rng.random() * 20
        elif adr > 0.5:
            sentiment = "BEARISH"
            score = 20 + self.rng.random() * 20
        else:
            sentiment = "VERY_BEARISH"
            score = self.rng.random() * 20

        return MarketBreadthData(
            advancing=adv,
            declining=dec,
            unchanged=unc,
            advance_decline_ratio=adr,
            sectors=sectors,
            sentiment=sentiment,
            sentiment_score=round(score, 1),
            status=DataStatus.DEMO,
            timestamp=datetime.now(timezone.utc)
        )

    async def get_expiries(self, symbol: str) -> list[datetime]:
        """Resolve expiries dynamically from contract master."""
        underlying = "NIFTY"
        if "BANK" in symbol:
            underlying = "BANKNIFTY"
        elif "FIN" in symbol:
            underlying = "FINNIFTY"
        elif "SENSEX" in symbol:
            underlying = "SENSEX"
        
        dates = contract_master_service.get_expiries(underlying)
        return [datetime.combine(d, dt_time(15, 30), tzinfo=IST).astimezone(timezone.utc) for d in dates]

    async def get_option_chain(
        self,
        symbol: str,
        expiry: datetime | None = None,
    ) -> list[NormalizedOptionQuote]:
        """Generate normalized option chain quotes for an underlying."""
        underlying = "NIFTY"
        if "BANK" in symbol:
            underlying = "BANKNIFTY"
        elif "FIN" in symbol:
            underlying = "FINNIFTY"
        elif "SENSEX" in symbol:
            underlying = "SENSEX"

        exp_date = expiry.date() if expiry else (contract_master_service.resolve_expiries(underlying).current_expiry)
        if not exp_date:
            return []

        contracts = contract_master_service.search_contracts(underlying=underlying, expiry=exp_date)
        quotes = []
        
        quote = await self.get_quote("NIFTY 50" if underlying == "NIFTY" else underlying)
        spot = quote.ltp

        for c in contracts:
            if c.strike is None or c.option_type is None:
                continue
                
            diff = spot - c.strike if c.option_type == OptionType.CE else c.strike - spot
            intrinsic = max(0.0, diff)
            time_val = max(10.0, spot * 0.01 * (1 + self.rng.random()))
            ltp = round(intrinsic + time_val, 2)
            bid = round(max(0.05, ltp - 0.5), 2)
            ask = round(ltp + 0.5, 2)

            quotes.append(NormalizedOptionQuote(
                timestamp=datetime.now(timezone.utc),
                provider=self.provider_name,
                instrument=c.symbol,
                contract_id=c.instrument_token,
                underlying=underlying,
                expiry=datetime.combine(exp_date, dt_time(15, 30), tzinfo=IST).astimezone(timezone.utc),
                strike=c.strike,
                option_type=c.option_type.value,
                ltp=ltp,
                bid=bid,
                ask=ask,
                volume=int(self.rng.random() * 50000),
                oi=int(self.rng.random() * 200000),
            ))

        return quotes

    async def start_stream(self) -> None:
        """Start the background live tick stream generator."""
        if self._stream_running:
            return
        self._stream_running = True
        self.token_manager.set_state(ConnectionState.CONNECTED)
        self._stream_task = asyncio.create_task(self._stream_loop())
        logger.info("mock_stream_started")

    async def stop_stream(self) -> None:
        """Stop the background stream generator."""
        self._stream_running = False
        self.token_manager.set_state(ConnectionState.DISCONNECTED)
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        logger.info("mock_stream_stopped")

    async def _stream_loop(self) -> None:
        """Simulate high-frequency incoming market ticks."""
        from app.services.central_feed import central_feed

        while self._stream_running:
            try:
                for symbol, inst in self.instruments.items():
                    self._seq_counter += 1
                    vol = inst["volatility"]
                    base = inst["base_price"]
                    move = (self.rng.random() - 0.5) * vol * base * 0.05
                    ltp = round(base + move, 2)

                    tick = TickEvent(
                        timestamp=datetime.now(timezone.utc),
                        symbol=symbol,
                        instrument_token=f"{symbol}_TOKEN",
                        ltp=ltp,
                        open=base,
                        high=round(max(base, ltp) * 1.002, 2),
                        low=round(min(base, ltp) * 0.998, 2),
                        close=ltp,
                        volume=int(inst["volume_base"] / 100),
                        open_interest=None if symbol == "INDIA VIX" else 500000,
                        bid=round(ltp - 0.5, 2),
                        ask=round(ltp + 0.5, 2),
                        sequence_number=self._seq_counter,
                        provider="mock",
                        priority=EventPriority.HIGH,
                    )
                    await central_feed.ingest_tick(tick)
                    self.token_manager.record_message()

                await asyncio.sleep(1.0)  # 1-second tick cadence
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("mock_stream_error", error=str(e))
                await asyncio.sleep(1.0)
