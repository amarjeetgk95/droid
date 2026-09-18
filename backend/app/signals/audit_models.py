"""Audit ledger domain models and FSM<->ledger status mapping.

Split out of :mod:`audit_ledger` so the ledger engine and the settlement
booking logic can share these types without circular imports. The public names
are re-exported from :mod:`audit_ledger` so existing imports keep working.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional
from pydantic import BaseModel, Field, computed_field

from app.signals.safety.clocks import ist_from_timestamp

# Unified status enum with FSM: ledger stores BOTH fsm_state (canonical) and
# status (display). Mapping is single-sourced here and covered by test.
FSM_TO_AUDIT_STATUS: dict[str, str] = {
    "DETECTED": "ARMED",
    "VALIDATED": "ARMED",
    "ARMED": "ARMED",
    "TRIGGERED": "TRIGGERED",
    "CONFIRMED": "EXECUTED",
    "TARGET_1_HIT": "TARGET_1_HIT",
    "TARGET_2_HIT": "WON",
    "STOP_LOSS_HIT": "LOST",
    "TIME_STOP_HIT": "CLOSED",
    "RUNNER_TIME_STOP_HIT": "CLOSED",
    "INVALIDATED": "CLOSED",
    "EXPIRED": "CLOSED",
    "CLOSED": "CLOSED",
}
AUDIT_TO_FSM_STATUS: dict[str, str] = {
    "ARMED": "ARMED",
    "TRIGGERED": "TRIGGERED",
    "CONFIRMED": "CONFIRMED",
    "EXECUTED": "CONFIRMED",
    "TARGET_1_HIT": "TARGET_1_HIT",
    "WON": "TARGET_2_HIT",
    "LOST": "STOP_LOSS_HIT",
    "CLOSED": "CLOSED",
    "VOID": "CLOSED",
}

SETTLED_STATUSES: frozenset[str] = frozenset({"WON", "LOST", "CLOSED", "VOID"})


def format_timestamp_ist(epoch_ms: Optional[int]) -> Optional[str]:
    """Format epoch millisecond timestamp into full IST date and time string."""
    if not epoch_ms:
        return None
    try:
        dt = ist_from_timestamp(epoch_ms / 1000.0)
        return dt.strftime("%d %b %Y, %H:%M:%S IST")
    except Exception:
        return None


class AuditStateEvent(BaseModel):
    timestamp_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    from_state: str
    to_state: str
    market_price: Optional[float] = None
    reason: str = "STATE_UPDATE"


class AuditTradeRecord(BaseModel):
    audit_id: str = Field(default_factory=lambda: f"AUD-{uuid.uuid4().hex[:8].upper()}")
    signal_id: str
    underlying: str
    strategy: str
    direction: str
    timeframe: str = "5M"

    # Contract specs
    option_symbol: Optional[str] = None
    option_type: Optional[str] = None
    option_strike: Optional[float] = None
    expiry: Optional[str] = None
    lot_size: int = 75
    lots: int = 1
    quantity: int = 75

    # Planned signal levels
    spot_price_at_creation: float = 0.0
    trigger_price: float = 0.0
    entry_min: float = 0.0
    entry_max: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    risk_points: float = 0.0
    risk_reward_t1: float = 1.5
    risk_reward_t2: float = 3.0
    confidence: float = 80.0
    is_scalp: bool = False
    signal_type: str = "INTRADAY"

    # Paper execution details
    paper_order_id: Optional[str] = None
    paper_side: Optional[str] = None
    actual_fill_price: Optional[float] = None
    executed_at_utc: Optional[int] = None
    slippage_points: Optional[float] = None
    margin_used: Optional[float] = None

    # Exit & Square-off details
    exit_price: Optional[float] = None
    exited_at_utc: Optional[int] = None
    exit_reason: Optional[str] = None
    holding_time_seconds: Optional[int] = None
    holding_time_str: Optional[str] = None

    # Actual Profit & Loss (Audited)
    actual_pnl_inr: Optional[float] = None
    actual_pnl_points: Optional[float] = None
    actual_pnl_pct: Optional[float] = None
    theoretical_pnl_points: Optional[float] = None
    theoretical_pnl_inr: Optional[float] = None

    # Live Real-Time Mark-to-Market (MTM) Metrics
    current_price: Optional[float] = None
    unrealized_pnl_inr: Optional[float] = None
    unrealized_pnl_points: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    total_pnl_inr: Optional[float] = None
    live_duration_seconds: Optional[int] = None
    live_duration_str: Optional[str] = None

    # Mark provenance (single mark authority). Says WHICH price produced
    # current_price, so a broker print is never confused with a model output:
    #   CHAIN_BIDASK / CHAIN_LTP  real broker print
    #   MODEL_BLACK76             labeled theoretical value
    #   INDEX_SPOT                non-option instrument
    #   UNAVAILABLE               fail-closed: MTM deliberately not updated
    mark_source: Optional[str] = None
    mark_age_ms: Optional[int] = None
    mark_note: Optional[str] = None
    #: True when the last MTM attempt had no usable price. Stale beats wrong:
    #: the previous mark is retained and this flags the gap to the UI.
    economics_unavailable: bool = False

    # Status — unified with FSM via mapping table (both stored).
    # fsm_state is the canonical FSM domain; status is the ledger display domain.
    status: str = "ARMED"
    fsm_state: Optional[str] = None
    outcome_label: Optional[str] = None
    is_winner: Optional[bool] = None
    # Chain-mark re-validation provenance for restored receipts.
    source: Optional[str] = None
    chain_revalidated: bool = False

    # History
    state_history: list[AuditStateEvent] = Field(default_factory=list)
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    updated_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    @computed_field
    @property
    def created_at_str(self) -> str:
        return format_timestamp_ist(self.created_at_utc) or ""

    @computed_field
    @property
    def executed_at_str(self) -> Optional[str]:
        return format_timestamp_ist(self.executed_at_utc)

    def compute_live_duration(self, now_ms: Optional[int] = None) -> tuple[int, str]:
        now = now_ms or int(time.time() * 1000)
        start = self.executed_at_utc or self.created_at_utc
        duration_s = max(1, int((now - start) / 1000))
        mins, secs = divmod(duration_s, 60)
        hrs, mins = divmod(mins, 60)
        dur_str = f"{hrs}h {mins}m {secs}s" if hrs > 0 else f"{mins}m {secs}s"
        return duration_s, dur_str

    def format_holding_time(self) -> str:
        if not self.holding_time_seconds:
            if self.status in ("ARMED", "TRIGGERED", "CONFIRMED", "EXECUTED", "TARGET_1_HIT"):
                _, d_str = self.compute_live_duration()
                return f"{d_str} (Live)"
            return "—"
        mins, secs = divmod(self.holding_time_seconds, 60)
        hrs, mins = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs}h {mins}m {secs}s"
        return f"{mins}m {secs}s"
