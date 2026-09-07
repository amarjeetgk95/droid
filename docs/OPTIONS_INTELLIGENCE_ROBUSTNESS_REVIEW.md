# Options Intelligence — Robustness Review & Hardening Plan

**Scope:** `backend/app/signals/options_intelligence/` (greeks, path_simulator, selector), `backend/app/signals/expected_move.py`, `backend/app/signals/portfolio_greeks.py`, `backend/app/api/options_intelligence.py`, `backend/app/institutional/options_intelligence.py`, `backend/app/event_engine/options_context.py`, `backend/app/services/options_service.py` (IV pipeline), and `frontend/src/app/(app)/options-intelligence/page.tsx`.

**Validation method:** All 21 existing tests pass (`tests/test_options_intelligence.py`, `tests/test_options_intelligence_api.py`, `tests/test_expected_move.py`). Every P0 issue below was reproduced empirically against the live code — these are verified defects, not speculation.

---

## P0 — Critical (fix before any live/paper trading reliance)

### P0-1. Invalid market data silently produces a plausible-looking delta of 0.5
**Where:** `backend/app/signals/options_intelligence/greeks.py:62-80` (`calculate_d1_d2` guard) consumed by `calculate_greeks` at line 129.

`calculate_d1_d2` returns `(0.0, 0.0)` when `spot <= 0 or strike <= 0 or t <= 0 or vol <= 0`. `calculate_greeks` then proceeds with `d1 = d2 = 0`, yielding `N(0) = 0.5`:

```
Repro: BlackScholesGreeks.calculate_greeks(spot=-1.0, strike=24500.0, t=0.01, vol=0.15, "CE")
       -> delta=0.4999, gamma=0.0, price=0.0     # a dead feed looks like an ATM option
```

A transient broker-feed failure (spot=0/None coerced) downstream becomes a fake "ATM, delta 0.5" reading that flows into sizing, R/R and the dashboard without any error.

**Draft fix — fail loudly at the boundary, zero-Greek for the legitimate 0-DTE edge:**
```python
# greeks.py
class BlackScholesGreeks:
    @classmethod
    def calculate_d1_d2(cls, spot, strike, time_to_expiry_years, volatility,
                        risk_free_rate=DEFAULT_R, dividend_yield=DEFAULT_Q):
        if spot <= 0 or strike <= 0:
            raise ValueError(
                f"Invalid option inputs: spot={spot}, strike={strike} must be positive"
            )
        if volatility <= 0:
            raise ValueError(f"Invalid volatility: {volatility} must be positive")
        if time_to_expiry_years <= 0:
            return float("-inf"), float("-inf")  # expiry limit; pdf/cdf handled below
        ...
```
And in `calculate_greeks`, clamp only *time* (0-DTE is legitimate), never spot/strike/vol:
```python
t = max(1e-6, time_to_expiry_years)
if spot <= 0 or strike <= 0 or volatility <= 0:
    raise ValueError("spot, strike and volatility must be strictly positive")
```
Do the same at the API boundary (`api/options_intelligence.py` `GreeksRequest`: `spot: float = Field(gt=0)` etc.) so Pydantic rejects bad payloads with a 422 instead of computing garbage.

### P0-2. IV solver silently saturates at 400% for arbitrage-violating quotes
**Where:** `greeks.py:259-273` (bisection fallback), `:233-234` (intrinsic floor).

When the market price exceeds the maximum theoretical price at `sigma = 4.0`, bisection converges to the boundary and the function returns `4.0` (400% IV) as if it were a real quote:

```
Repro: theo at sigma=4.0 = 5915.41; ask = 17746.23
       solve_iv(17746.23, ...) -> 4.0     # no flag that the price is impossible
```

Downstream, 400% IV feeds regime detection (`SHOCK`), expected-move and selection scoring as genuine data.

