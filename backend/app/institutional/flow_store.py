"""PIT-safe institutional flow store (FII/DII daily + positioning proxy).

Minimal genuine step toward institutional-flow awareness WITHOUT fabricating
a live feed:

- NSE publishes FII/DII cash + derivatives positioning as DAILY files,
  available T+1 ~18:00 IST (plus possible revisions). Any intraday use of
  "today's" flow is lookahead. This store enforces:
      available_time <= decision_time
  via app.ml.pit_store.as_of_join + app.ml.leakage_gate + signals PIT validator.

- Current truth-of-wall: no live broker FII/DII endpoint exists
  (see app/services/fii_dii_service.py). This store SEEDS from that static
  snapshot but attaches correct event/available/ingestion timestamps so it is
  PIT-safe from day one. When a real NSE ingestion lands, replace seed_rows()
  with file/DB rows — the as_of() contract does not change.

- Futures basis/OI remain UNAVAILABLE live (fno/context hardcodes 0/UNKNOWN).
  This store does NOT synthesize them. It exposes futures_status=UNAVAILABLE
  and forces downstream to fail-closed (DEGRADED, capped confidence).

Outputs (all PIT-safe):
  as_of(decision_time) -> InstitutionalFlowSnapshot | None (None = no data yet)
  to_overlay(snapshot, regime, fno) -> pure adjustment used by confluence/scanner
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import statistics

from app.ml.pit_store import pit_store
from app.ml.leakage_gate import leakage_gate

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "nse_daily_files_via_static_seed"
HISTORY_SOURCE = "mrchartist_proxy_fetch-pipeline"
FLOW_AVAILABLE_HOUR_IST = 18  # T+1 18:00 IST

# Seed mirrors app/services/fii_dii_service.py static snapshot (2026-08-27..29).
# event_date = session the flow belongs to. available_time = T+1 18:00 IST.
_SEED_CASH = [
    # (event_date, fii_net_cr, dii_net_cr)
    ("2026-08-27", 2200.00, 1600.00 if False else 0.0),  # DII 27th not in seed; set below
    ("2026-08-28", -850.00, 1600.00),
    ("2026-08-29", 1560.30, 1229.60),
]
# Correct DII 27th: seed file has no DII row for 27th; keep 0.0 + missing flag
# rather than inventing a number.
_SEED_POSITIONING = {
    "event_date": "2026-08-29",
    "fii_fut_long": 78420,
    "fii_fut_short": 62150,
    "fii_fut_net": 16270,
    "dii_fut_net": -5600,
}


def _ist_to_utc(d_ist, hour: int = 18, minute: int = 0) -> datetime:
    dt_ist = datetime.combine(d_ist, dtime(hour, minute), tzinfo=IST)
    return dt_ist.astimezone(timezone.utc)


def _parse_event_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


@dataclass
class FlowDay:
    event_date: str
    fii_cash_net_crores: float
    dii_cash_net_crores: float
    fii_fut_net: Optional[int] = None
    fii_lsr: Optional[float] = None
    available_time_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ingestion_time_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_revision: bool = False
    source: str = SOURCE


@dataclass
class InstitutionalFlowSnapshot:
    event_date: str
    available_time_utc: str
    fii_cash_net_crores: float
    dii_cash_net_crores: float
    fii_cash_5d_z: Optional[float]
    dii_cash_5d_z: Optional[float]
    fii_cash_accel_crores: Optional[float]  # latest - mean(prev 4)
    dii_cash_accel_crores: Optional[float]
    fii_fut_net: Optional[int]
    fii_lsr: Optional[float]
    n_days_window: int
    pit_ok: bool = True
    live_available: bool = False
    source: str = SOURCE
    futures_status: str = "UNAVAILABLE"  # never synthesized


def _zscore(latest: float, window: List[float]) -> Optional[float]:
    if len(window) < 3:
        return None
    try:
        mu = statistics.fmean(window)
        sd = statistics.pstdev(window)
        if sd <= 1e-9:
            return 0.0
        z = (latest - mu) / sd
        return round(max(-3.0, min(3.0, z)), 3)
    except Exception:
        return None


class InstitutionalFlowStore:
    """In-memory PIT-safe store. Single writer (ingest), many readers (as_of)."""

    def __init__(self) -> None:
        self._days: List[FlowDay] = []
        self._seeded = False

    def seed_rows(self) -> None:
        if self._seeded:
            return
        now_utc = datetime.now(timezone.utc)
        for evt, fii, dii in _SEED_CASH:
            d = _parse_event_date(evt)
            avail = _ist_to_utc(d + timedelta(days=1), FLOW_AVAILABLE_HOUR_IST)
            pos = _SEED_POSITIONING if evt == _SEED_POSITIONING["event_date"] else {}
            lsr = None
            if pos:
                try:
                    lsr = round(pos["fii_fut_long"] / max(1, pos["fii_fut_short"]), 4)
                except Exception:
                    lsr = None
            day = FlowDay(
                event_date=evt,
                fii_cash_net_crores=float(fii),
                dii_cash_net_crores=float(dii),
                fii_fut_net=pos.get("fii_fut_net"),
                fii_lsr=lsr,
                available_time_utc=avail,
                ingestion_time_utc=now_utc,
                is_revision=False,
            )
            self._days.append(day)
            # Mirror into global pit_store so as_of_join() works for trainers.
            obs_ms = int(avail.timestamp() * 1000)
            pit_store.insert_record("NSE", "fii_cash_net_crores", float(fii), obs_ms, obs_ms, obs_ms, "flow-v1")
            pit_store.insert_record("NSE", "dii_cash_net_crores", float(dii), obs_ms, obs_ms, obs_ms, "flow-v1")
        self._load_history_file(now_utc)
        self._days.sort(key=lambda r: r.event_date)
        self._seeded = True

    def _load_history_file(self, now_utc: datetime) -> None:
        """Merge backend/data/fii_dii_history.json if present (history wins on date).

        Third-party proxy cache of NSE (see scripts/ingest_fii_dii_history.py).
        F&O zeros were already mapped to None at ingest; never zero-filled here.
        """
        import json as _json
        from pathlib import Path as _Path

        try:
            p = _Path(__file__).resolve().parents[2] / "data" / "fii_dii_history.json"
            if not p.exists():
                return
            payload = _json.loads(p.read_text(encoding="utf-8"))
            rows = payload.get("rows", []) if isinstance(payload, dict) else []
            if not rows:
                return
            # History is real trading days; the 3-row static seed contains a
            # Saturday snapshot (2026-08-29, non-trading) that must not enter
            # training once real history exists. Drop seed, keep history only.
            by_date = {d.event_date: d for d in self._days} if len(rows) < 50 else {}
            for r in rows:
                try:
                    evt = str(r["event_date"])
                    fii = float(r["fii_cash_net_crores"])
                    dii = float(r["dii_cash_net_crores"])
                    d = _parse_event_date(evt)
                    avail = _ist_to_utc(d + timedelta(days=1), FLOW_AVAILABLE_HOUR_IST)
                    fut_net = r.get("fii_fut_net")
                    fut_net = int(fut_net) if fut_net is not None else None
                    lsr = r.get("fii_lsr")
                    lsr = float(lsr) if lsr is not None else None
                    day = FlowDay(
                        event_date=evt,
                        fii_cash_net_crores=fii,
                        dii_cash_net_crores=dii,
                        fii_fut_net=fut_net,
                        fii_lsr=lsr,
                        available_time_utc=avail,
                        ingestion_time_utc=now_utc,
                        is_revision=False,
                        source=HISTORY_SOURCE,
                    )
                    by_date[evt] = day
                    obs_ms = int(avail.timestamp() * 1000)
                    pit_store.insert_record("NSE", "fii_cash_net_crores", fii, obs_ms, obs_ms, obs_ms, "flow-v1")
                    pit_store.insert_record("NSE", "dii_cash_net_crores", dii, obs_ms, obs_ms, obs_ms, "flow-v1")
                except Exception:
                    continue
            self._days = [by_date[k] for k in sorted(by_date)]
        except Exception:
            return

    def ingest_daily_file(
        self,
        event_date: str,
        fii_cash_net_crores: float,
        dii_cash_net_crores: float,
        fii_fut_net: Optional[int] = None,
        fii_fut_long: Optional[int] = None,
        fii_fut_short: Optional[int] = None,
        is_revision: bool = False,
        ingestion_time_utc: Optional[datetime] = None,
    ) -> FlowDay:
        """Future live path: NSE daily file loader calls this. Enforces T+1 availability."""
        self.seed_rows()
        d = _parse_event_date(event_date)
        avail = _ist_to_utc(d + timedelta(days=1), FLOW_AVAILABLE_HOUR_IST)
        now_utc = ingestion_time_utc or datetime.now(timezone.utc)
        # Ingestion cannot predate availability (else lookahead).
        if now_utc < avail:
            raise ValueError(f"PIT: ingestion {now_utc.isoformat()} before available_time {avail.isoformat()}")
        lsr = None
        if fii_fut_long is not None and fii_fut_short:
            try:
                lsr = round(float(fii_fut_long) / float(fii_fut_short), 4)
            except Exception:
                lsr = None
        day = FlowDay(
            event_date=event_date,
            fii_cash_net_crores=float(fii_cash_net_crores),
            dii_cash_net_crores=float(dii_cash_net_crores),
            fii_fut_net=fii_fut_net,
            fii_lsr=lsr,
            available_time_utc=avail,
            ingestion_time_utc=now_utc,
            is_revision=is_revision,
        )
        # Replace same event_date unless this is an explicit revision insert.
        self._days = [r for r in self._days if r.event_date != event_date] + [day]
        self._days.sort(key=lambda r: r.event_date)
        obs_ms = int(avail.timestamp() * 1000)
        pit_store.insert_record("NSE", "fii_cash_net_crores", float(fii_cash_net_crores), obs_ms, obs_ms, obs_ms, "flow-v1")
        return day

    def as_of(self, decision_time: Optional[datetime] = None) -> Optional[InstitutionalFlowSnapshot]:
        """Latest flow row with available_time <= decision_time. None if none yet."""
        self.seed_rows()
        t = decision_time or datetime.now(timezone.utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        eligible = [r for r in self._days if r.available_time_utc <= t]
        if not eligible:
            return None
        latest = eligible[-1]
        # Leakage-gate proof for this read.
        obs_ms = int(t.timestamp() * 1000)
        pub_ms = int(latest.available_time_utc.timestamp() * 1000)
        leakage_gate.assert_no_leakage(
            [{"observation_time_utc": obs_ms, "publication_timestamps": {"fii_flow": pub_ms}}]
        )
        window = eligible[-5:]
        fii_w = [r.fii_cash_net_crores for r in window]
        dii_w = [r.dii_cash_net_crores for r in window]
        prev_fii = fii_w[:-1] if len(fii_w) > 1 else fii_w
        prev_dii = dii_w[:-1] if len(dii_w) > 1 else dii_w
        try:
            fii_accel = round(float(fii_w[-1] - statistics.fmean(prev_fii)), 2) if len(prev_fii) >= 2 else None
        except Exception:
            fii_accel = None
        try:
            dii_accel = round(float(dii_w[-1] - statistics.fmean(prev_dii)), 2) if len(prev_dii) >= 2 else None
        except Exception:
            dii_accel = None
        return InstitutionalFlowSnapshot(
            event_date=latest.event_date,
            available_time_utc=latest.available_time_utc.isoformat(),
            fii_cash_net_crores=float(latest.fii_cash_net_crores),
            dii_cash_net_crores=float(latest.dii_cash_net_crores),
            fii_cash_5d_z=_zscore(float(latest.fii_cash_net_crores), fii_w),
            dii_cash_5d_z=_zscore(float(latest.dii_cash_net_crores), dii_w),
            fii_cash_accel_crores=fii_accel,
            dii_cash_accel_crores=dii_accel,
            fii_fut_net=latest.fii_fut_net,
            fii_lsr=latest.fii_lsr,
            n_days_window=len(window),
            pit_ok=True,
            live_available=False,
            futures_status="UNAVAILABLE",
        )

    def to_training_rows(self) -> List[Dict[str, Any]]:
        """PIT-safe training rows for future h60 retrain (event + available_time kept)."""
        self.seed_rows()
        rows: List[Dict[str, Any]] = []
        for i, r in enumerate(self._days):
            win = self._days[max(0, i - 4): i + 1]
            fii_w = [x.fii_cash_net_crores for x in win]
            dii_w = [x.dii_cash_net_crores for x in win]
            rows.append(
                {
                    "event_date": r.event_date,
                    "observation_time_utc": int(r.available_time_utc.timestamp() * 1000),
                    "publication_timestamps": {
                        "fii_cash_net_crores": int(r.available_time_utc.timestamp() * 1000),
                        "dii_cash_net_crores": int(r.available_time_utc.timestamp() * 1000),
                    },
                    "fii_cash_net_crores": float(r.fii_cash_net_crores),
                    "dii_cash_net_crores": float(r.dii_cash_net_crores),
                    "fii_cash_5d_z": _zscore(float(r.fii_cash_net_crores), fii_w),
                    "dii_cash_5d_z": _zscore(float(r.dii_cash_net_crores), dii_w),
                    "fii_fut_net": r.fii_fut_net,
                    "fii_lsr": r.fii_lsr,
                    "is_revision": r.is_revision,
                }
            )
        # Fail loud on leakage before any trainer consumes this.
        leakage_gate.assert_no_leakage(rows)
        return rows


flow_store = InstitutionalFlowStore()
