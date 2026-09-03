import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import structlog
from app.models.crypto import (
    CryptoOrderBook,
    CryptoOrderBookLevel,
    OrderBookSequenceStatus,
    ALLOWED_CRYPTO_SYMBOLS,
)
from app.models.market import DataStatus

logger = structlog.get_logger()


class OrderBookState:
    """Internal state for a single symbol's L2 order book depth."""

    def __init__(self, symbol: str, market_type: str = "spot"):
        self.symbol = symbol.upper()
        self.market_type = market_type
        self.bids: Dict[float, float] = {}  # price -> quantity
        self.asks: Dict[float, float] = {}  # price -> quantity
        self.last_update_id: int = 0
        self.snapshot_id: Optional[int] = None
        self.sequence_status: OrderBookSequenceStatus = OrderBookSequenceStatus.SYNCING
        self.data_status: DataStatus = DataStatus.LIVE
        self.last_event_timestamp: float = time.time()
        self.stale_threshold_sec: float = 5.0
        self.is_initialized: bool = False
        self.buffer: List[dict] = []

    def set_snapshot(self, last_update_id: int, bids_raw: List[List[str]], asks_raw: List[List[str]]):
        """Seed book from REST snapshot."""
        self.bids.clear()
        self.asks.clear()
        self.last_update_id = last_update_id
        self.snapshot_id = last_update_id

        for p_str, q_str in bids_raw:
            p, q = float(p_str), float(q_str)
            if q > 0:
                self.bids[p] = q

        for p_str, q_str in asks_raw:
            p, q = float(p_str), float(q_str)
            if q > 0:
                self.asks[p] = q

        self.last_event_timestamp = time.time()
        self.is_initialized = True
        self.sequence_status = OrderBookSequenceStatus.ACTIVE
        self.data_status = DataStatus.LIVE

    def apply_diff(self, event: dict) -> bool:
        """Apply sequential depth diff event with sequence verification."""
        self.last_event_timestamp = time.time()

        # Extract sequence IDs
        # Spot: U = first_update_id, u = final_update_id
        # Futures: U, u, pu = previous_final_update_id
        first_u = int(event.get("U", 0))
        final_u = int(event.get("u", 0))
        prev_u = int(event.get("pu", 0)) if "pu" in event else None

        if not self.is_initialized:
            # Buffer events until snapshot is received
            if len(self.buffer) < 500:
                self.buffer.append(event)
            return False

        # Sequence validation:
        if self.market_type == "futures" and prev_u is not None:
            # Binance Futures rule: event.pu == last_update_id
            if prev_u != self.last_update_id:
                # Check if this is an older event we already processed
                if final_u <= self.last_update_id:
                    return True  # drop duplicate / older event
                logger.warning(
                    "orderbook_sequence_gap_futures",
                    symbol=self.symbol,
                    expected_pu=self.last_update_id,
                    received_pu=prev_u,
                )
                self.sequence_status = OrderBookSequenceStatus.GAP_DETECTED
                self.data_status = DataStatus.DEGRADED
                return False
        else:
            # Binance Spot rule:
            if final_u <= self.last_update_id:
                return True  # drop older event
            if first_u > self.last_update_id + 1:
                logger.warning(
                    "orderbook_sequence_gap_spot",
                    symbol=self.symbol,
                    expected_next=self.last_update_id + 1,
                    received_first_u=first_u,
                )
                self.sequence_status = OrderBookSequenceStatus.GAP_DETECTED
                self.data_status = DataStatus.DEGRADED
                return False

        # Apply bid & ask updates
        bids_diff = event.get("b", []) or event.get("bids", [])
        asks_diff = event.get("a", []) or event.get("asks", [])

        for p_str, q_str in bids_diff:
            p, q = float(p_str), float(q_str)
            if q == 0.0:
                self.bids.pop(p, None)
            else:
                self.bids[p] = q

        for p_str, q_str in asks_diff:
            p, q = float(p_str), float(q_str)
            if q == 0.0:
                self.asks.pop(p, None)
            else:
                self.asks[p] = q

        self.last_update_id = final_u
        self.sequence_status = OrderBookSequenceStatus.ACTIVE
        self.data_status = DataStatus.LIVE
        return True

    def replay_buffer(self) -> int:
        """Replay buffered events onto recent snapshot."""
        replayed = 0
        if not self.is_initialized or not self.buffer:
            return replayed

        for ev in list(self.buffer):
            final_u = int(ev.get("u", 0))
            first_u = int(ev.get("U", 0))
            if final_u <= self.last_update_id:
                continue
            if first_u <= self.last_update_id + 1 <= final_u or (self.market_type == "futures" and ev.get("pu") == self.last_update_id):
                self.apply_diff(ev)
                replayed += 1
        self.buffer.clear()
        return replayed

    def check_health(self):
        """Check for stale order book."""
        age = time.time() - self.last_event_timestamp
        if age > self.stale_threshold_sec:
            if self.sequence_status != OrderBookSequenceStatus.GAP_DETECTED:
                self.sequence_status = OrderBookSequenceStatus.STALE
                self.data_status = DataStatus.STALE

    def to_model(self, limit: int = 20) -> CryptoOrderBook:
        """Convert in-memory depth to validated CryptoOrderBook model."""
        self.check_health()
        now = datetime.now(timezone.utc)

        sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:limit]
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:limit]

        bids_levels: List[CryptoOrderBookLevel] = []
        cum_qty_bid = 0.0
        cum_notional_bid = 0.0
        for p, q in sorted_bids:
            notional = p * q
            cum_qty_bid += q
            cum_notional_bid += notional
            bids_levels.append(
                CryptoOrderBookLevel(
                    price=p,
                    quantity=q,
                    notional=round(notional, 2),
                    cumulative_quantity=round(cum_qty_bid, 4),
                    cumulative_notional=round(cum_notional_bid, 2),
                )
            )

        asks_levels: List[CryptoOrderBookLevel] = []
        cum_qty_ask = 0.0
        cum_notional_ask = 0.0
        for p, q in sorted_asks:
            notional = p * q
            cum_qty_ask += q
            cum_notional_ask += notional
            asks_levels.append(
                CryptoOrderBookLevel(
                    price=p,
                    quantity=q,
                    notional=round(notional, 2),
                    cumulative_quantity=round(cum_qty_ask, 4),
                    cumulative_notional=round(cum_notional_ask, 2),
                )
            )

        best_bid = sorted_bids[0][0] if sorted_bids else 0.0
        best_ask = sorted_asks[0][0] if sorted_asks else 0.0
        mid = round((best_bid + best_ask) / 2.0, 2) if (best_bid > 0 and best_ask > 0) else best_bid
        spread = max(0.0, round(best_ask - best_bid, 2))
        spread_pct = round((spread / best_ask * 100), 4) if best_ask > 0 else 0.0

        bid_depth_total = round(cum_notional_bid, 2)
        ask_depth_total = round(cum_notional_ask, 2)
        imbalance = round(bid_depth_total - ask_depth_total, 2)
        total_depth = bid_depth_total + ask_depth_total
        imbalance_pct = round((imbalance / total_depth * 100), 2) if total_depth > 0 else 0.0

        age_ms = int((time.time() - self.last_event_timestamp) * 1000)

        return CryptoOrderBook(
            symbol=self.symbol,
            market_type=self.market_type,
            bids=bids_levels,
            asks=asks_levels,
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid,
            spread=spread,
            spread_percent=spread_pct,
            bid_depth_total=bid_depth_total,
            ask_depth_total=ask_depth_total,
            depth_imbalance=imbalance,
            depth_imbalance_pct=imbalance_pct,
            snapshot_id=self.snapshot_id,
            last_update_id=self.last_update_id,
            received_timestamp=now,
            data_age_ms=max(0, age_ms),
            sequence_status=self.sequence_status,
            status=self.data_status,
            provider="binance",
            timestamp=now,
        )


class OrderBookEngine:
    """Central registry maintaining live order books for BTC & ETH."""

    def __init__(self):
        self._books: Dict[Tuple[str, str], OrderBookState] = {}

    def get_or_create(self, symbol: str, market_type: str = "spot") -> OrderBookState:
        sym = symbol.upper()
        if sym not in ALLOWED_CRYPTO_SYMBOLS:
            raise ValueError(f"Symbol {sym} not in allowed whitelist {ALLOWED_CRYPTO_SYMBOLS}")
        key = (sym, market_type.lower())
        if key not in self._books:
            self._books[key] = OrderBookState(sym, market_type.lower())
        return self._books[key]

    def reset(self, symbol: str, market_type: str = "spot"):
        sym = symbol.upper()
        key = (sym, market_type.lower())
        if key in self._books:
            del self._books[key]


orderbook_engine = OrderBookEngine()