**Draft fix — return `None` (or a result object with a `status`) instead of a fake number:**
```python
def solve_iv(self, market_price, spot, strike, time_to_expiry_years, option_type,
             risk_free_rate=DEFAULT_R, dividend_yield=DEFAULT_Q, ...) -> Optional[float]:
    ...
    # Reject prices above the no-arbitrage ceiling before searching
    upper_theo = cls.calculate_price(spot, strike, t, 4.0, option_type, r, q)
    if market_price > upper_theo * 1.05:
        return None   # caller decides: skip quote / flag stale / alert
    ...
    # after bisection fails to converge inside tolerance:
    if abs(cls.calculate_price(spot, strike, t, 0.5*(low+high), option_type, r, q) - market_price) > tolerance * 10:
        return None
    return round(0.5 * (low + high), 4)
```
Callers (`options_service` IV pipeline, API `/solve-iv`) must handle `None` explicitly and mark the row `iv: None, iv_status: "UNRESOLVABLE"`.
### P0-3. Contract selector returns a tradable-looking result even when every candidate is rejected
**Where:** `selector.py:214-219` ("Pick highest scoring candidate among acceptable (or highest overall if none strictly pass)") and `:244-256`.

Repro (all three candidates rejected — theta drag, low delta, failed viability):

```
Repro: select_optimal_contract(NIFTY, 24900, LONG_CALL, expected_move_points=5.0,
       stop_loss_points=5.0, target_horizon_hours=4.0, current_iv=0.40)
       -> selected_strike_type=ITM_1, score=15.25, is_acceptable=False on ALL candidates
       -> API returns HTTP 200 with a full StrikeSelectionResult
```

`StrikeSelectionResult` has **no top-level viability flag**, so any consumer that checks the status code (the frontend does; an algo consumer would too) treats a 15/100, explicitly-rejected contract as a recommendation.

**Draft fix:**
```python
class StrikeSelectionResult(BaseModel):
    ...
    is_viable: bool = Field(..., description="True only if the selected candidate passed all guards")
    non_viability_reasons: list[str] = Field(default_factory=list)
```
```python
# selector.py, after best_candidate is chosen
best = max(acceptable_candidates, key=...) if acceptable_candidates else max(evaluated_candidates, key=...)
return StrikeSelectionResult(
    ...,
    is_viable=bool(acceptable_candidates),
    non_viability_reasons=[] if acceptable_candidates else best.rejection_reasons,
)
```
And the API should either return `200` with `is_viable: false` prominently, or `422` when `strict` is requested. At minimum the frontend `ContractSelectorTab` must render a "NO VIABLE CONTRACT" state instead of a selection.

### P0-4. Live options context fabricates data and marks it `market_data_valid=True`
**Where:** `backend/app/event_engine/options_context.py:129-154`.

On **any** exception the service returns a fully synthetic context (spot 52000/24500, IV 14.5, OI 1.25M, …) with `market_data_valid=True` and only a diagnostics hint `"mode": "FALLBACK_CALIBRATED"`. The `market_data_valid` flag is the contract downstream consumers rely on to know data is real — this inverts it. Additionally:
- `target_symbol = "BANKNIFTY" if "BANK" in clean_symbol else "NIFTY"` (lines 53-54) silently maps **SENSEX, FINNIFTY, MIDCPNIFTY** onto NIFTY data.
- The blanket `except Exception` also swallows genuine code bugs (AttributeError, KeyError) and converts them into confident fake data.

**Draft fix:**
```python
return LiveOptionsContext(
    underlying=target_symbol,
    ...
    market_data_valid=False,                       # <-- the critical change
    data_source="FALLBACK_CALIBRATED",
    diagnostics={"mode": "FALLBACK_CALIBRATED", "error": str(e)},
)
```
```python
APPROVED_INDEXES = {"NIFTY", "BANKNIFTY", "SENSEX"}
target_symbol = underlying.upper().replace(" ", "")
if target_symbol not in APPROVED_INDEXES:
    raise ValueError(f"Unsupported underlying for options context: {underlying}")
# catch narrowly:
except (TimeoutError, ConnectionError, DataUnavailableError) as e:   # not Exception
```
Audit every consumer of `get_live_options_context()` / `LiveOptionsContext` to hard-gate on `market_data_valid` before acting.
---

## P1 — High

### P1-1. Two incompatible IV conventions coexist (percent vs decimal)
- **Percent (×100):** `options_service.py:247` (`atm_iv = round(base_atm_iv * 100.0, 2)`), `institutional/options_intelligence.py` regime thresholds (`iv > 30 → SHOCK`), `event_engine/options_context.py` (`atm_iv / 100.0` in expected move), AI prompt builder.
- **Decimal:** `greeks.py` / `selector.py` / `path_simulator.py` (`current_iv: float = 0.16`), `expected_move.py`, frontend `INSTRUMENT_IV = {NIFTY: 0.142, ...}`.

