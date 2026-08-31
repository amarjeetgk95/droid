"""
Instrument Registry — §§3,4,6,7,14,15
Centralized registry for all tradable instruments: NIFTY, BANKNIFTY, SENSEX, BTCUSD
Extensible without rewriting core. Single source of truth that determines
asset class, exchange, session, capabilities, contract spec, timeframes, strategy & risk config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Literal, Any

AssetClass = Literal["INDEX", "CRYPTO"]
Pipeline = Literal["INDIAN_EQUITY", "CRYPTO"]
ExchangeLiteral = Literal["NSE", "BSE", "BINANCE", "COINBASE"]
ContractTypeLiteral = Literal["INDEX_FUT", "INDEX_OPTION", "LINEAR_PERP", "SPOT", "FUTURES", "OPTIONS"]
SettlementTypeLiteral = Literal["CASH", "PHYSICAL"]
ExpiryTypeLiteral = Literal["WEEKLY", "MONTHLY", "PERPETUAL", "SPOT"]


@dataclass(frozen=True)
class ContractSpec:
    """
    Contract-aware metadata — required fields per §14
    Dynamically sourceable from broker/exchange metadata.
    """
    contract_type: ContractTypeLiteral
    lot_size: Decimal
    min_order_qty: Decimal
    quantity_step: Decimal
    tick_size: Decimal
    contract_multiplier: Decimal
    quote_currency: str
    settlement_type: SettlementTypeLiteral
    expiry_type: ExpiryTypeLiteral
    expiry_timestamp_utc: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "lot_size": str(self.lot_size),
            "min_order_qty": str(self.min_order_qty),
            "quantity_step": str(self.quantity_step),
            "tick_size": str(self.tick_size),
            "contract_multiplier": str(self.contract_multiplier),
            "quote_currency": self.quote_currency,
            "settlement_type": self.settlement_type,
            "expiry_type": self.expiry_type,
            "expiry_timestamp_utc": self.expiry_timestamp_utc,
        }


@dataclass
class InstrumentProfile:
    instrument_id: str
    display_name: str
    asset_class: AssetClass
    pipeline: Pipeline
    exchange: ExchangeLiteral
    quote_currency: str
    underlying: str
    # Session / availability
    market_session: str  # e.g. NSE_0915_1530, BINANCE_24x7
    timezone: str
    supported_timeframes: list[str] = field(default_factory=lambda: ["1m", "3m", "5m", "15m", "30m", "1h"])
    # Capabilities
    has_spot: bool = True
    has_futures: bool = False
    has_options: bool = False
    has_funding: bool = False
    has_oi: bool = False
    has_liquidations: bool = False
    # Contract
    contract_spec: ContractSpec | None = None
    # Strategy / risk defaults
    strategy_config: dict[str, Any] = field(default_factory=dict)
    risk_config: dict[str, Any] = field(default_factory=dict)
    # Aliases for resolution
    aliases: list[str] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "display_name": self.display_name,
            "asset_class": self.asset_class,
            "pipeline": self.pipeline,
            "exchange": self.exchange,
            "quote_currency": self.quote_currency,
            "underlying": self.underlying,
            "market_session": self.market_session,
            "timezone": self.timezone,
            "supported_timeframes": self.supported_timeframes,
            "has_spot": self.has_spot,
            "has_futures": self.has_futures,
            "has_options": self.has_options,
            "has_funding": self.has_funding,
            "has_oi": self.has_oi,
            "has_liquidations": self.has_liquidations,
            "contract_spec": self.contract_spec.to_dict() if self.contract_spec else None,
            "aliases": self.aliases,
            "is_active": self.is_active,
        }


class CapabilityMap:
    """
    Declares per-instrument data-module availability.
    Prevents forcing equity-only fields (PC R, breadth) into BTCUSD (§8, §29)
    """
    # Per instrument_id -> set of available analysis modules
    _caps: dict[str, set[str]] = {
        "NIFTY": {
            "spot", "futures", "options_chain", "oi", "oi_change", "pcr",
            "futures_basis", "volume", "vwap", "breadth", "related_indices",
            "support_resistance", "multi_timeframe", "volatility",
        },
        "BANKNIFTY": {
            "spot", "futures", "options_chain", "oi", "oi_change", "pcr",
            "futures_basis", "volume", "vwap", "breadth", "related_indices",
            "support_resistance", "multi_timeframe", "volatility",
        },
        "SENSEX": {
            "spot", "futures", "options_chain", "oi", "oi_change", "pcr",
            "futures_basis", "volume", "vwap", "breadth", "related_indices",
            "support_resistance", "multi_timeframe", "volatility",
        },
        "BTCUSD": {
            "spot", "perpetual", "oi", "funding", "liquidations", "basis",
            "volume", "vwap", "order_book", "long_short_positioning",
            "volatility", "support_resistance", "multi_timeframe",
        },
    }

    @classmethod
    def available_modules(cls, instrument_id: str) -> set[str]:
        return cls._caps.get(instrument_id.upper(), set())

    @classmethod
    def supports(cls, instrument_id: str, module: str) -> bool:
        return module in cls.available_modules(instrument_id)

    @classmethod
    def is_applicable(cls, instrument_id: str, field_name: str) -> bool:
        # Generic check — return NOT_APPLICABLE marker if field irrelevant
        if field_name in ("pcr", "equity_breadth", "index_options") and instrument_id.upper() == "BTCUSD":
            return False
        if field_name in ("funding", "liquidations", "long_short") and instrument_id.upper() in ("NIFTY", "BANKNIFTY", "SENSEX"):
            return False
        return True


# ── Central AssetRegistry (the single unified registry) ───────────────

class AssetRegistry:
    """
    Unified instrument registry — §4.
    Do NOT duplicate the application per asset. All resolution goes through here.
    Backed by contract specs that can be hot-refreshed from broker metadata.
    """
    def __init__(self):
        self._profiles: dict[str, InstrumentProfile] = {}
        self._by_alias: dict[str, str] = {}
        self._bootstrap_defaults()

    def _bootstrap_defaults(self) -> None:
        # NIFTY — Indian index via NSE
        self.register(InstrumentProfile(
            instrument_id="NIFTY",
            display_name="NIFTY 50",
            asset_class="INDEX", pipeline="INDIAN_EQUITY",
            exchange="NSE", quote_currency="INR", underlying="NIFTY",
            market_session="NSE_0915_1530", timezone="Asia/Kolkata",
            supported_timeframes=["1m","3m","5m","15m","30m","1h","1D"],
            has_spot=True, has_futures=True, has_options=True, has_oi=True,
            contract_spec=ContractSpec(
                contract_type="INDEX_FUT", lot_size=Decimal("25"), min_order_qty=Decimal("25"),
                quantity_step=Decimal("25"), tick_size=Decimal("0.05"),
                contract_multiplier=Decimal("1"), quote_currency="INR",
                settlement_type="CASH", expiry_type="WEEKLY_OR_MONTHLY",
            ),
            aliases=["nifty 50", "nifty50", "nse:nifty", "nifty 50 index"],
        ))
        self.register(InstrumentProfile(
            instrument_id="BANKNIFTY",
            display_name="NIFTY Bank",
            asset_class="INDEX", pipeline="INDIAN_EQUITY",
            exchange="NSE", quote_currency="INR", underlying="BANKNIFTY",
            market_session="NSE_0915_1530", timezone="Asia/Kolkata",
            has_spot=True, has_futures=True, has_options=True, has_oi=True,
            contract_spec=ContractSpec(
                contract_type="INDEX_FUT", lot_size=Decimal("15"), min_order_qty=Decimal("15"),
                quantity_step=Decimal("15"), tick_size=Decimal("0.05"),
                contract_multiplier=Decimal("1"), quote_currency="INR",
                settlement_type="CASH", expiry_type="WEEKLY_OR_MONTHLY",
            ),
            aliases=["bank nifty", "banknifty index", "nse:banknifty"],
        ))
        self.register(InstrumentProfile(
            instrument_id="SENSEX",
            display_name="BSE SENSEX",
            asset_class="INDEX", pipeline="INDIAN_EQUITY",
            exchange="BSE", quote_currency="INR", underlying="SENSEX",
            market_session="BSE_0915_1530", timezone="Asia/Kolkata",
            has_spot=True, has_futures=True, has_options=True, has_oi=True,
            contract_spec=ContractSpec(
                contract_type="INDEX_FUT", lot_size=Decimal("10"), min_order_qty=Decimal("10"),
                quantity_step=Decimal("10"), tick_size=Decimal("0.05"),
                contract_multiplier=Decimal("1"), quote_currency="INR",
                settlement_type="CASH", expiry_type="WEEKLY_OR_MONTHLY",
            ),
            aliases=["bse sensex", "sensex 30", "bse:sensex"],
        ))
        self.register(InstrumentProfile(
            instrument_id="BTCUSD",
            display_name="Bitcoin USD",
            asset_class="CRYPTO", pipeline="CRYPTO",
            exchange="BINANCE", quote_currency="USD", underlying="BTC",
            market_session="CRYPTO_24x7", timezone="UTC",
            supported_timeframes=["1m","3m","5m","15m","30m","1h","4h","1D"],
            has_spot=True, has_futures=True, has_options=False,
            has_funding=True, has_oi=True, has_liquidations=True,
            contract_spec=ContractSpec(
                contract_type="LINEAR_PERP", lot_size=Decimal("0.001"), min_order_qty=Decimal("0.001"),
                quantity_step=Decimal("0.001"), tick_size=Decimal("0.01"),
                contract_multiplier=Decimal("1"), quote_currency="USD",
                settlement_type="CASH", expiry_type="PERPETUAL",
            ),
            aliases=["btcusd", "btc/usd", "xbtusd", "binance:btcusdt", "btcusdt", "btc"],
        ))

    def register(self, profile: InstrumentProfile) -> None:
        key = profile.instrument_id.upper()
        self._profiles[key] = profile
        self._by_alias[key] = key
        for alias in profile.aliases:
            norm = alias.strip().upper().replace("/", "").replace(":", "").replace(" ", "")
            self._by_alias[norm] = key
            self._by_alias[alias.upper()] = key

    def get(self, instrument_id: str) -> InstrumentProfile | None:
        if not instrument_id:
            return None
        k = instrument_id.strip().upper()
        if k in self._profiles:
            return self._profiles[k]
        # alias fallback
        compact = k.replace("/", "").replace(":", "").replace(" ", "").replace("-", "")
        resolved = self._by_alias.get(k) or self._by_alias.get(compact)
        if resolved:
            return self._profiles.get(resolved)
        return None

    def require(self, instrument_id: str) -> InstrumentProfile:
        p = self.get(instrument_id)
        if not p:
            raise KeyError(f"instrument {instrument_id!r} not in AssetRegistry")
        return p

    def all_profiles(self) -> list[InstrumentProfile]:
        return list(self._profiles.values())

    def all_ids(self) -> list[str]:
        return list(self._profiles.keys())

    def pipeline_for(self, instrument_id: str) -> Pipeline:
        return self.require(instrument_id).pipeline

    def is_indian_equity(self, instrument_id: str) -> bool:
        return self.pipeline_for(instrument_id) == "INDIAN_EQUITY"

    def is_crypto(self, instrument_id: str) -> bool:
        return self.pipeline_for(instrument_id) == "CRYPTO"

    def update_contract_spec(self, instrument_id: str, spec: ContractSpec) -> None:
        """Hot-refresh from broker metadata — never permanently hard-code (§14)"""
        prof = self.require(instrument_id)
        prof.contract_spec = spec

    def update_from_broker_metadata(self, instrument_id: str, meta: dict) -> None:
        """Dynamic sourcing from authoritative broker instrument metadata (§14)"""
        prof = self.get(instrument_id)
        if not prof:
            return
        # meta keys: lot_size, tick_size, contract_multiplier etc
        old = prof.contract_spec
        if old is None:
            return
        def _d(k, fallback):
            v = meta.get(k, fallback)
            return Decimal(str(v)) if v is not None else fallback
        new_spec = ContractSpec(
            contract_type=meta.get("contract_type", old.contract_type),
            lot_size=_d("lot_size", old.lot_size),
            min_order_qty=_d("min_order_qty", old.min_order_qty),
            quantity_step=_d("quantity_step", old.quantity_step),
            tick_size=_d("tick_size", old.tick_size),
            contract_multiplier=_d("contract_multiplier", old.contract_multiplier),
            quote_currency=meta.get("quote_currency", old.quote_currency),
            settlement_type=meta.get("settlement_type", old.settlement_type),
            expiry_type=meta.get("expiry_type", old.expiry_type),
            expiry_timestamp_utc=meta.get("expiry_timestamp_utc", old.expiry_timestamp_utc),
        )
        prof.contract_spec = new_spec


# Global singleton — importable everywhere
asset_registry = AssetRegistry()
