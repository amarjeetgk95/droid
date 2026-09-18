"""Canonical settlement and realized-P&L booking for the signal audit ledger.

Holds ``record_square_off`` minus the ledger storage concerns, extracted from
:class:`SignalAuditLedger` so the reconciliation-driven net booking lives in a
focused module. Mixed into the ledger: call sites and public API unchanged.
"""
from __future__ import annotations

import time
from typing import Optional
import structlog

from app.signals.audit_models import AuditStateEvent, AuditTradeRecord, SETTLED_STATUSES

logger = structlog.get_logger()


class AuditSettlementMixin:
    """``record_square_off``: exact realized P&L booking for a closed trade."""

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

        # Guard: Once trade is closed/settled, return ALREADY_SETTLED without history append.
        if rec.status in SETTLED_STATUSES:
            logger.debug("trade_already_settled_skip_square_off", signal_id=signal_id, status=rec.status)
            return rec

        now_ms = exit_time_ms or int(time.time() * 1000)
        qty = rec.quantity or (rec.lots * rec.lot_size)
        side = (rec.paper_side or "BUY").upper()
        is_bullish = ("CALL" in rec.direction or "BULLISH" in rec.direction) and not ("PUT" in rec.direction or "BEARISH" in rec.direction)
        is_option = bool(rec.option_symbol or rec.option_type or rec.option_strike)

        # ── FAIL CLOSED on economics ──
        # A realized P&L requires two *real* premium-domain prices: the actual
        # fill and the actual exit. Nothing here may fall back to a Black-76
        # estimate or treat a spot index level as a premium. When either side is
        # missing or out of domain we still settle the record (so no position
        # lingers) but book no P&L and flag it for review.
        entry_price = rec.actual_fill_price
        economics_ok = True
        if is_option:
            if entry_price is None or entry_price > 5000.0 or exit_price > 5000.0:
                economics_ok = False
        elif entry_price is None:
            entry_price = rec.trigger_price

        if not economics_ok:
            rec.status = "CLOSED"
            rec.exit_price = exit_price if not (is_option and exit_price > 5000.0) else None
            rec.exited_at_utc = now_ms
            rec.exit_reason = exit_reason
            rec.outcome_label = f"{exit_reason} :: ECONOMICS_UNAVAILABLE"
            rec.is_winner = None
            rec.economics_unavailable = True
            rec.actual_pnl_inr = None
            rec.actual_pnl_points = None
            rec.actual_pnl_pct = None
            rec.total_pnl_inr = None
            rec.unrealized_pnl_inr = 0.0
            rec.unrealized_pnl_points = 0.0
            rec.unrealized_pnl_pct = 0.0
            rec.updated_at_utc = now_ms
            rec.state_history.append(
                AuditStateEvent(
                    timestamp_utc=now_ms,
                    from_state="EXECUTED",
                    to_state="CLOSED",
                    market_price=exit_price,
                    reason=f"SQUARE_OFF {exit_reason} (no P&L: entry/exit not premium-domain)",
                )
            )
            logger.warning(
                "square_off_economics_unavailable",
                signal_id=signal_id,
                entry_price=entry_price,
                exit_price=exit_price,
                reason=exit_reason,
            )
            self._schedule_persist(rec)
            return rec

        # ── ONE PnL SOURCE (phase 2b-1) ──
        # When the fill reconciler tracked this trade, its net figure is the
        # canonical realized PnL: it already contains the T1 staged leg and the
        # runner leg exactly once plus statutory costs, and it is immune to
        # `sync_with_paper_service` rewriting `rec.quantity` to the residual
        # quantity after a T1 partial. Direct close callers (delete / EOD) never
        # run the outcome tracker's final reconcile, so finish the residual leg
        # here. Synthetic (restored) records are deliberately skipped: their
        # pre-restart stage splits are unknown, so the ledger's own fill-based
        # P&L stays authoritative. With no reconciliation record (audit-only /
        # NO_MARK paths) the previous gross computation remains the fallback.
        recon_rec = None
        canonical_net: Optional[float] = None
        try:
            from app.signals.fill_reconciler import option_fill_reconciler
            recon_rec = option_fill_reconciler.get_reconciliation(signal_id)
        except Exception as recon_lookup_err:
            recon_rec = None
            logger.debug(
                "square_off_recon_lookup_failed",
                signal_id=signal_id,
                error=str(recon_lookup_err)[:150],
            )

        if recon_rec is not None and not getattr(recon_rec, "synthetic", False):
            if not recon_rec.is_fully_closed:
                try:
                    from app.signals.fsm import signal_fsm as _fsm
                    _recon_sig = _fsm.get(signal_id)
                except Exception:
                    _recon_sig = None
                if _recon_sig is not None:
                    try:
                        recon_rec = option_fill_reconciler.reconcile_final_exit(
                            _recon_sig,
                            float(exit_price),
                            exit_reason=exit_reason,
                            exit_time_ms=now_ms,
                        )
                    except Exception as recon_final_err:
                        logger.warning(
                            "square_off_reconcile_final_failed",
                            signal_id=signal_id,
                            error=str(recon_final_err)[:200],
                        )
            if recon_rec is not None and recon_rec.is_fully_closed:
                # The recon entry and the audit fill must share a price domain
                # (both option premiums <5000 or both spot-scale >5000), and a
                # zero/absent recon entry must never override a real audit fill:
                # otherwise a quarantined reconciliation would fabricate P&L.
                _audit_fill = rec.actual_fill_price
                _recon_entry = float(recon_rec.entry_fill_price or 0.0)
                _recon_domain_ok = True
                try:
                    if _recon_entry <= 0.0 and (_audit_fill or 0.0) > 0.0:
                        _recon_domain_ok = False
                    elif _audit_fill:
                        _recon_domain_ok = (float(_audit_fill) > 5000.0) == (_recon_entry > 5000.0)
                except Exception:
                    _recon_domain_ok = True
                if _recon_domain_ok:
                    canonical_net = round(float(recon_rec.net_realized_pnl_inr), 2)
                else:
                    logger.warning(
                        "square_off_recon_domain_mismatch_gross_fallback",
                        signal_id=signal_id,
                        audit_fill=_audit_fill,
                        recon_entry=_recon_entry,
                        recon_pnl=recon_rec.net_realized_pnl_inr,
                    )

        # Calculate actual PnL
        if is_option:
            # For option purchases, profit is exit premium minus entry premium
            if side == "BUY":
                points_diff = exit_price - entry_price
                # Invariant: An option buyer's loss is strictly bounded by 100% of premium paid
                if points_diff < -entry_price:
                    points_diff = -entry_price
            else:
                points_diff = entry_price - exit_price

            # Theoretical P&L is only meaningful against an independent price
            # reference. With no model permitted there is no second basis, so it
            # collapses to the realized move rather than a fabricated anchor.
            theo_diff = points_diff
        else:
            # Spot / Futures underlying tracking
            if is_bullish:
                points_diff = exit_price - entry_price
                theo_diff = exit_price - rec.trigger_price
            else:
                points_diff = entry_price - exit_price
                theo_diff = rec.trigger_price - exit_price

        actual_pnl_inr = round(points_diff * qty, 2)
        if is_option and side == "BUY":
            max_loss_inr = round(entry_price * qty, 2)
            if actual_pnl_inr < -max_loss_inr:
                actual_pnl_inr = -max_loss_inr

        # Canonical override: the reconciler net already carries the exact staged
        # T1 + runner split and costs, so it wins over the recalculated gross.
        # `points_diff` is re-derived as the blended gross per-unit move on the
        # intended trade quantity so the displayed points/rr stay coherent even
        # when sync shrank `rec.quantity` to the residual.
        _pnl_qty = qty
        if canonical_net is not None:
            _pnl_qty = int(recon_rec.intended_qty or qty or 0) or qty
            if _pnl_qty > 0:
                points_diff = round(float(recon_rec.gross_realized_pnl) / _pnl_qty, 2)
            theo_diff = points_diff
            actual_pnl_inr = canonical_net

        margin = rec.margin_used or (entry_price * _pnl_qty)
        pnl_pct = round((actual_pnl_inr / margin * 100.0), 2) if margin > 0 else 0.0
        if is_option and side == "BUY":
            pnl_pct = max(-100.0, pnl_pct)

        # Holding duration
        start_ts = rec.executed_at_utc or rec.created_at_utc
        duration_s = max(1, int((now_ms - start_ts) / 1000))
        mins, secs = divmod(duration_s, 60)
        hrs, mins = divmod(mins, 60)
        duration_str = f"{hrs}h {mins}m {secs}s" if hrs > 0 else f"{mins}m {secs}s"

        theo_pnl_inr = round(theo_diff * _pnl_qty, 2)

        # Winner classification aligned with FSM terminal domain states
        if exit_reason in ("STOP_LOSS_HIT", "LOSS"):
            is_win = False
            final_status = "LOST"
        elif exit_reason in ("TARGET_1_HIT", "TARGET_2_HIT", "WON"):
            is_win = True
            final_status = "WON"
        else:
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
        rec.current_price = exit_price
        rec.unrealized_pnl_inr = 0.0
        rec.unrealized_pnl_points = 0.0
        rec.unrealized_pnl_pct = 0.0
        rec.total_pnl_inr = actual_pnl_inr
        rec.status = final_status
        rec.outcome_label = exit_reason
        rec.is_winner = is_win
        # Zero-economics guard: prices moved but nothing booked — flag loudly
        # instead of letting a ₹0 close masquerade as a flat trade.
        if actual_pnl_inr == 0 and qty > 0 and abs(points_diff) > 0:
            rec.outcome_label = f"{exit_reason} :: ZERO_PNL_REVIEW"
            rec.is_winner = None
            logger.warning(
                "square_off_zero_pnl_flagged",
                signal_id=signal_id,
                entry_price=entry_price,
                exit_price=exit_price,
                qty=qty,
                reason=exit_reason,
            )
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

        # Asynchronously persist squared-off trade to Supabase
        self._schedule_persist(rec)

        return rec
