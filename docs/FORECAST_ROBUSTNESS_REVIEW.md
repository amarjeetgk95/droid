# Forecast Module — Robustness Review & Hardening Plan (draft)

**Scope:** `backend/app/research/trend_forecast.py` (orchestrator + ensemble + v2 contract),
`backend/app/research/cache.py` (TTL caches + minute-bucket idempotency),
`backend/app/research/predictions.py` (snapshot/prediction persistence),
`backend/app/research/risk_v2.py` + `options_context.py` (target sizing inputs),
`backend/app/api/research.py` (HTTP surface), `backend/app/research/scheduler.py` / `shadow.py`
(evidence collection), `frontend/src/lib/api/intelligence.ts` + `components/research/ForecastCard.tsx`.

**Validation method:** Static read of the orchestration path end to end (fetch → features → indicators → ML → ensemble → gates → persist → validate → replay) plus the existing tests
(`tests/test_forecast_v2_contract.py`, `tests/test_forecast_cache_p33.py`, `tests/research/test_trend_forecast_1h.py`,
`tests/test_calibrator_risk_v2.py`, `tests/test_forecast_scheduler.py`). Findings below are
code-traced, not speculative; each names the exact call site.

**Already solid (keep, don't regress):** never-synthetic "insufficient candles" path (`ValueError` → 503),
per-TF `asyncio.wait_for(12s)` + local 1m→higher-TF resample fallback with `resampled_tfs` provenance,
data-quality/settleability/late-session gates, per-layer graceful degradation, ML artifact/spec guard
(`validate_ml_artifact`), flag-gated v2 branch that never raises, pure contract validator, kill-switchable
caches, minute-bucket idempotency, release-bundle + rolling health endpoints, and honest `limitations[]` plumbing.

**Implementation status (this change set):** P0-1, P0-2, P0-3, P1-1, P1-2, P1-3, P1-4, P1-5, P1-6, P1-7
and P2-3 are implemented, with regression coverage in `backend/tests/test_forecast_robustness.py`
(24 tests) and `frontend/src/lib/api/intelligence.test.ts` (7 tests).

- P0-1: `GET /forecast/{h}` and `GET /tactical-bias/{h}` inject `Depends(get_db_session)` and pass it to
  `forecast(..., session=...)`; the response carries `persisted` (true only for a durable
  snapshot+prediction — the in-memory fallback reports `false`).
- P0-2: `SnapshotService.record_snapshot` / `PredictionService.record_prediction` take `strict=True`,
  raise `PersistenceError` (and drop the memory mirror) instead of returning an id for an unwritten row;
  the forecast degrades to `DEGRADED` + `persistence-failed:{snapshot|prediction}`. A prediction-write
  failure no longer escapes as a 500 and keeps the already-recorded snapshot id.
- P0-3: `PredictionService.find_in_minute_bucket` runs before the inserts and reuses the ids of a row
  already recorded for the same `(instrument, indicator_id, minute)` — across processes — so no duplicate
  immutable rows are written; the in-memory replay still short-circuits same-process repeats.
- P1-1: v2 targets use EM only when the options snapshot is `available` with `data_quality=LIVE`; otherwise
  `target_basis=ATR-only` + `em-unavailable-synthetic-options`.
- P1-2: `forecast()` wraps the orchestration in an `asyncio.wait_for` watchdog (`FORECAST_DEADLINE_S`,
  default 20s so the per-stage bounds win first) and raises `ForecastDeadlineExceeded`, which the API maps
  to a labeled 503. Options/ML got their own `FORECAST_STAGE_TIMEOUT_S` (default 3s) bounds. Kept as a hard
  error rather than a synthetic NEUTRAL verdict: a deadline means the forecast could not be computed.
- P1-4: an all-empty MTF picture is cached on `cache.NEGATIVE_TTL_S` (3s) instead of the 30s read TTL —
  long enough to coalesce concurrent callers on a dead feed, short enough that a re-auth + Retry recovers.
- P1-5: `_flight_lock` gives MTF/options/ML a per-key `asyncio.Lock`; each stage re-checks its cache under
  the lock, so N concurrent misses collapse into one provider/model call.
- P1-6: the heavy layers are opt-in (`include_layers=true`, threaded through both endpoints) and never
  retained by the replay map. `shadow._call_forecast` introspects the signature and requests them, since
  the shadow snapshot persists `options_context`.

- P1-3: `fetch_multi_timeframe_candles` returns a copy carrying its own `cache_hit` flag, and the ML layer
  reports its hit via a per-task `ContextVar` — no more mutable hit flags on the process-wide singleton.
- P1-7: `ApiCore` now throws `ApiError` (with `status`) so `getTacticalBias` falls back to `/forecast` only on
  404/405; every other failure (503, timeout, network) propagates immediately instead of doubling the
  provider work. `include_explain` is a real query param (default true, so WhyPanel keeps rendering) and the
  client can opt out; persisted recordings keep the bundle either way.
- P2-3: `forecast_runtime_metrics()` counts calls, persistence failures, deadline aborts, contract
  violations, degraded/abstain verdicts and bucket replays (plus a 200-sample latency ring with p50/p95),
  and `/monitoring/forecast-health` exposes them in a `runtime` block — a failure inside
  `RUNTIME_FRESH_WINDOW_S` (15 min) now marks the verdict degraded with a reason instead of existing only in
  the logs. Extending the DB-row rolling thresholds themselves is left as follow-up.

Still open: P2-1 (validate before persisting), P2-2 (error codes), P2-4 (confidence semantics), P2-5
(artifact-meta I/O), and extending `rolling_window_metrics`/`DEFAULT_THRESHOLDS` with the new runtime signals.

---

## P0 — Critical (the "immutable evidence" promise does not hold yet)

### P0-1. `record=True` writes nothing to the database from the API path
**Where:** `backend/app/api/research.py:182-206` (`GET /forecast/{horizon}` — no `session` dependency) and
`:212-232` (`GET /tactical-bias/{horizon}`); `trend_forecast.py:1429` (`forecast()` signature has no `session`);
`:1740` `SnapshotService.record_snapshot(snapshot)`, `:1793` `PredictionService.record_prediction(pred)`.

Both endpoints delegate to the process-wide `trend_forecaster` singleton and pass only
`instrument/horizon/record`. Because no `AsyncSession` is threaded through, every snapshot and prediction
lands in the bounded in-memory fallbacks (`predictions.py:51-54`, `:137-140` — 1000 entries, oldest evicted)
and is lost on the next restart/deploy. The only writer that actually reaches Postgres is the hourly shadow
scheduler (`shadow.py:183-326` → `_record_shadow_result(..., session=session)`), and it is **disabled by default**
(`FORECAST_SCHEDULER_ENABLED=off`, `scheduler.py:22-30`, started from `main.py:158-166` — note
`start-backend-local.ps1:15` turns it **on** for local dev, which is why DB rows only ever appear from
shadow cycles).

Consequences: `/monitoring/forecast-health` and the settlement/backfill scripts
(`scripts/backfill_research_settlement.py`) see only shadow rows, so user-facing forecasts never accumulate
the Cycle-1 evidence the module is built around; a memory eviction (1000 rows, or any deploy) silently
destroys auditability.

**Draft fix — thread the request session through, commit once:**
```python
# api/research.py
@router.get("/forecast/{horizon}")
async def get_forecast(
    horizon: str,
    instrument: str = Query("NIFTY 50"),
    record: bool = Query(True),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    ...
    return await trend_forecaster.forecast(
        instrument=instrument, horizon=h, record=record, session=session
    )
```
```python
# trend_forecast.py
async def forecast(self, instrument, horizon="1h", record=True, session=None):
    ...
    snapshot_id = await SnapshotService.record_snapshot(snapshot, session=session)
    ...
    prediction_id = await PredictionService.record_prediction(pred, session=session)
    result["persisted"] = bool(session is not None and snapshot_id and prediction_id)
```
Then commit the snapshot+prediction pair in one transaction instead of committing inside each service
call (see P0-3), and keep in-memory mirroring as a cache, not the store of record.

### P0-2. Database write failure is indistinguishable from success
**Where:** `predictions.py:88` (`failed_to_write_snapshot_db_fallback_memory` → `session.rollback()`, then
`return snapshot.snapshot_id`), `:187` (`failed_to_write_prediction_db_fallback_memory` → `return prediction.prediction_id`).

When the insert fails, the service rolls back, logs a warning, and **returns the id anyway** (`:189`).
Callers treat any truthy id as "persisted": `trend_forecast.py:1740-1793` keeps `status="RESEARCH"`,
`data_quality="HEALTHY"`, `snapshot_id`/`prediction_id` set, and no limitation is appended. A schema drift,
connection-pool exhaustion, or read-only replica therefore degrades every forecast into memory-only storage
while the API reports a fully healthy, immutable record. There is no counter for this in the health endpoint.

**Draft fix — make persistence outcome explicit and honest:**
```python
class PersistenceError(RuntimeError): ...

@classmethod
async def record_prediction(cls, prediction, session=None) -> str:
    ...
    if session is not None:
        try:
            await session.execute(stmt, params)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning("failed_to_write_prediction_db", error=str(e))
            raise PersistenceError(str(e))   # caller decides how to degrade
    return prediction.prediction_id
```
and in `forecast()` (`:1740-1793`) wrap the record block: on `PersistenceError` append
`persistence-failed:db`, set `data_quality="DEGRADED"` (or keep `HEALTHY` with `persisted=False` —
pick one and document it), and surface `persisted: false` in the response so the UI can stop showing a
"recorded" id. Add a `persist_failure_rate` metric to `/monitoring/forecast-health`.

### P0-3. Idempotent replay leaves duplicate immutable rows in the database
**Where:** `trend_forecast.py:1850-1904` — the replay branch pops duplicates from
`PredictionService._memory_predictions` (`:1860`) and `SnapshotService._memory_snapshots`, then replays
`_old_res` (`:1870`, `:1890`) and re-`put`s the key (`:1904`).

The dedupe only touches the in-memory dicts. With P0-1 fixed, the duplicate snapshot/prediction rows are
already committed inside the service calls (both commit before returning — `predictions.py:84-88`,
`:183-187`), so a same-minute second call produces **two** `research_predictions` rows and **two**
`research_snapshots` for one logical forecast —
double-counted evidence, distinct `prediction_id`s, and an outcomes table that will settle both. The current
memory-only behavior hides this; the DB wiring would expose it immediately.

**Draft fix — check-and-insert inside one transaction (or make the bucket the conflict key):**
```python
# Preferred: single transaction per forecast, idempotency check inside it
async with session.begin():
    existing = await PredictionService.find_by_bucket(session, instrument, horizon, bucket, weights_v, model)
    if existing:
        return replay(existing)                       # no new rows written
    await SnapshotService.record_snapshot(snapshot, session=session, commit=False)
    await PredictionService.record_prediction(pred, session=session, commit=False)
```
If a schema change is unwanted now, add `ON CONFLICT DO NOTHING` on a unique
`(instrument, forecast_horizon, minute_bucket, weights_version, model_flag)` key and treat
`inserted == 0` as a replay. Note `append_outcome` already uses `ON CONFLICT (prediction_id) DO NOTHING`
(`predictions.py:226`), so the pattern exists in this module.

---

## P1 — High (wrong numbers or unbounded request behavior)

### P1-1. Synthetic options defaults silently feed v2 target sizing
**Where:** `options_context.py:35-53` (unavailable → `available=False`, `atm_iv=15.0` at `:49`,
`days_to_expiry=1.0`) and `:104-119` (`data_quality=FAILED`, same synthetic values); consumed at
`trend_forecast.py:1353-1357`:
```python
em_v2 = _risk_v2.expected_move(
    current_price,
    (options_ctx or {}).get("atm_iv"),
    (options_ctx or {}).get("days_to_expiry"),
)
```

`risk_v2.expected_move` (`risk_v2.py:42-74`) accepts anything positive, so a fabricated
IV 15% / DTE 1.0 produces a real EM (≈0.78% of spot), `target_basis` is reported as `"ATR+EM"`
(`trend_forecast.py:1390-1396`), and the target/invalidation distances are then capped by that EM
(`0.70·EM`, `0.35·EM`). The response therefore advertises EM-backed risk levels derived from data the
module already knows is absent — the opposite of the "never a synthetic EM" contract stated in
`risk_v2.py`'s own docstring.

**Draft fix — gate EM on real options data, fall back to ATR-only with a limitation:**
```python
em_v2 = None
if options_ctx.get("available") and str(options_ctx.get("data_quality", "")).upper() == "LIVE":
    try:
        em_v2 = _risk_v2.expected_move(
            current_price, options_ctx.get("atm_iv"), options_ctx.get("days_to_expiry")
        )
    except Exception:
        em_v2 = None
else:
    v2_limitations.append("em-unavailable-synthetic-options")
```
and make the same choice for `barrier_v2` (walls are `None` when unavailable, so it is already safe).
Add a regression test asserting `target_basis == "ATR-only"` when `available=False`.

### P1-2. No end-to-end deadline — the documented SLO is unenforced
**Where:** the only timeouts are the per-TF fetches (`trend_forecast.py:690-699`, `wait_for(12.0)` at `:694`).
`ResearchOptionsContext.get_context`, indicator `calculate`, `MLPredictor.predict_probabilities`,
`build_forecast_explain`, the snapshot/prediction writes and the replay `deepcopy`
(`:1870`) are all unbounded inside the request. The docstring's "p95 < 8s / hard 12s" (module header)
describes intent, not enforcement.

Impact: one hung provider call holds a worker slot, an open client socket, and one of the browser's
poll cycles (frontend aborts at 60s, `client.ts:79-84`) while N users × 5 horizons each stack up. There is
no watchdog, so "hangs" show up as client timeouts with no server-side verdict.

**Draft fix — one budget for the whole orchestration, degrade instead of hanging:**
```python
FORECAST_DEADLINE_S = float(os.getenv("FORECAST_DEADLINE_S", "12"))

result = await asyncio.wait_for(
    self._forecast_inner(instrument, horizon, record=record, session=session),
    timeout=FORECAST_DEADLINE_S,
)
```
```python
except asyncio.TimeoutError:
    return degraded_verdict(instrument, horizon, limitation="deadline-exceeded", status="DEGRADED")
```
Also give the options context and ML predict their own modest timeouts (e.g. 3s) so they degrade to
`available=False` / `ml-unavailable` instead of consuming the whole budget, and skip the record step when
the deadline already expired.

### P1-3. Cross-request state on the shared singleton corrupts cache telemetry — *fixed (per-call provenance)*
**Where:** `trend_forecast.py:677` (`self._last_mtf_cache_hit = True` inside the cache-hit branch, read at
`:1453-1456`) and `:860` (ML twin, read at `:1520-1523`), both against the module singleton
`trend_forecaster` (`:1962-1964`).

Both flags are plain instance attributes set before an `await` and read after it. With two concurrent
requests, task B's fetch completion can overwrite task A's flag between A's `await` and A's read, so
`result["cache_hit"]` — the source for the P3-3 SLO story — can report a hit for a request that missed, or
vice versa.

**Draft fix — return provenance instead of stashing it.** `_MTFCandles` already exists for exactly this
purpose: add `cache_hit: bool` to it and read `mtf_candles.cache_hit`. For ML, return
`(value, cache_hit)` (or a small dataclass) from `get_ml_forecast` instead of setting an attribute.
This also removes the `try/except` dance around the flag assignments.

### P1-4. Transient gaps get cached, blocking recovery — *fixed via a 3s negative TTL*
**Where:** `trend_forecast.py:738-748` — `self._mtf_cache.set(_mtf_key, result)` runs unconditionally, even
when every timeframe came back empty (all `_fetch_one` failures were swallowed into `[]` at `:697-699`).

Consequence: one broker rate-limit blip / expired token makes `forecast()` raise "Insufficient 1h candle
data" instantly for the next 30s, including immediately after the operator re-auths and hits Retry. The
existing error message explicitly tells the user to re-auth and retry — and the cache silently ignores that
retry for 30 seconds.

**Draft fix:**
```python
if _ce() and _mtf_key is not None and self._mtf_cache is not None:
    if any(result.values()):          # never cache an all-empty picture
        self._mtf_cache.set(_mtf_key, result)
    else:
        logger.info("forecast_mtf_cache_skip_empty", instrument=instrument)
```
(or a short negative TTL, e.g. 3s, if you want some protection against a thundering herd on a dead feed —
in which case also add single-flight, see P1-5.)

### P1-5. No single-flight — a cache miss fans out into N identical provider storms
**Where:** `fetch_multi_timeframe_candles` (`:645-750`), `get_ml_forecast` (`:848-905`) and the options
cache block in `forecast()` (`:1467-1512`) all do "check cache → await provider → store", with no
in-flight coalescing.

With the documented load model (10 users polling 5 horizons), a 30s MTF TTL expiry means simultaneous
misses across all users, each issuing 7 candle fetches. That is exactly the pattern the FYERS rate
limiter punishes, and it is when the per-TF 12s timeout is most likely to fire.

**Draft fix — per-key `asyncio.Lock` (or a shared `Task`) keyed the same as the cache:**
```python
async def _single_flight(self, key, coro_factory):
    async with self._locks.setdefault(key, asyncio.Lock()):
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        value = await coro_factory()
        self._cache.set(key, value)
        return value
```
Cap the lock map (e.g. 200 keys, same bound as the caches) and add a `coalesced_waiters` counter to the
completion log.

### P1-6. Replay/memory amplification: full layer payloads are copied, retained and echoed — *fixed (opt-in `include_layers`)*
**Where:** `trend_forecast.py:1868-1904` (`deepcopy(result)` at `:1870`, stored via
`MinuteBucketReplay` — `cache.py:133` `max_entries=500`), `:1245-1255` (`result["mtf_features"]` at
`:1252`, plus `result["indicator_outputs"]` and `result["options_context"]`), and
`predictions.py:51-54`/`:137-140` (1000-entry in-memory stores referencing the same objects).

`result` carries the untrimmed `mtf_features` (every TF's `features` including the full `ta_suite`),
`options_context.raw_fno`, the model-dumped indicator outputs and the explain bundle. That object is
returned over HTTP, deepcopied into the replay map (up to 500×), and referenced by up to 1000 in-memory
predictions. Each forecast is plausibly 50-200 KB, i.e. tens of MB of resident copies — and a large JSON
response on every poll.

**Draft fix:**
- Store a slimmed reply in the replay map and in the in-memory prediction branch (reuse the same field
  allow-list as `_trim_mtf_features_for_snapshot`, `:1039-1072`).
- Stop echoing the raw layers in the HTTP response; add an explicit `?include_layers=true` for debugging.
  The frontend consumes none of them (`HourForecast` in `ForecastCard.tsx:34-78` has no `mtf_features`, and
  only `tests/research/test_trend_forecast_1h.py:78` asserts the key exists).
- Have the replay restore the ids and verdict fields from the slim copy, since those are all a consumer
  reads.

(For scale: `MinuteBucketReplay` keeps up to 500 copies and the in-memory prediction store 1000 more, each
of which can carry a full per-TF `ta_suite`; the replay path is also the only place a per-request `deepcopy`
of the whole verdict happens.)

### P1-7. Frontend doubles the work on every failure — *fixed (status-aware fallback)*
**Where:** `frontend/src/lib/api/intelligence.ts:46-57` — `getTacticalBias` wraps the call in
`try { ... } catch { return this.getForecast(...) }`.

`/tactical-bias/{h}` and `/forecast/{h}` (`api/research.py:212-232` vs `:182-206`) are the same code path,
so the fallback only ever fires on a genuine failure. A 503 "insufficient candles" or a 500 therefore
triggers a **second** complete orchestration (another 7+ candle fetches, indicators, ML) with no backoff —
worst case ~2× the provider load precisely when the broker is already struggling, and it converts a fast
error into a 24s+ user-visible stall.

**Draft fix:** fall back only when the route is genuinely absent (404/405), not on 5xx; add jittered
backoff and an in-flight dedupe keyed by `(instrument, horizon)` in the client/desk hook. While in there:
`getForecastExplain` (`intelligence.ts:58-62`) sends `include_explain=true`, which the endpoint does not
declare — FastAPI ignores it and the explain bundle is returned every time. Either add the query param
(default `false` so the heavy bundle is opt-in) or delete the client function's claim.

---

## P2 — Medium (contract ordering, error surface, observability)

### P2-1. Contract validation happens after persistence
**Where:** `trend_forecast.py:1800` (`validate_forecast_v2(result, record=record)`) runs *after* the
snapshot (`:1740`) and prediction (`:1793`) writes; its reactions are the `if contract_errors:` block at
`:1803-1813`.

An invalid payload is therefore written to the immutable tables first and only downgraded
(`status→DEGRADED`, `data_quality→DEGRADED`, `contract-validation:...` limitation) in the HTTP body
afterwards — response and database disagree, and the durable record is the unvalidated one.
**Fix:** validate the final verdict before the record step; if invalid, either skip persistence
(`record=False` semantics + limitation) or persist the validator output alongside so the row is
self-describing.

### P2-2. Error surface leaks internals and has no machine-readable codes
**Where:** `api/research.py:198-206` and `:228-232` — `HTTPException(500, detail=f"Forecast failed: {e}")`
and `HTTPException(503, detail=str(e))`.

The 500 path echoes arbitrary internal exception text to the client, and both paths force the UI to string
-match a message to tell "broker down" from "after hours" from "bug". **Fix:** stable codes
(`insufficient_history`, `broker_unavailable`, `deadline_exceeded`, `internal_error`) in a structured
`detail`, a correlation id in the logs, and a generic message for 500.

### P2-3. Contract violations, replay rate and abstain rate aren't alerted — *partially fixed (runtime counters in /forecast-health)*
**Where:** the only reaction to `contract_errors` is a `logger.warning` (`:1803-1813`), and
`/monitoring/forecast-health` (`api/monitoring.py:106-202`) computes rolling metrics from **persisted
rows** — which today mostly don't exist (P0-1). **Fix:** once P0-1 lands, add contract-violation count,
`idempotent_replay` share, `ABSTAIN`/`DEGRADED` shares and `latency_ms` p50/p95 to the rolling window and
its `DEFAULT_THRESHOLDS`, so the SLO in the module docstring is measured rather than asserted.

### P2-4. Confidence is a restatement of score on the default path
**Where:** `trend_forecast.py:1192-1194` builds a composite `confidence` from alignment/indicator/ML, then
`:1261-1262` overwrites it with `raw_confidence = max(probabilities)` (applied at `:1650`). Since
`score_to_probabilities_v2` is a deterministic function of `score`, the number the UI labels
"confidence" contains no information beyond the score. **Fix:** either surface the composite as a separate
field (`evidence_confidence`) or drop the dead mean and document that `confidence = max(P)`.
Related note: `alignment_score` (`features.py:301-315`, computed at `:308`) is a concentration measure
(the winning side's share of votes), not trend strength — worth a docstring so downstream consumers stop
reading it as conviction.

### P2-5. Per-request artifact I/O on the event loop
**Where:** `validate_ml_artifact` (`:919-990`) does a synchronous `meta_path.read_text()` plus
`json.loads` on every forecast. Small, but it blocks the loop and runs regardless of caching.
**Fix:** `lru_cache` keyed on `(horizon, mtime, size)` or read via `asyncio.to_thread`.

---

## Suggested tests (currently missing)

```python
# tests/test_forecast_robustness.py

async def test_forecast_persists_with_session_and_replays_without_duplicates():
    """P0-1/P0-3: two same-minute record=True calls -> 1 prediction row, same id.""" 

async def test_forecast_db_failure_is_surfaced_not_silent():
    """P0-2: broken session -> persisted=False + limitation, never a healthy verdict."""

async def test_synthetic_options_never_produce_em_targets(monkeypatch):
    """P1-1: options available=False -> target_basis 'ATR-only' and em limitation present."""

async def test_forecast_deadline_degrades_instead_of_hanging():
    """P1-2: a provider that sleeps past FORECAST_DEADLINE_S -> DEGRADED, not a hang."""

async def test_concurrent_forecasts_share_one_mtf_fetch():
    """P1-3/P1-5: N parallel calls -> 1 provider fetch per TF, per-request cache_hit flags correct."""

async def test_all_empty_mtf_is_not_cached(monkeypatch):
    """P1-4: after a failed fetch the next call must retry the provider immediately."""

async def test_response_omits_heavy_layers_by_default():
    """P1-6: no mtf_features/indicator_outputs in the default body; present with include_layers=true."""
```

---

## Rollout priority

1. **P0-1 + P0-3** (session wiring + single-transaction idempotency) — Medium — without it the module's
   core evidence promise is memory-only and duplicate-prone; do them together so the replay path is never
   DB-duplicating.
2. **P0-2** (persistence failure is explicit) — Small — prevents silent memory-only degradation from
   looking healthy.
3. **P1-1** (EM only from real options data) — Small — fabricated IV/DTE currently shape published targets.
4. **P1-2** (end-to-end deadline) — Small — turns unbounded hangs into labeled DEGRADED verdicts.
5. **P1-4 + P1-3** (negative-cache guard, provenance flags) — Small — restores recovery and fixes the SLO
   telemetry that the p95 story depends on.
6. **P1-5 + P1-6** (single-flight, slim replay/response) — Medium — protects the broker and the process
   under the documented 10-user poll load.
7. **P1-7** (frontend fallback + `include_explain`) — Small — removes the failure-path double orchestration.
8. **P2-1 … P2-5** — Medium — contract ordering, error codes, alerting, confidence semantics.

**Non-goals in this pass:** re-tuning the ensemble weights or thresholds, changing the v1→v2 label spec,
and touching the shadow/promotion workflow. All fixes above are additive and keep the v1 response keys
intact, so the frontend contract in `ForecastCard.tsx` is unaffected (with the single exception of P1-6's
opt-in layer echo, which no current consumer reads).
