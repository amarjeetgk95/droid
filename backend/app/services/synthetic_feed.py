import asyncio
import random
from datetime import datetime, timezone
from app.models.contracts import TickEvent, EventPriority
from app.services.central_feed import central_feed
import structlog

logger = structlog.get_logger()


class SyntheticTickFeed:
    """Demo-mode synthetic tick generator — restores realtime behaviour that
    was lost when MockProvider was removed (c3b18dd).

    When Indian providers are in DEMO mode (no valid broker token), no upstream
    websocket pushes ticks into central_feed, so the dashboard's
    `useMarketStream` never receives MARKET_TICKS and cards appear static.
    This service emulates the mock's 1-second tick cadence using realistic
    per-symbol base prices (mirrors Groww _DEMO_QUOTES) with a small random
    walk, feeding central_feed.ingest_tick so the existing broadcast loop
    delivers ticks to all frontend subscribers.

    It is provider-agnostic and runs regardless of the active provider —
    real providers' ticks (when they eventually stream) will simply intermix.
    """

    # Base prices calibrated to NSE/BSE live snapshot 31-Aug-2026 (NSE allIndices + BSE)
    # Previous 51520 for BANKNIFTY was 5.8k low vs TradingView 57336.
    _BASES: dict[str, float] = {
        "NIFTY 50": 24034.7,
        "BANKNIFTY": 57348.95,
        "FINNIFTY": 26102.15,
        "SENSEX": 76826.23,
        "INDIA VIX": 11.2,
    }

    _VOLUME_BASE: dict[str, int] = {
        "NIFTY 50": 1450000,
        "BANKNIFTY": 980000,
        "FINNIFTY": 620000,
        "SENSEX": 410000,
        "INDIA VIX": 0,
    }

    def __init__(self, interval_seconds: float = 1.0):
        self.interval = interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None
        self._seq: dict[str, int] = {s: 0 for s in self._BASES}
        self.rng = random.Random(42)
        # Mutable walk prices (start at bases)
        self._prices: dict[str, float] = dict(self._BASES)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("synthetic_feed_started", interval=self.interval, symbols=list(self._BASES.keys()))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("synthetic_feed_stopped")

    async def _loop(self) -> None:
        """Generate 1 tick per symbol per interval and ingest into central_feed."""
        while self._running:
            try:
                for symbol, base in list(self._prices.items()):
                    self._seq[symbol] += 1
                    # Deterministic small jitter +/- 0.06% for indices, +/-1.5% for VIX
                    is_vix = "VIX" in symbol
                    vol_pct = 0.015 if is_vix else 0.0006
                    jitter = (self.rng.random() - 0.5) * 2 * vol_pct * base
                    new_ltp = round(base + jitter, 2)
                    # Clamp VIX to realistic 10-20 range
                    if is_vix:
                        new_ltp = max(10.0, min(20.0, new_ltp))
                    self._prices[symbol] = new_ltp

                    tick = TickEvent(
                        timestamp=datetime.now(timezone.utc),
                        symbol=symbol,
                        instrument_token=f"{symbol.replace(' ', '_')}_SYNTH",
                        ltp=new_ltp,
                        open=round(self._BASES[symbol], 2),
                        high=round(max(self._BASES[symbol], new_ltp) * (1.0008 if not is_vix else 1.02), 2),
                        low=round(min(self._BASES[symbol], new_ltp) * (0.9992 if not is_vix else 0.98), 2),
                        close=new_ltp,
                        volume=self._VOLUME_BASE[symbol] // 100 + self.rng.randint(0, 5000) if self._VOLUME_BASE[symbol] else 0,
                        open_interest=None if is_vix else self.rng.randint(300000, 500000),
                        bid=round(new_ltp - 0.5, 2),
                        ask=round(new_ltp + 0.5, 2),
                        sequence_number=self._seq[symbol],
                        provider="synthetic",
                        priority=EventPriority.HIGH,
                    )
                    await central_feed.ingest_tick(tick)

                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("synthetic_feed_error", error=str(e))
                await asyncio.sleep(1.0)


synthetic_feed = SyntheticTickFeed()
