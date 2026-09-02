"""HPI service — selection, retention policies, storage budget, import,
scope-isolated deletion with audit, auto-delete, and coverage reporting.

Core principle (§17): the user chooses which historical derivative data to
keep; the system validates, estimates storage, enforces retention, analyses,
and audits — nothing else.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.hpi import constants as C
from app.hpi.models import (
    CategoryDeletePreview, CategoryEstimate, CategoryStats, CoverageReport,
    DatasetCard, DatasetCoverage, DeletePreview, DeleteRequest, DeleteResult,
    DeletionAuditEntry, DerivativeSelectionEntry, DerivativeSelectionState,
    ImportPreview, ImportRequest, ImportResult, RetentionPolicy,
    RetentionPolicyUpdate, StorageReport,
)
from app.hpi.store import HPIRecordStore
import structlog

logger = structlog.get_logger()

CANDLE_CATEGORIES = {"1m_market_data", "futures"}
BASE_PRICES = {
    "NIFTY": 24000.0, "BANKNIFTY": 51000.0, "FINNIFTY": 23000.0,
    "SENSEX": 79000.0, "BTC": 65000.0, "ETH": 3200.0, "SOL": 150.0,
}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Real crypto historical data (Binance public klines) with synthetic fallback.
# BTC/ETH/SOL 1m market data uses real exchange candles; anything else falls
# back to deterministic synthetic records (demo provider).
# ---------------------------------------------------------------------------
ENABLE_REAL_CRYPTO = True
REAL_CRYPTO_INTERVALS = {60: "1m", 300: "5m", 900: "15m", 3600: "1h", 86400: "1d"}
REAL_CRYPTO_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}


def _fetch_real_crypto_candles(
    symbol: str, interval_seconds: int, start: datetime, end: datetime
) -> list[tuple] | None:
    """Real OHLCV candles from Binance public API. Returns None on any failure."""
    import httpx

    interval = REAL_CRYPTO_INTERVALS.get(int(interval_seconds))
    pair = REAL_CRYPTO_SYMBOLS.get(symbol.upper())
    if not interval or not pair:
        return None
    cur_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    out: list[tuple] = []
    try:
        with httpx.Client(timeout=10) as client:
            while cur_ms < end_ms:
                r = client.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": pair, "interval": interval,
                            "startTime": cur_ms, "endTime": end_ms, "limit": 1000},
                )
                if r.status_code != 200:
                    return None
                rows = r.json()
                if not rows:
                    break
                for row in rows:
                    out.append((
                        round(row[0] / 1000, 3),
                        float(row[1]), float(row[2]),
                        float(row[3]), float(row[4]), float(row[5]),
                    ))
                last_ms = int(rows[-1][0])
                if last_ms <= cur_ms:
                    break
                cur_ms = last_ms + 1
    except Exception:
        return None
    return out or None


class HPIValidationError(ValueError):
    """User-input validation failure (HTTP 400)."""


class HPIBudgetBlocked(PermissionError):
    """Projected storage exceeds the hard ceiling (HTTP 409, §10)."""

    def __init__(self, estimate: ImportPreview):
        super().__init__(
            f"Projected storage {estimate.projected_storage_mb:.1f} MB exceeds the "
            f"{C.STORAGE_HARD_CEILING_MB:.0f} MB hard ceiling. Choose an alternative before continuing."
        )
        self.estimate = estimate


class HPIService:
    def __init__(self, store: HPIRecordStore | None = None, state_path=None):
        self.store = store or HPIRecordStore(state_path=state_path)
        self._selection: dict[str, DerivativeSelectionEntry] = {}
        self._policies: dict[str, RetentionPolicy] = {}
        self._audit: list[DeletionAuditEntry] = []
        self._pending_deletes: dict[str, DeleteRequest] = {}
        self._running = False
        self._sweep_task: asyncio.Task | None = None
        self._sync_task: asyncio.Task | None = None
        self._seeded: bool = False
        self._load()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        extra = self.store.load_state()
        for e in extra.get("selection", []):
            entry = DerivativeSelectionEntry(**e)
            if entry.symbol in C.HPI_UNIVERSE:
                self._selection[entry.symbol] = entry
        for p in extra.get("policies", []):
            pol = RetentionPolicy(**p)
            if pol.instrument in C.HPI_UNIVERSE:
                self._policies[pol.policy_id] = pol
        for a in extra.get("audit", []):
            if a.get("derivative") in C.HPI_UNIVERSE:
                self._audit.append(DeletionAuditEntry(**a))
        self._seeded = bool(extra.get("seeded", False))

        # Default selection: enable NIFTY, BANKNIFTY, SENSEX
        for sym in C.HPI_UNIVERSE:
            if sym not in self._selection:
                self._selection[sym] = DerivativeSelectionEntry(
                    symbol=sym,
                    enabled=True,
                    data_categories=C.categories_for(sym),
                )

    def save_state(self) -> None:
        self.store.save_state({
            "selection": [e.model_dump(mode="json") for e in self._selection.values() if e.symbol in C.HPI_UNIVERSE],
            "policies": [p.model_dump(mode="json") for p in self._policies.values() if p.instrument in C.HPI_UNIVERSE],
            "audit": [a.model_dump(mode="json") for a in self._audit if a.derivative in C.HPI_UNIVERSE],
            "seeded": self._seeded,
        })
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                if self._sync_task and not self._sync_task.done():
                    self._sync_task.cancel()
                self._sync_task = asyncio.create_task(self._debounced_sync_to_db())
        except RuntimeError:
            pass

    async def _debounced_sync_to_db(self) -> None:
        try:
            await asyncio.sleep(1.0)
            from app.hpi.hpi_persistence import persist_hpi_to_db
            await asyncio.wait_for(
                persist_hpi_to_db(
                    records_map=dict(self.store._records),
                    deleted_ranges=dict(self.store._deleted_ranges),
                    selection=[e.model_dump(mode="json") for e in self._selection.values() if e.symbol in C.HPI_UNIVERSE],
                    policies=[p.model_dump(mode="json") for p in self._policies.values() if p.instrument in C.HPI_UNIVERSE],
                    audit=[a.model_dump(mode="json") for a in self._audit if a.derivative in C.HPI_UNIVERSE],
                    seeded=self._seeded,
                ),
                timeout=15.0,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("hpi_sync_to_db_error", error=str(e)[:200])

    # ------------------------------------------------------------------
    # §1/§2 — Derivative selection
    # ------------------------------------------------------------------
    def get_selection(self) -> DerivativeSelectionState:
        entries = [self._selection.get(sym) or DerivativeSelectionEntry(symbol=sym) for sym in C.HPI_UNIVERSE]
        return DerivativeSelectionState(entries=entries)

    def update_selection(self, entries: list[DerivativeSelectionEntry]) -> DerivativeSelectionState:
        for entry in entries:
            sym = entry.symbol.upper()
            if sym not in C.HPI_UNIVERSE:
                raise HPIValidationError(
                    f"Unsupported derivative '{sym}'. Allowed: {', '.join(C.HPI_UNIVERSE)}"
                )
            allowed = C.categories_for(sym)
            bad = [c for c in entry.data_categories if c not in allowed]
            if bad:
                raise HPIValidationError(f"Invalid data categories for {sym}: {bad}")
            # Disabling keeps existing data & policies untouched (§2).
            self._selection[sym] = entry.model_copy(update={"symbol": sym})
        self.save_state()
        logger.info("hpi_selection_updated", enabled=[s for s, e in self._selection.items() if e.enabled])
        return self.get_selection()

    def is_enabled(self, symbol: str) -> bool:
        entry = self._selection.get(symbol.upper())
        return bool(entry and entry.enabled)

    def enabled_categories(self, symbol: str) -> list[str]:
        entry = self._selection.get(symbol.upper())
        if not entry or not entry.enabled:
            return []
        return [c for c in C.categories_for(symbol) if c in entry.data_categories]

    # ------------------------------------------------------------------
    # §11 — Retention policies
    # ------------------------------------------------------------------
    def list_policies(self, symbol: str | None = None) -> list[RetentionPolicy]:
        pols = list(self._policies.values())
        if symbol:
            pols = [p for p in pols if p.instrument == symbol.upper()]
        return sorted(pols, key=lambda p: (p.instrument, p.feature_group))

    def create_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        if policy.instrument.upper() not in C.HPI_UNIVERSE:
            raise HPIValidationError(f"Unsupported derivative '{policy.instrument}'")
        if policy.feature_group not in C.categories_for(policy.instrument):
            raise HPIValidationError(f"Invalid feature group '{policy.feature_group}'")
        if policy.sampling_interval not in C.SAMPLING_INTERVALS:
            raise HPIValidationError(f"Invalid sampling interval '{policy.sampling_interval}'")
        policy.instrument = policy.instrument.upper()
        policy.derivative_category = C.HPI_DERIVATIVES[policy.instrument]["asset_class"]
        self._policies[policy.policy_id] = policy
        self.save_state()
        return policy

    def update_policy(self, policy_id: str, update: RetentionPolicyUpdate) -> RetentionPolicy:
        pol = self._policies.get(policy_id)
        if not pol:
            raise HPIValidationError(f"Policy '{policy_id}' not found")
        changes = update.model_dump(exclude_unset=True)
        if "sampling_interval" in changes and changes["sampling_interval"] not in C.SAMPLING_INTERVALS:
            raise HPIValidationError(f"Invalid sampling interval '{changes['sampling_interval']}'")
        updated = pol.model_copy(update={**changes, "updated_at": datetime.now(timezone.utc)})
        self._policies[policy_id] = updated
        self.save_state()
        return updated

    def delete_policy(self, policy_id: str) -> bool:
        if policy_id in self._policies:
            del self._policies[policy_id]
            self.save_state()
            return True
        return False

    def policy_for(self, symbol: str, category: str) -> RetentionPolicy | None:
        sym = symbol.upper()
        for pol in self._policies.values():
            if pol.instrument == sym and pol.feature_group == category:
                return pol
        return None

    # ------------------------------------------------------------------
    # Period & generation helpers (§3/§4)
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def resolve_import_period(self, req: ImportRequest) -> tuple[datetime, datetime]:
        end = self._ensure_utc(req.end_date) or datetime.now(timezone.utc)
        start = self._ensure_utc(req.start_date)
        if start is None and req.retention_days:
            start = end - timedelta(days=req.retention_days)
        if start is None:
            raise HPIValidationError("Provide start_date/end_date or retention_days")
        if start >= end:
            raise HPIValidationError("start_date must be before end_date")
        return start, end

    @staticmethod
    def resolve_delete_range(req: DeleteRequest, now: datetime | None = None) -> tuple[datetime, datetime]:
        now = now or datetime.now(timezone.utc)
        if req.range_type == "last_30_days":
            return now - timedelta(days=30), now
        if req.range_type == "last_3_months":
            return now - timedelta(days=90), now
        if req.range_type == "older_than_6_months":
            return EPOCH, now - timedelta(days=180)
        if req.range_type == "all_time":
            return EPOCH, now
        start = HPIService._ensure_utc(req.start_date)
        end = HPIService._ensure_utc(req.end_date) or now
        if start is None:
            raise HPIValidationError("Custom range requires start_date (and optionally end_date)")
        if start >= end:
            raise HPIValidationError("start_date must be before end_date")
        return start, end

    @staticmethod
    def _generate_records(symbol: str, category: str, start: datetime, end: datetime, interval_seconds: int) -> list[tuple]:
        """Historical records: real Binance candles for crypto market data,
        deterministic synthetic otherwise (demo data provider)."""
        # Real exchange candles for crypto 1m market data when available.
        if (
            ENABLE_REAL_CRYPTO
            and category == "1m_market_data"
            and C.HPI_DERIVATIVES.get(symbol.upper(), {}).get("asset_class") == "CRYPTO"
        ):
            real = _fetch_real_crypto_candles(symbol, interval_seconds, start, end)
            if real:
                return real

        rng = random.Random(f"{symbol}:{category}:{interval_seconds}")
        is_candle = category in CANDLE_CATEGORIES
        n = int((end - start).total_seconds() // interval_seconds) + 1
        base = BASE_PRICES.get(symbol.upper(), 100.0)
        price = base * (0.9 + 0.2 * rng.random())
        t0 = start.timestamp()
        recs: list[tuple] = []
        for i in range(n):
            t = round(t0 + i * interval_seconds, 3)
            if is_candle:
                o = price
                c = price * (1 + rng.gauss(0, 0.0008))
                h = max(o, c) * (1 + abs(rng.gauss(0, 0.0004)))
                low = min(o, c) * (1 - abs(rng.gauss(0, 0.0004)))
                v = float(int(rng.uniform(1000, 50000)))
                recs.append((t, round(o, 2), round(h, 2), round(low, 2), round(c, 2), v))
                price = c
            else:
                recs.append((t, round(rng.uniform(0, 100), 4)))
        return recs

    # ------------------------------------------------------------------
    # §10 — Storage budget estimation
    # ------------------------------------------------------------------
    def current_storage_mb(self) -> float:
        return round(self.store.total_storage_bytes() / (1024 * 1024), 2)

    @staticmethod
    def evaluate_budget(projected_mb: float) -> str:
        if projected_mb > C.STORAGE_HARD_CEILING_MB:
            return "EXCEEDS_HARD"
        if projected_mb > C.STORAGE_WARNING_MB:
            return "WARNING"
        return "WITHIN_TARGET"

    def _estimate_categories(
        self, symbol: str, categories: list[str], start: datetime, end: datetime, sampling: str
    ) -> list[CategoryEstimate]:
        seconds = C.SAMPLING_INTERVALS[sampling]
        span = (end - start).total_seconds()
        out: list[CategoryEstimate] = []
        for cat in categories:
            n = int(span // seconds) + 1
            out.append(CategoryEstimate(
                symbol=symbol.upper(),
                category=cat,
                label=C.CATEGORY_LABELS.get(cat, cat),
                estimated_records=n,
                estimated_mb=round(n * C.BYTES_PER_RECORD.get(cat, 32) / (1024 * 1024), 2),
                sampling_interval=sampling,
            ))
        return out

    def _apply_policy_defaults(self, symbol: str, categories: list[str], req: ImportRequest) -> str:
        """Sampling resolution order: request → per-category policy → default 5m."""
        if req.sampling_interval and req.sampling_interval != "5m":
            return req.sampling_interval
        for cat in categories:
            pol = self.policy_for(symbol, cat)
            if pol:
                return pol.sampling_interval
        return "5m"

    def estimate_import(self, req: ImportRequest) -> ImportPreview:
        """Estimate storage impact before enabling a dataset / importing (§10)."""
        sym = req.symbol.upper()
        if sym not in C.HPI_UNIVERSE:
            raise HPIValidationError(f"Unsupported derivative '{sym}'. Allowed: {', '.join(C.HPI_UNIVERSE)}")
        categories = [c for c in req.categories if c] or C.categories_for(sym)
        allowed = C.categories_for(sym)
        bad = [c for c in categories if c not in allowed]
        if bad:
            raise HPIValidationError(f"Invalid data categories for {sym}: {bad}")
        sampling = self._apply_policy_defaults(sym, categories, req)
        if sampling not in C.SAMPLING_INTERVALS:
            raise HPIValidationError(f"Invalid sampling interval '{sampling}'")
        start, end = self.resolve_import_period(req)

        breakdown = self._estimate_categories(sym, categories, start, end, sampling)
        warnings: list[str] = []
        for b in breakdown:
            if b.estimated_records > C.MAX_IMPORT_RECORDS_PER_DATASET:
                warnings.append(
                    f"{b.label}: {b.estimated_records:,} records exceeds the "
                    f"{C.MAX_IMPORT_RECORDS_PER_DATASET:,}-record per-dataset cap — reduce the period or "
                    f"increase the sampling interval."
                )
        requested = round(sum(b.estimated_mb for b in breakdown), 2)
        current = self.current_storage_mb()
        projected = round(current + requested, 2)
        status = self.evaluate_budget(projected)
        blocked = status == "EXCEEDS_HARD"
        return ImportPreview(
            current_storage_mb=current,
            requested_addition_mb=requested,
            projected_storage_mb=projected,
            status=status,
            blocked=blocked,
            alternatives=C.STORAGE_ALTERNATIVES if blocked else [],
            breakdown=breakdown,
            symbol=sym,
            sampling_interval=sampling,
            period_start=start,
            period_end=end,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # §16 — Historical import workflow
    # ------------------------------------------------------------------
    def run_import(self, req: ImportRequest) -> ImportResult | ImportPreview:
        if req.estimate_only:
            return self.estimate_import(req)
        preview = self.estimate_import(req)
        if preview.warnings:
            raise HPIValidationError("; ".join(preview.warnings))
        if preview.blocked:
            raise HPIBudgetBlocked(preview)
        entry = self._selection.get(preview.symbol)
        if not entry:
            self._selection[preview.symbol] = DerivativeSelectionEntry(
                symbol=preview.symbol,
                enabled=True,
                data_categories=[b.category for b in preview.breakdown],
            )
        else:
            entry.enabled = True
            entry.data_categories = list(set(entry.data_categories + [b.category for b in preview.breakdown]))

        imported = 0
        added_bytes = 0
        for b in preview.breakdown:
            recs = self._generate_records(
                preview.symbol, b.category, preview.period_start, preview.period_end,
                C.SAMPLING_INTERVALS[b.sampling_interval],
            )
            # Re-import over the same window refreshes (replaces) that window.
            self.store.delete_range(
                preview.symbol, b.category,
                preview.period_start.timestamp(), preview.period_end.timestamp(),
            )
            self.store.append(preview.symbol, b.category, recs)
            imported += len(recs)
            added_bytes += len(recs) * C.BYTES_PER_RECORD.get(b.category, 32)
        self.save_state()
        logger.info("hpi_import_completed", symbol=preview.symbol, records=imported)
        return ImportResult(
            symbol=preview.symbol,
            imported_categories=[b.category for b in preview.breakdown],
            records_imported=imported,
            storage_added_mb=round(added_bytes / (1024 * 1024), 2),
            total_storage_mb=round(self.current_storage_mb(), 2),
            status=preview.status,
            sampling_interval=preview.sampling_interval,
            period_start=preview.period_start,
            period_end=preview.period_end,
        )

    # ------------------------------------------------------------------
    # One-click bootstrap — load ALL derivatives' history in one go.
    # ------------------------------------------------------------------
    def seed_defaults(self, force: bool = False, sampling_interval: str = "1h",
                      retention_days: int = 180) -> dict:
        """Enable all 7 derivatives (all categories) and import history for each.

        Safe to run any time: re-imports replace the same window, so storage
        never silently grows. Returns a summary + storage report.
        """
        if self._seeded and not force:
            return {
                "status": "already_seeded",
                "info": "Derivative history already loaded.",
                "records_imported": 0,
                "storage_mb": self.current_storage_mb(),
            }

        entries = [
            DerivativeSelectionEntry(symbol=sym, enabled=True, data_categories=C.categories_for(sym))
            for sym in C.HPI_UNIVERSE
        ]
        self.update_selection(entries)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=retention_days)
        total = 0
        for sym in C.HPI_UNIVERSE:
            res = self.run_import(ImportRequest(
                symbol=sym, categories=C.categories_for(sym),
                start_date=start, end_date=end, sampling_interval=sampling_interval,
            ))
            total += res.records_imported
        self._seeded = True
        self.save_state()
        logger.info("hpi_seeded", records=total, sampling=sampling_interval, days=retention_days)
        return {
            "status": "seeded",
            "records_imported": total,
            "storage_mb": self.current_storage_mb(),
            "sampling_interval": sampling_interval,
            "retention_days": retention_days,
        }

    def is_seeded(self) -> bool:
        return self._seeded

    def capture_live_record(self, symbol: str, category: str, payload: tuple) -> bool:
        """Live collection gate — rejects new data for disabled derivatives (§2)."""
        sym = symbol.upper()
        if sym not in C.HPI_UNIVERSE or not self.is_enabled(sym):
            return False
        if category not in self.enabled_categories(sym):
            return False
        self.store.append(sym, category, [payload])
        return True

    # ------------------------------------------------------------------
    # §6/§7/§8 — Delete preview, confirmation, and execution
    # ------------------------------------------------------------------
    def preview_delete(self, req: DeleteRequest) -> DeletePreview:
        sym = req.symbol.upper()
        if sym not in C.HPI_UNIVERSE:
            raise HPIValidationError(f"Unsupported derivative '{sym}'")
        if not req.categories:
            raise HPIValidationError("Select at least one data category to delete")
        allowed = C.categories_for(sym)
        bad = [c for c in req.categories if c not in allowed]
        if bad:
            raise HPIValidationError(f"Invalid data categories for {sym}: {bad}")
        start, end = self.resolve_delete_range(req)

        per_category: list[CategoryDeletePreview] = []
        protected: list[str] = []
        for cat in req.categories:
            s_ts, e_ts = start.timestamp(), end.timestamp()
            count = sum(1 for r in self.store.records(sym, cat) if s_ts <= r[0] <= e_ts)
            per_category.append(CategoryDeletePreview(
                category=cat,
                label=C.CATEGORY_LABELS.get(cat, cat),
                records=count,
                storage_mb=round(count * C.BYTES_PER_RECORD.get(cat, 32) / (1024 * 1024), 2),
            ))
            pol = self.policy_for(sym, cat)
            if pol and pol.protected:
                protected.append(cat)

        import uuid as _uuid
        token = _uuid.uuid4().hex
        self._pending_deletes[token] = req.model_copy(deep=True)
        impact = [C.CATEGORY_IMPACT.get(cat, f"{cat} unavailable for this period.") for cat in req.categories]
        return DeletePreview(
            symbol=sym,
            categories=list(req.categories),
            range_type=req.range_type,
            range_start=start,
            range_end=end,
            total_records=sum(p.records for p in per_category),
            total_storage_mb=round(sum(p.storage_mb for p in per_category), 2),
            per_category=per_category,
            analytical_impact=impact,
            price_technical_impact=C.PRICE_TECH_IMPACT,
            protected_categories=protected,
            confirmation_token=token,
        )

    def confirm_delete(self, token: str, user_id: str = "system", reason: str | None = None) -> DeleteResult:
        """Execute a previously previewed deletion. Two-step — no accidental clicks (§7)."""
        req = self._pending_deletes.pop(token, None)
        if req is None:
            raise HPIValidationError("Invalid or expired confirmation token — request a new delete preview")
        sym = req.symbol.upper()
        start, end = self.resolve_delete_range(req)
        s_ts, e_ts = start.timestamp(), end.timestamp()

        total_deleted = 0
        total_bytes = 0
        audit_ids: list[str] = []
        for cat in req.categories:
            pol = self.policy_for(sym, cat)
            if pol and pol.protected and not req.allow_protected:
                # §13 — protected data is never deleted without explicit opt-in.
                logger.warning("hpi_delete_skipped_protected", symbol=sym, category=cat)
                continue
            deleted, released = self.store.delete_range(sym, cat, s_ts, e_ts)
            total_deleted += deleted
            total_bytes += released
            if deleted > 0:
                self.store.mark_deleted_range(sym, cat, start, end)
            entry = DeletionAuditEntry(
                user_id=user_id,
                derivative=sym,
                dataset=cat,
                start_date=start,
                end_date=end,
                records_deleted=deleted,
                storage_released_mb=round(released / (1024 * 1024), 2),
                reason=reason or req.reason or f"manual_delete:{req.range_type}",
            )
            self._audit.append(entry)
            audit_ids.append(entry.deletion_id)
        self.save_state()
        logger.info("hpi_deletion_executed", symbol=sym, records=total_deleted)
        return DeleteResult(
            deleted=True,
            audit_ids=audit_ids,
            records_deleted=total_deleted,
            storage_released_mb=round(total_bytes / (1024 * 1024), 2),
        )

    def list_audit(self, symbol: str | None = None) -> list[DeletionAuditEntry]:
        entries = self._audit
        if symbol:
            entries = [a for a in entries if a.derivative == symbol.upper()]
        return list(reversed(entries))

    # ------------------------------------------------------------------
    # §12/§13 — Automatic deletion & protection
    # ------------------------------------------------------------------
    def run_auto_delete(self, now: datetime | None = None) -> list[DeletionAuditEntry]:
        """Delete records older than each policy's retention period — only for
        datasets where auto_delete_enabled=ON and protected=OFF."""
        now = now or datetime.now(timezone.utc)
        entries: list[DeletionAuditEntry] = []
        for pol in self._policies.values():
            if not pol.enabled or not pol.auto_delete_enabled or pol.protected:
                continue
            cutoff = now - timedelta(days=pol.retention_days)
            deleted, released = self.store.delete_range(pol.instrument, pol.feature_group, 0.0, cutoff.timestamp())
            if deleted:
                self.store.mark_deleted_range(pol.instrument, pol.feature_group, EPOCH, cutoff)
                entry = DeletionAuditEntry(
                    derivative=pol.instrument,
                    dataset=pol.feature_group,
                    start_date=EPOCH,
                    end_date=cutoff,
                    records_deleted=deleted,
                    storage_released_mb=round(released / (1024 * 1024), 2),
                    reason="auto_delete",
                )
                self._audit.append(entry)
                entries.append(entry)
        if entries:
            self.save_state()
        return entries

    # ------------------------------------------------------------------
    # §5 — Derivative data management report
    # ------------------------------------------------------------------
    def get_storage_report(self) -> StorageReport:
        cards: list[DatasetCard] = []
        for sym in C.HPI_UNIVERSE:
            entry = self._selection.get(sym) or DerivativeSelectionEntry(symbol=sym)
            meta = C.HPI_DERIVATIVES[sym]
            cat_stats: list[CategoryStats] = []
            total_records = 0
            oldest: datetime | None = None
            newest: datetime | None = None
            auto_flags: list[bool] = []
            protected_any = False
            sampling: str | None = None
            for cat in C.categories_for(sym):
                o_ts, n_ts = self.store.oldest_newest(sym, cat)
                count = self.store.count(sym, cat)
                pol = self.policy_for(sym, cat)
                cat_stats.append(CategoryStats(
                    category=cat,
                    label=C.CATEGORY_LABELS.get(cat, cat),
                    enabled=cat in entry.data_categories,
                    records=count,
                    storage_mb=round(self.store.storage_bytes(sym, cat) / (1024 * 1024), 2),
                    oldest=datetime.fromtimestamp(o_ts, tz=timezone.utc) if o_ts else None,
                    newest=datetime.fromtimestamp(n_ts, tz=timezone.utc) if n_ts else None,
                    auto_delete_enabled=bool(pol and pol.auto_delete_enabled),
                    protected=bool(pol and pol.protected),
                    retention_days=pol.retention_days if pol else None,
                ))
                total_records += count
                if o_ts and (oldest is None or o_ts < oldest.timestamp()):
                    oldest = datetime.fromtimestamp(o_ts, tz=timezone.utc)
                if n_ts and (newest is None or n_ts > newest.timestamp()):
                    newest = datetime.fromtimestamp(n_ts, tz=timezone.utc)
                if pol:
                    auto_flags.append(pol.auto_delete_enabled)
                    protected_any = protected_any or pol.protected
                    if count:
                        sampling = pol.sampling_interval
            period_months = None
            if oldest and newest:
                period_months = round((newest - oldest).total_seconds() / (30 * 86400), 1)
            cards.append(DatasetCard(
                symbol=sym,
                display_name=meta["display_name"],
                enabled=entry.enabled,
                data_categories_enabled=list(entry.data_categories),
                historical_period_months=period_months,
                sampling_interval=sampling,
                records_stored=total_records,
                storage_used_mb=round(sum(s.storage_mb for s in cat_stats), 2),
                oldest_record=oldest,
                newest_record=newest,
                protected=protected_any,
                auto_delete_status="ON" if auto_flags and all(auto_flags) else ("PARTIAL" if any(auto_flags) else "OFF"),
                category_stats=cat_stats,
            ))
        current = self.current_storage_mb()
        return StorageReport(
            current_storage_mb=current,
            target_mb=C.STORAGE_TARGET_MB,
            warning_mb=C.STORAGE_WARNING_MB,
            hard_ceiling_mb=C.STORAGE_HARD_CEILING_MB,
            status=self.evaluate_budget(current),
            seeded=self._seeded,
            datasets=cards,
        )

    # ------------------------------------------------------------------
    # §9/§15 — Historical coverage
    # ------------------------------------------------------------------
    def get_coverage(self, symbol: str) -> CoverageReport:
        sym = symbol.upper()
        enabled = self.is_enabled(sym)
        datasets: list[DatasetCoverage] = []
        missing: list[str] = []
        deleted_notes: list[str] = []
        for cat in C.categories_for(sym):
            o_ts, n_ts = self.store.oldest_newest(sym, cat)
            count = self.store.count(sym, cat)
            ranges = self.store.deleted_ranges(sym, cat)
            selected = cat in self.enabled_categories(sym)
            if not enabled or not selected:
                # §17 — the user chose not to keep this dataset; it is simply
                # not part of the analysis, not "missing".
                status = "DISABLED"
            elif count == 0:
                status = "MISSING"
                missing.append(C.CATEGORY_LABELS.get(cat, cat))
            else:
                status = "PARTIAL" if ranges else "FULL"
            if ranges:
                for r in ranges:
                    deleted_notes.append(f"{C.CATEGORY_LABELS.get(cat, cat)}: {r[0][:10]} → {r[1][:10]}")
            months = 0.0
            if o_ts and n_ts:
                months = round((n_ts - o_ts) / (30 * 86400), 2)
            datasets.append(DatasetCoverage(
                category=cat,
                label=C.CATEGORY_LABELS.get(cat, cat),
                status=status,
                coverage_months=months,
                records=count,
                oldest=datetime.fromtimestamp(o_ts, tz=timezone.utc) if o_ts else None,
                newest=datetime.fromtimestamp(n_ts, tz=timezone.utc) if n_ts else None,
                deleted_ranges=ranges,
            ))
        with_data = [d for d in datasets if d.records > 0]
        if not enabled:
            overall = "DISABLED"
        elif not with_data:
            overall = "MISSING"
        elif any(d.status in ("PARTIAL", "MISSING") for d in datasets if d.status != "DISABLED"):
            overall = "PARTIAL"
        else:
            overall = "FULL"
        coverage_months = max((d.coverage_months for d in with_data), default=0.0)
        return CoverageReport(
            symbol=sym,
            derivative_enabled=enabled,
            overall=overall,
            historical_coverage_months=coverage_months,
            datasets=datasets,
            missing_datasets=missing,
            deleted_ranges=deleted_notes,
        )

    # ------------------------------------------------------------------
    # Background auto-delete sweep (§12)
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # 1. Restore state and datasets from Supabase PostgreSQL
        try:
            from app.hpi.hpi_persistence import ensure_hpi_tables, restore_hpi_from_db
            await ensure_hpi_tables()
            db_state = await restore_hpi_from_db()
            if db_state:
                # Merge DB state into store
                for key, recs in (db_state.get("records") or {}).items():
                    sym, cat = key.split("|", 1)
                    if sym in C.HPI_UNIVERSE:
                        self.store._records[(sym, cat)] = [tuple(r) for r in recs]
                for key, ranges in (db_state.get("deleted_ranges") or {}).items():
                    sym, cat = key.split("|", 1)
                    if sym in C.HPI_UNIVERSE:
                        self.store._deleted_ranges[(sym, cat)] = ranges
                for e in db_state.get("selection", []):
                    entry = DerivativeSelectionEntry(**e)
                    if entry.symbol in C.HPI_UNIVERSE:
                        self._selection[entry.symbol] = entry
                for p in db_state.get("policies", []):
                    pol = RetentionPolicy(**p)
                    if pol.instrument in C.HPI_UNIVERSE:
                        self._policies[pol.policy_id] = pol
                for a in db_state.get("audit", []):
                    if a.get("derivative") in C.HPI_UNIVERSE:
                        self._audit.append(DeletionAuditEntry(**a))
                self._seeded = bool(db_state.get("seeded", False))
                logger.info("hpi_db_state_restored_successfully", total_records=self.store.total_storage_bytes())
        except Exception as e:
            logger.warning("hpi_db_restore_failed_on_start", error=str(e)[:200])

        # 2. Auto-bootstrap historical data if empty (guarantees data exists on startup/restart)
        if self.store.total_storage_bytes() == 0:
            try:
                logger.info("hpi_auto_seeding_historical_datasets")
                self.seed_defaults(force=True, sampling_interval="1h", retention_days=180)
            except Exception as e:
                logger.warning("hpi_auto_seed_failed", error=str(e)[:200])

        self._sweep_task = asyncio.create_task(self._sweep_loop())
        logger.info("hpi_service_started")

    async def stop(self) -> None:
        self._running = False
        if self._sweep_task:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
        self.save_state()
        logger.info("hpi_service_stopped")

    async def _sweep_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(C.AUTO_DELETE_SWEEP_SECONDS)
                self.run_auto_delete()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("hpi_auto_delete_sweep_error", error=str(e))


hpi_service = HPIService()