Nothing prevents `atm_iv` (14.5) from being passed as `current_iv` (0.16) — the Greeks would then be computed at 1450% IV and every metric would look "plausible" to a non-expert reviewer. **Draft guard (defense in depth):**
```python
def normalize_iv(iv: float, *, assume="DECIMAL") -> float:
    """DECIMAL: 0.15 == 15%. Auto-detects percent units as a safety net."""
    if iv > 1.5:            # 150%+ is beyond any NIFTY/BANKNIFTY/SENSEX regime -> almost surely percent
        iv = iv / 100.0
    if not (0.0005 <= iv <= 3.0):
        raise ValueError(f"IV out of sane range after normalization: {iv}")
    return iv
```
Apply in `calculate_greeks`, `solve_iv`, `select_optimal_contract`, `project_move`, and document "decimal everywhere internally; percent only at display/serialization boundaries".

### P1-2. No authentication on the whole `/api/v1/options-intelligence` router
Other routers (`api/algo.py`, `api/telegram.py`) consistently use `Depends(get_current_user)` / `Depends(require_auth)`. The options-intelligence router — including `POST /financial-research/synthesize`, which invokes the AI engine (token cost, latency) — is fully open. **Draft fix:** add `user: AuthUser = Depends(get_current_user)` to all endpoints (minimum: all POSTs and the synthesize endpoint; consider `require_auth` for synthesize). Rate-limit `synthesize` per user.

### P1-3. Simulated data presented as solved: fabricated IV smile, fake IV rank/percentile/term structure
- `options_service.py:142-147, 182-187` — when Black-76 IV solve fails, a synthetic smile `base_atm_iv * (1 + 0.18m² ± 0.06m)` is written into `greeks.iv` indistinguishably from a solved IV.
- `institutional/options_intelligence.py:107-108` — `iv_percentile = min(95, max(5, int((iv-8)/22*80+10)))` is a linear fabrication; `iv_rank = int(iv_percentile * 0.9)` compounds it; `term_structure = "CONTANGO" if atm_iv < 20 else "FLAT"` never compares two expiries; `iv_change`/`skew_change` are hardcoded `None`.
- `institutional/options_intelligence.py:199` — comment admits `oi_change` is "synthetic 5%", and positioning classification (P1-4) runs on it.

**Draft fix:** introduce an explicit provenance enum on every derived field:
```python
class DataProvenance(str, Enum):
    SOLVED = "SOLVED"            # computed from real quotes
    INTERPOLATED = "INTERPOLATED" # model-filled, flagged
    FALLBACK = "FALLBACK"        # static default
```
Expose `iv_provenance`, `percentile_provenance` etc. in responses; render a "model-estimated" badge in the UI for anything not SOLVED. Persist a rolling ATM-IV history (even an in-memory 30-day ring buffer in a service) so percentile/rank are real instead of fabricated.

### P1-4. Positioning classifier mislabels on edge cases and ignores volume
`institutional/options_intelligence.py:29-56` — `price_up = ltp > prev_ltp` (strict). Unchanged price + rising OI → `SHORT_BUILDUP` (wrong); `oi_change == 0` → `prev_oi=None` → `INSUFFICIENT_DATA` (a flat OI day is not missing data); the `volume` argument is accepted and never used although the docstring claims price+OI+volume context. **Draft fix:** add a dead-band (e.g. |Δltp| < 0.05 → price flat; flat+OI-up → `NEUTRAL_BUILDUP`), compute `prev_oi = open_interest - oi_change` whenever `oi_change is not None` (including 0), and incorporate a volume percentile floor before labeling any BUILDUP.
### P1-5. Simulator mixes market entry price with model-IV exits → systematic bias
`path_simulator.py` `evaluate_candidate` (241-270): entry premium = market price (good), but all five scenario exits are repriced at the *supplied* `iv` (default 0.16), ignoring what the market actually implies for that strike. If the strike trades rich/cheap vs 16%, fast/slow/adverse P&Ls are biased by the mismatch — exactly the number the viability decision hinges on. **Draft fix:** calibrate first — `iv_calibrated = BlackScholesGreeks.solve_iv(market_premium, spot, strike, t, option_type)`; if `None` (P0-2), fall back to supplied IV **and** append `viability_rationale.append("IV uncalibratable — model IV used, results low-confidence")`. Then use `iv_calibrated` for the initial Greeks and all scenario repricing.

