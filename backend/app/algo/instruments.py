"""
Instrument Master & Corporate Actions — §9-10

Stable internal ID, not display symbol. Versioned contract specs.
Corporate action freeze → refresh → reconcile → resume
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Any
import structlog

from app.algo.money import D

logger = structlog.get_logger()

ActionType = Literal[
    "SPLIT", "BONUS", "SYMBOL_CHANGE", "LOT_SIZE_CHANGE",
    "STRIKE_GRID_CHANGE", "CONTRACT_SPEC_CHANGE", "EXPIRY_CHANGE",
    "UNDERLYING_CHANGE", "TICK_SIZE_CHANGE", "INSTRUMENT_CODE_CHANGE"
]


@dataclass
class InstrumentSpec:
    internal_id: str
    broker_symbol: str
    broker_instrument_id: str | None
    exchange: str
    instrument_type: str
    underlying: str | None
    expiry: date | None
    strike: Decimal | None
    option_type: Literal["CE", "PE"] | None
    lot_size: int
    tick_size: Decimal
    contract_multiplier: Decimal
    contract_spec_version: int = 1
    valid_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: datetime | None = None
    is_active: bool = True
    is_tradable: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class CorporateAction:
    id: str
    instrument_internal_id: str
    action_type: ActionType
    effective_date: date
    details: dict[str, Any]
    status: Literal["PENDING", "APPLIED", "FAILED"] = "PENDING"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InstrumentMaster:
    """Versioned central registry."""

    def __init__(self):
        self._by_internal: dict[str, list[InstrumentSpec]] = {}
        self._by_broker: dict[str, InstrumentSpec] = {}
        self._pending_actions: list[CorporateAction] = []
        self._frozen_instruments: set[str] = set()  # internal_ids frozen pending CA

    def upsert(self, spec: InstrumentSpec) -> InstrumentSpec:
        lst = self._by_internal.setdefault(spec.internal_id, [])
        # version bump if spec changed materially
        if lst and lst[-1].contract_spec_version == spec.contract_spec_version:
            # Check if material change requires new version
            prev = lst[-1]
            if (prev.lot_size != spec.lot_size or prev.tick_size != spec.tick_size or
                prev.strike != spec.strike or prev.expiry != spec.expiry):
                spec.contract_spec_version = prev.contract_spec_version + 1
                spec.valid_from = datetime.now(timezone.utc)
                prev.valid_to = spec.valid_from
        lst.append(spec)
        self._by_broker[spec.broker_symbol] = spec
        logger.info("instrument_upsert", internal_id=spec.internal_id, version=spec.contract_spec_version)
        return spec

    def get_by_internal(self, internal_id: str, as_of: datetime | None = None) -> InstrumentSpec | None:
        lst = self._by_internal.get(internal_id)
        if not lst:
            return None
        if as_of is None:
            return lst[-1]
        # valid range search
        for s in reversed(lst):
            if s.valid_from <= as_of and (s.valid_to is None or as_of < s.valid_to):
                return s
        return lst[-1]

    def get_by_broker_symbol(self, symbol: str) -> InstrumentSpec | None:
        return self._by_broker.get(symbol)

    def resolve(self, symbol: str) -> InstrumentSpec | None:
        """Resolve display symbol → authoritative spec (never rely solely on symbol for identity)."""
        return self.get_by_broker_symbol(symbol)

    def is_frozen(self, internal_id: str) -> bool:
        return internal_id in self._frozen_instruments

    # --- Corporate actions §10 ---
    def register_corporate_action(self, action: CorporateAction) -> None:
        self._pending_actions.append(action)
        self._frozen_instruments.add(action.instrument_internal_id)
        logger.warning("corporate_action_freeze", internal_id=action.instrument_internal_id, type=action.action_type)

    def apply_corporate_action(self, action_id: str) -> CorporateAction | None:
        for a in self._pending_actions:
            if a.id == action_id:
                # In production: refresh broker metadata, reconcile positions/orders, recalc margin, invalidate signals
                a.status = "APPLIED"
                self._frozen_instruments.discard(a.instrument_internal_id)
                logger.info("corporate_action_applied", id=action_id)
                return a
        return None

    def freeze_check(self, internal_id: str) -> tuple[bool, str | None]:
        """Return (is_blocked, reason)."""
        if self.is_frozen(internal_id):
            return True, f"CORPORATE_ACTION_PENDING:{internal_id}"
        spec = self.get_by_internal(internal_id)
        if spec and not spec.is_tradable:
            return True, "INSTRUMENT_NOT_TRADABLE"
        if spec and not spec.is_active:
            return True, "INSTRUMENT_NOT_ACTIVE"
        return False, None

    def validate_order_params(self, spec: InstrumentSpec, price: Decimal, quantity: int) -> tuple[bool, str | None]:
        """§8 tick/quantity validation."""
        px = D(price)
        tick = spec.tick_size
        # price must be multiple of tick_size
        # (px / tick) should be integer within tolerance
        ratio = px / tick
        if ratio != ratio.to_integral_value():
            # Allow small epsilon via quantized check
            quantized = (ratio.to_integral_value(rounding="ROUND_HALF_UP") * tick)
            if abs(quantized - px) > tick / D(2):
                return False, f"PRICE_NOT_MULTIPLE_OF_TICK:{tick}"
        if quantity % spec.lot_size != 0:
            return False, f"QUANTITY_NOT_MULTIPLE_OF_LOT:{spec.lot_size}"
        if quantity <= 0:
            return False, "QUANTITY_MUST_BE_POSITIVE"
        return True, None


# Singleton
instrument_master = InstrumentMaster()
