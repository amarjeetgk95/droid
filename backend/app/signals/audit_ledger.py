"""
Institutional Signal Audit Ledger & Trade Performance Engine
Provides comprehensive lifecycle auditing for quantitative signals:
  - ARMED -> CONFIRMED -> PAPER_EXECUTED -> TARGET_HIT / STOP_LOSS_HIT -> SQUARED_OFF
  - Exact realized Profit and Loss (INR ₹, points, and %)
  - Slippage & Spread audit
  - Portfolio attribution & Strategy performance analytics
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


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

    # Status
    status: Literal["DETECTED", "ARMED", "CONFIRMED", "EXECUTED", "WON", "LOST", "EXPIRED", "CLOSED"] = "ARMED"
    outcome_label: Optional[str] = None
    is_winner: Optional[bool] = None

    # History
    state_history: list[AuditStateEvent] = Field(default_factory=list)
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    updated_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    def format_holding_time(self) -> str:
        if not self.holding_time_seconds:
            return "—"
        mins, secs = divmod(self.holding_time_seconds, 60)
        hrs, mins = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs}h {mins}m {secs}s"
        return f"{mins}m {secs}s"


class SignalAuditLedger:
    """
    Authoritative append-only in-memory ledger for Signal & Paper Trade Audit with PnL reconciliation.
    """

    def __init__(self, max_records: int = 5000):
        self._trades: dict[str, AuditTradeRecord] = {}  # signal_id -> AuditTradeRecord
        self._max_records = max_records

    def record_signal_created(
        self,
        signal_id: str,
        underlying: str,
        strategy: str,
        direction: str,
        timeframe: str,
        spot_price: float,
        trigger: float,
        stop_loss: float,
        target_1: float,
        target_2: float,
        confidence: float = 80.0,
        option_contract: Optional[dict] = None,
        lots: int = 1,
        status: str = "ARMED",
    ) -> AuditTradeRecord:
        opt = option_contract or {}
        lot_sz = int(opt.get("lot_size", 75 if underlying == "NIFTY" else (30 if underlying == "BANKNIFTY" else 10)))
        qty = lots * lot_sz

        rec = AuditTradeRecord(
            signal_id=signal_id,
            underlying=underlying,
            strategy=strategy,
            direction=direction,
            timeframe=timeframe,
            option_symbol=opt.get("broker_symbol") or opt.get("symbol"),
            option_type=opt.get("option_type", "CE" if "CALL" in direction else "PE"),
            option_strike=float(opt.get("strike", 0.0)) if opt.get("strike") else None,
            expiry=opt.get("expiry"),
            lot_size=lot_sz,
            lots=lots,
            quantity=qty,
            spot_price_at_creation=spot_price,
            trigger_price=trigger,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_points=abs(trigger - stop_loss),
            confidence=confidence,
            status="CONFIRMED" if status == "CONFIRMED" else "ARMED",
        )
        rec.state_history.append(
            AuditStateEvent(
                from_state="DETECTED",
                to_state=rec.status,
                market_price=spot_price,
                reason="SIGNAL_REGISTERED",
            )
        )
        self._trades[signal_id] = rec
        return rec

    def record_paper_executed(
        self,
        signal_id: str,
        paper_order_id: str,
        fill_price: float,
        quantity: int,
        lots: int,
        side: str = "BUY",
        margin_used: Optional[float] = None,
    ) -> Optional[AuditTradeRecord]:
        rec = self._trades.get(signal_id)
        now_ms = int(time.time() * 1000)
        if not rec:
            return None

        rec.paper_order_id = paper_order_id
        rec.paper_side = side
        rec.actual_fill_price = fill_price
        rec.quantity = quantity
        rec.lots = lots
        rec.executed_at_utc = now_ms
        rec.slippage_points = round(abs(fill_price - rec.trigger_price), 2)
        rec.margin_used = margin_used or (fill_price * quantity)
        rec.status = "EXECUTED"
        rec.updated_at_utc = now_ms

        rec.state_history.append(
            AuditStateEvent(
                timestamp_utc=now_ms,
                from_state="CONFIRMED",
                to_state="EXECUTED",
                market_price=fill_price,
                reason=f"PAPER_ORDER_FILLED {paper_order_id}",
            )
        )
        logger.info("audit_paper_executed", signal_id=signal_id, order_id=paper_order_id, fill_price=fill_price)
        return rec

    def record_square_off(
        self,
        signal_id: str,
        exit_price: float,
        exit_reason: str,
        exit_time_ms: Optional[int] = None,
    ) -> Optional[AuditTradeRecord]:
        """
        Calculates exact actual profit and loss upon trade exit and closes the trade record.
        """
        rec = self._trades.get(signal_id)
        if not rec:
            return None

        now_ms = exit_time_ms or int(time.time() * 1000)
        entry_price = rec.actual_fill_price or rec.trigger_price
        qty = rec.quantity or (rec.lots * rec.lot_size)
        side = (rec.paper_side or "BUY").upper()

        # Calculate actual PnL
        is_call_or_buy = "BUY" in side or "CALL" in rec.direction
        if is_call_or_buy:
            points_diff = exit_price - entry_price
        else:
            points_diff = entry_price - exit_price

        actual_pnl_inr = round(points_diff * qty, 2)
        margin = rec.margin_used or (entry_price * qty)
        pnl_pct = round((actual_pnl_inr / margin * 100.0), 2) if margin > 0 else 0.0

        # Holding duration
        start_ts = rec.executed_at_utc or rec.created_at_utc
        duration_s = max(1, int((now_ms - start_ts) / 1000))
        mins, secs = divmod(duration_s, 60)
        hrs, mins = divmod(mins, 60)
        duration_str = f"{hrs}h {mins}m {secs}s" if hrs > 0 else f"{mins}m {secs}s"

        # Theoretical outcome for comparison
        theo_diff = (exit_price - rec.trigger_price) if is_call_or_buy else (rec.trigger_price - exit_price)
        theo_pnl_inr = round(theo_diff * qty, 2)

        # Winner classification
        is_win = actual_pnl_inr > 0
        final_status = "WON" if is_win else ("LOST" if actual_pnl_inr < 0 else "CLOSED")

        rec.exit_price = exit_price
        rec.exited_at_utc = now_ms
        rec.exit_reason = exit_reason
        rec.holding_time_seconds = duration_s
        rec.holding_time_str = duration_str
        rec.actual_pnl_inr = actual_pnl_inr
        rec.actual_pnl_points = round(points_diff, 2)
        rec.actual_pnl_pct = pnl_pct
        rec.theoretical_pnl_points = round(theo_diff, 2)
        rec.theoretical_pnl_inr = theo_pnl_inr
        rec.status = final_status
        rec.outcome_label = exit_reason
        rec.is_winner = is_win
        rec.updated_at_utc = now_ms

        rec.state_history.append(
            AuditStateEvent(
                timestamp_utc=now_ms,
                from_state="EXECUTED",
                to_state=final_status,
                market_price=exit_price,
                reason=f"SQUARE_OFF {exit_reason} (P&L: ₹{actual_pnl_inr:+,.2f})",
            )
        )
        logger.info(
            "audit_trade_squared_off",
            signal_id=signal_id,
            exit_price=exit_price,
            pnl_inr=actual_pnl_inr,
            duration=duration_str,
            reason=exit_reason,
        )
        return rec

    def get(self, signal_id: str) -> Optional[AuditTradeRecord]:
        return self._trades.get(signal_id)

    def list_trades(
        self,
        underlying: Optional[str] = None,
        strategy: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditTradeRecord]:
        trades = list(self._trades.values())
        if underlying and underlying != "ALL":
            trades = [t for t in trades if t.underlying == underlying.upper()]
        if strategy and strategy != "ALL":
            trades = [t for t in trades if t.strategy == strategy.upper()]
        if status and status != "ALL":
            trades = [t for t in trades if t.status == status.upper()]
        # Newest first
        trades.sort(key=lambda t: t.created_at_utc, reverse=True)
        return trades[:limit]

    def get_summary_metrics(self) -> dict[str, Any]:
        """Compute aggregated portfolio PnL and accuracy statistics."""
        all_t = list(self._trades.values())
        closed_t = [t for t in all_t if t.status in ("WON", "LOST", "CLOSED")]
        open_t = [t for t in all_t if t.status in ("ARMED", "CONFIRMED", "EXECUTED")]

        total_closed = len(closed_t)
        winners = [t for t in closed_t if t.is_winner is True]
        losers = [t for t in closed_t if t.is_winner is False and (t.actual_pnl_inr or 0) < 0]

        win_rate = round((len(winners) / total_closed * 100.0), 1) if total_closed > 0 else 0.0
        net_pnl = round(sum(t.actual_pnl_inr or 0.0 for t in closed_t), 2)
        gross_profit = round(sum(t.actual_pnl_inr or 0.0 for t in winners), 2)
        gross_loss = round(abs(sum(t.actual_pnl_inr or 0.0 for t in losers)), 2)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        max_win = max([t.actual_pnl_inr or 0.0 for t in winners], default=0.0)
        max_loss = min([t.actual_pnl_inr or 0.0 for t in losers], default=0.0)

        avg_pnl = round(net_pnl / total_closed, 2) if total_closed > 0 else 0.0
        avg_holding = round(sum(t.holding_time_seconds or 0 for t in closed_t) / total_closed, 0) if total_closed > 0 else 0

        # Strategy breakdown
        strat_breakdown: dict[str, dict] = {}
        for t in all_t:
            s_entry = strat_breakdown.setdefault(t.strategy, {"total": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
            s_entry["total"] += 1
            if t.is_winner:
                s_entry["wins"] += 1
            elif t.is_winner is False and (t.actual_pnl_inr or 0) < 0:
                s_entry["losses"] += 1
            s_entry["net_pnl"] = round(s_entry["net_pnl"] + (t.actual_pnl_inr or 0.0), 2)

        for v in strat_breakdown.values():
            dec = v["wins"] + v["losses"]
            v["win_rate"] = round((v["wins"] / dec * 100.0), 1) if dec > 0 else 0.0

        # Underlying breakdown
        under_breakdown: dict[str, dict] = {}
        for t in all_t:
            u_entry = under_breakdown.setdefault(t.underlying, {"total": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
            u_entry["total"] += 1
            if t.is_winner:
                u_entry["wins"] += 1
            elif t.is_winner is False and (t.actual_pnl_inr or 0) < 0:
                u_entry["losses"] += 1
            u_entry["net_pnl"] = round(u_entry["net_pnl"] + (t.actual_pnl_inr or 0.0), 2)

        for v in under_breakdown.values():
            dec = v["wins"] + v["losses"]
            v["win_rate"] = round((v["wins"] / dec * 100.0), 1) if dec > 0 else 0.0

        return {
            "total_signals_audited": len(all_t),
            "open_trades": len(open_t),
            "closed_trades": total_closed,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate_pct": win_rate,
            "net_realized_pnl_inr": net_pnl,
            "gross_profit_inr": gross_profit,
            "gross_loss_inr": gross_loss,
            "profit_factor": profit_factor,
            "max_win_inr": max_win,
            "max_loss_inr": max_loss,
            "avg_trade_pnl_inr": avg_pnl,
            "avg_holding_time_seconds": avg_holding,
            "strategy_breakdown": strat_breakdown,
            "underlying_breakdown": under_breakdown,
        }


signal_audit_ledger = SignalAuditLedger()
