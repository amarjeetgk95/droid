"""
Reconciliation Engine — §71-72

Continuously reconcile Internal Orders ↔ Broker Orders,
Internal Positions ↔ Broker Positions, Internal Capital ↔ Broker Funds/Margin,
Reservations ↔ Order State.

Material discrepancy → BLOCK_NEW_ENTRIES
After restart: load persistent → query broker → reconcile all → rebuild → resume
"""
from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass
from typing import Literal, Any
import structlog

from app.algo.money import D

logger = structlog.get_logger()

ReconType = Literal["ORDERS","POSITIONS","FUNDS","RESERVATIONS"]
ReconStatus = Literal["MATCHED","MISMATCHED","RECONCILING","RESOLVED","BLOCKED"]


@dataclass
class ReconResult:
    recon_type: ReconType
    status: ReconStatus
    discrepancy: dict | None = None
    magnitude: Decimal | None = None
    affected_order_id: Any | None = None
    affected_position_id: str | None = None
    should_block: bool = False
    message: str = ""


class ReconciliationEngine:
    """
    Stateless engine — caller supplies internal & broker snapshots.
    Persistent audit written via DB (algo_reconciliation_log).
    """

    # Thresholds for material discrepancy
    AMOUNT_TOLERANCE: Decimal = D("0.01")
    QTY_TOLERANCE: int = 0

    def reconcile_orders(self, internal_orders: list[dict], broker_orders: list[dict]) -> list[ReconResult]:
        results: list[ReconResult] = []
        broker_by_client: dict[str, dict] = {o.get("client_order_id", o.get("clientOrderId")): o for o in broker_orders if o.get("client_order_id") or o.get("clientOrderId")}
        broker_by_broker_id: dict[str, dict] = {o.get("broker_order_id", o.get("order_id")): o for o in broker_orders}

        for io in internal_orders:
            cid = io.get("client_order_id") or io.get("clientOrderId") or str(io.get("id"))
            bid = io.get("broker_order_id")
            bo = broker_by_client.get(str(cid)) or (broker_by_broker_id.get(str(bid)) if bid else None)
            if not bo:
                # No broker counterpart — could be not yet submitted or broker lag
                # If status is SUBMITTED/ACKNOWLEDGED for >30s without broker match → mismatch
                results.append(ReconResult(
                    recon_type="ORDERS", status="MISMATCHED",
                    discrepancy={"internal": io, "broker": None},
                    affected_order_id=cid,
                    should_block=True,
                    message=f"ORDER_MISSING_ON_BROKER:{cid}",
                ))
                continue
            # Compare status
            istatus = io.get("status")
            bstatus = bo.get("status")
            if istatus != bstatus:
                # Broker fill wins over local cancel is expected (§52) — not mismatch if broker is FILLED
                if bstatus in ("FILLED","PARTIALLY_FILLED") and istatus in ("CANCEL_PENDING","CANCELLED"):
                    results.append(ReconResult(
                        recon_type="ORDERS", status="MISMATCHED",
                        discrepancy={"internal_status": istatus, "broker_status": bstatus, "note": "CANCEL_FILL_RACE_BROKER_WINS"},
                        affected_order_id=cid, message="CANCEL_FILL_RACE",
                    ))
                else:
                    results.append(ReconResult(
                        recon_type="ORDERS", status="MISMATCHED",
                        discrepancy={"internal_status": istatus, "broker_status": bstatus},
                        affected_order_id=cid, should_block=True,
                        message=f"ORDER_STATUS_MISMATCH:{istatus}!={bstatus}",
                    ))
                continue
            # Compare quantity/price within tolerance
            iq = io.get("quantity"); bq = bo.get("quantity") or bo.get("fill_quantity")
            if iq is not None and bq is not None and abs(int(iq)-int(bq)) > self.QTY_TOLERANCE and bstatus in ("FILLED","PARTIALLY_FILLED"):
                results.append(ReconResult(
                    recon_type="ORDERS", status="MISMATCHED",
                    discrepancy={"qty_mismatch": f"{iq} != {bq}"}, affected_order_id=cid, should_block=True,
                    message="ORDER_QTY_MISMATCH",
                ))
        # Orphan broker orders not in internal
        internal_cids = {io.get("client_order_id") or io.get("clientOrderId") or str(io.get("id")) for io in internal_orders}
        for bo in broker_orders:
            bcid = bo.get("client_order_id") or bo.get("clientOrderId")
            if bcid and str(bcid) not in internal_cids:
                results.append(ReconResult(
                    recon_type="ORDERS", status="MISMATCHED",
                    discrepancy={"broker_orphan": bo}, should_block=True,
                    message=f"BROKER_ORPHAN_ORDER:{bcid}",
                ))

        if not results:
            return [ReconResult(recon_type="ORDERS", status="MATCHED", message="ORDERS_RECONCILED_OK")]
        return results

    def reconcile_positions(self, internal_positions: list[dict], broker_positions: list[dict]) -> list[ReconResult]:
        results: list[ReconResult] = []
        bmap: dict[str, dict] = {p.get("position_id") or p.get("symbol"): p for p in broker_positions}
        imap: dict[str, dict] = {p.get("position_id") or p.get("symbol"): p for p in internal_positions}

        for pid, ipos in imap.items():
            bpos = bmap.get(pid)
            if not bpos:
                if ipos.get("is_open"):
                    results.append(ReconResult(
                        recon_type="POSITIONS", status="MISMATCHED",
                        discrepancy={"internal": ipos, "broker": None},
                        affected_position_id=pid, should_block=True,
                        message=f"POSITION_MISSING_ON_BROKER:{pid}",
                    ))
                continue
            iq = int(ipos.get("quantity", 0)); bq = int(bpos.get("quantity", bpos.get("qty", 0)))
            if abs(iq - bq) > self.QTY_TOLERANCE:
                results.append(ReconResult(
                    recon_type="POSITIONS", status="MISMATCHED",
                    discrepancy={"qty": f"{iq} vs {bq}"}, affected_position_id=pid, should_block=True,
                    magnitude=D(abs(iq-bq)), message="POSITION_QTY_MISMATCH",
                ))
            # avg price tolerance
            ip = D(ipos.get("average_price", ipos.get("average_entry", 0)) or 0)
            bp = D(bpos.get("average_price", bpos.get("average_entry", 0)) or 0)
            if abs(ip - bp) > self.AMOUNT_TOLERANCE and iq != 0:
                results.append(ReconResult(
                    recon_type="POSITIONS", status="MISMATCHED",
                    discrepancy={"avg_price": f"{ip} vs {bp}"}, affected_position_id=pid, should_block=True,
                    magnitude=abs(ip-bp), message="POSITION_PRICE_MISMATCH",
                ))

        for pid, bpos in bmap.items():
            if pid not in imap and int(bpos.get("quantity", bpos.get("qty", 0))) != 0:
                results.append(ReconResult(
                    recon_type="POSITIONS", status="MISMATCHED",
                    discrepancy={"broker_orphan": bpos}, affected_position_id=pid, should_block=True,
                    message=f"BROKER_ORPHAN_POSITION:{pid}",
                ))

        if not results:
            return [ReconResult(recon_type="POSITIONS", status="MATCHED", message="POSITIONS_RECONCILED_OK")]
        return results

    def reconcile_funds(self, internal_funds: dict, broker_funds: dict) -> ReconResult:
        avail_i = D(internal_funds.get("available_margin", internal_funds.get("available", 0)) or 0)
        avail_b = D(broker_funds.get("available_margin", broker_funds.get("available", 0)) or 0)
        if abs(avail_i - avail_b) > D("1.00"):
            return ReconResult(
                recon_type="FUNDS", status="MISMATCHED",
                discrepancy={"internal_avail": str(avail_i), "broker_avail": str(avail_b)},
                magnitude=abs(avail_i - avail_b), should_block=True,
                message=f"FUNDS_MISMATCH_{avail_i}_vs_{avail_b}",
            )
        return ReconResult(recon_type="FUNDS", status="MATCHED", message="FUNDS_RECONCILED_OK")

    def reconcile_reservations(self, reservations: list[dict], orders: list[dict]) -> list[ReconResult]:
        # Every RESERVED should have a corresponding order not in terminal state
        results: list[ReconResult] = []
        order_by_client = {o.get("client_order_id") or o.get("clientOrderId"): o for o in orders}
        for r in reservations:
            if r.get("status") != "RESERVED":
                continue
            cid = r.get("client_order_id")
            o = order_by_client.get(str(cid))
            if not o:
                results.append(ReconResult(
                    recon_type="RESERVATIONS", status="MISMATCHED",
                    discrepancy={"reservation": r, "order": None},
                    should_block=True, message=f"RESERVATION_ORPHAN:{cid}",
                ))
            elif o.get("status") in ("FILLED","CANCELLED","REJECTED","CLOSED"):
                results.append(ReconResult(
                    recon_type="RESERVATIONS", status="MISMATCHED",
                    discrepancy={"reservation_still_reserved": cid, "order_status": o.get("status")},
                    should_block=False, message=f"RESERVATION_SHOULD_BE_CONSUMED_OR_RELEASED:{cid}",
                ))
        if not results:
            return [ReconResult(recon_type="RESERVATIONS", status="MATCHED", message="RESERVATIONS_RECONCILED_OK")]
        return results

    def health(self, results: list[ReconResult]) -> str:
        """Return reconciliation health: HEALTHY / DEGRADED / BLOCKED"""
        if any(r.should_block for r in results):
            return "BLOCKED"
        if any(r.status == "MISMATCHED" for r in results):
            return "DEGRADED"
        return "HEALTHY"


reconciliation_engine = ReconciliationEngine()