### P1-6. Viability logic: comment/code drift and unused scenarios
- `path_simulator.py:352` comment says *"net gain > 1.25x friction"*; the code requires `net_pnl_total < friction_total * 1.5` — doc drift on a money-relevant threshold.
- The `iv_crush_target` and `sideways` scenarios are computed on every call but **never referenced** in the viability decision (348-376). An IV-crush kill-criterion that exists but is not wired cannot protect anyone. **Draft fix:** align constant (extract `MIN_PROFIT_VS_FRICTION_MULT = 1.5` as a named, documented constant) and add: `if sideways_scen.net_pnl_total < -0.5 * invested_capital * 0.35: reject("Sideways bleed exceeds 35% of premium")` and `if iv_crush_scen.net_pnl_total <= 0: reject("Target hit but IV crush turns trade unprofitable")` — both thresholds config-driven.

### P1-7. Portfolio Greeks ledger: thread-unsafe, silently overwriting, non-durable
`portfolio_greeks.py:96-97` — `add_position` overwrites an existing `position_id` without warning; `_positions` is a plain dict mutated from FastAPI's threadpool (sync endpoints) with no lock; the ledger is memory-only, so a restart zeroes all risk accounting while the algo still holds real positions; `max_expiry_concentration_pct` uses raw contract quantity (not lots/notional); gamma/vega limits are declared in `PortfolioRiskLimits` but never enforced in `evaluate_marginal_trade`. **Draft fix:**
```python
import threading
class PortfolioGreeksLedger:
    def __init__(self, limits=None):
        self.limits = limits or PortfolioRiskLimits()
        self._positions: dict[str, PortfolioGreekPosition] = {}
        self._lock = threading.Lock()

    def add_position(self, position):
        with self._lock:
            if position.position_id in self._positions:
                logger.warning("portfolio_position_overwritten", position_id=position.position_id)
            self._positions[position.position_id] = position
```
Plus: enforce gamma/vega ceilings symmetric to delta/theta; persist snapshots (the repo already has JSON state files / Firebase patterns) and reload on boot; concentration by lot count.
---

## P2 — Medium

### P2-1. Expected-move engine silently adopts NIFTY assumptions for unknown symbols
`expected_move.py:207` — `self.configs.get(u, self.configs["NIFTY"])` plus API `underlying: str` accepts anything (`RELIANCE` gets NIFTY velocity floors of 18 pts/hr — nonsense). **Fix:** validate with `validate_underlying()` from `contract_resolver` (single source of truth) and return 422 for out-of-universe symbols.

### P2-2. API request validation is absent where it matters most
`api/options_intelligence.py` — none of the DTOs constrain numeric ranges (`spot`, `strike`, `dte_days`, `iv`, `quantity` all unvalidated; `PathSimulateRequest.quantity` defaults to `75` regardless of underlying — BANKNIFTY lot is 30, SENSEX 10 per `INDEX_CONTRACT_CONFIGS`). **Fix:** `Field(gt=0)` on all price/vol fields, `dte_days: float = Field(ge=0, le=365)`, and derive default quantity from the resolver per underlying; reject quantities that are not lot multiples with a 422.

### P2-3. Selector details
- `selector.py:104` — `atm_strike = round(spot_price / step) * step` in float while the resolver uses `Decimal` (`resolve_atm_strike`) — use the resolver to avoid float-grid drift.
.
- `selector.py:144` — `strike_val in option_chain_quotes` float-equality lookup; quantize quote keys (`round(k, 2)`) or key by `Decimal`.
- Docstring promises expiry evaluation (§26 current-vs-next weekly) but only the current expiry is ever resolved — either implementthe next-weekly comparison or fix the docstring and the §-reference in the API docs.

### P2-4. Frontend page issues (`options-intelligence/page.tsx`)
- **Hardcoded IV** (`INSTRUMENT_IV`, lines 25-29) contradicts the page's own "no false or simulated data is fabricated" banner. Fetch ATM IV from the backend (e.g. reuse an options snapshot/chain context endpoint)and degrade explicitly when unavailable.
.
- **All-or-nothing loading** — `Promise.all` over 4 requests; one failure blanks the whole page. Use `Promise.allSettled` and render partial data with per-section error chips%.
- **Stale-response race** — no `AbortController`; rapid underlying/horizon flips can let an older response overwrite newer state. Abort in the `useEffect` cleanup.
- **NEUTRAL direction bug** — `direction === 'BULLISH' ? 'LONG_CALL' : 'LONG_PUT'` maps `NEUTRAL` (a valid `DirectionalBias`) silently to LONG_PUT. Disable the selector/calls for NEUTRAL or request both directions.

### P2-5. Schema/type hygiene
- `StrikeSelectionResult.expected_move_projection: Optional[object]` — untyped; use `Optional[ExpectedMoveProjection]`.
- `IndianOptionCosts.calculate_total_costs` returns a different key set when `quantity <= 0` (no `friction_per_share`) — return a consistent shape.
- `event_engine/options_context.py` `iv_crush_risk_level` docstring lists LOW|MODERATE|HIGH|EXTREME but code can only ever produce MODERATE|HIGH.
---

## P3 — Hygiene / calibration

1. **Cost model staleness** — `exchange_turnover_rate = 0.000505` vs NSE's revised 0.03503% (Oct 2024); spread/slippage defaults (₹1.0/₹0.5) are one-size-fits-all; make `IndianOptionCosts` load per-instrument config with an `as_of` stamp.
2. **Magic numbers** — spread-acceptability 5.0%, OI liquidity floor 50000, ATM band  erved 0.5%, `major_delta_oi` threshold 5000 — extract to named constants/config.
3. **`solve_iv` iterations** — cap Newton steps at ~30 and deduplicate the bisection tolerance; expose `max_iterations/tolerance` in the API DTO for ops tuning.
.
4. **Round-tripping** — `theta_pct_day` guard `theo_price > 0.05` is arbitrary; document or make it relative (`< 1% of spot * 0.001`).

---

## Suggested tests (currently missing coverage)

```python
# tests/test_options_intelligence_robustness.py
def test_greeks_reject_nonpositive_spot():        # P0-1
    with pytest.raises(ValueError):
        BlackScholesGreeks.calculate_greeks(-1.0, 24500.0, 0.01, 0.15, "CE")

def test_solve_iv_returns_none_for_overpriced():  # P0-2
    assert BlackScholesGreeks.solve_iv(17746.23, 24900, 24000,, 0.02,,"CE")is None

def test_selector_flags_all_rejected():           # P0-3
    res = quantitative_contract_selector.select_optimal_contract(
        "NIFTY", 24900.0, "LONG_CALL", expected_move_points=5.0,
        stop_loss_points=5.0, target_horizon_hours=4.0, current_iv=0.40)
    assert res.is_viableis Falseand res.non_viability_reasons

def test_iv_unit_normalization():                 # P1-1
    assert normalize_iv(14.5) == pytest.approx(0.145)
    with pytest.raises(ValueError:
        normalize_iv(50.0)                        # 5000% after normalization -> reject

def test_live_context_never_valid_in_fallback():  # P0-4
    ctx = ...  # force options_service failure via stub
    assert ctx.market_data_validis False

def test_api_rejects_bad_greeks_payload():        # P2-2
    r = client.post("/api/v1/options-intelligence/greeks",
                    json={"spot": -1, "strike": 100, "dte_days": 1,
                          "volatility": 0.2, "option_type": "CE"})
    assert r.status_code == 422
```
---

## Rollout priority

1. P0-1 and P0-2 (greeks/IV guards) plus tests — Small — Fake deltas/IVs silently poison every downstream metric
2. P0-4 (market_data_valid=False, symbol whitelist) — Small — Synthetic data treated as live by decision engines
3. P0-3 (is_viable flag and UI state) — Small — Rejected contracts rendered as recommendations
4. P1-1 (IV unit normalization) — Small — Cross-module 100x IV errors
5. P1-2 (auth on router) — Small — Open AI-synthesis cost and DoS surface
6. P1-5 and P1-6 (IV calibration and viability wiring) — Medium — Biased R/R on the core trade decision
7. P1-3 and P1-4 (provenance flags, positioning fixes) — Medium — Fabricated analytics displayed as solved
8. P1-7 (ledger lock, persistence, limits) — Medium — Risk accounting resets and is lost on restart
9. P2 items (validation, frontend, typing) — Medium — UX and data-quality degradation
10. P3 (cost calibration, constants) — Small — Slightly stale frictions

All P0 fixes are local, small diffs with no schema breaking for happy-path consumers; the new fields (is_viable, market_data_valid=False on failure, provenance enums) are additive.
