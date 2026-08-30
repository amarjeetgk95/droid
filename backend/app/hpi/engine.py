"""HPI pattern engine — coverage-aware historical setup analysis (§15).

The engine dynamically uses whatever historical period is currently available.
It never assumes two years, never reconstructs deleted data, and reduces
confidence when coverage is limited or derivative datasets are missing.
"""
from __future__ import annotations

from app.hpi import constants as C
from app.hpi.models import CoverageReport, HPIAnalysis, HPISetup
from app.hpi.service import HPIService, CANDLE_CATEGORIES

# Base confidence before coverage adjustments.
BASE_CONFIDENCE = 78.0
# Full confidence is reached with >= FULL_COVERAGE_MONTHS of history.
FULL_COVERAGE_MONTHS = 6.0
# Below this, flag a limited historical sample.
LIMITED_SAMPLE_MONTHS = 3.0
# Confidence multiplier when derivative datasets are partial/missing.
PARTIAL_DERIVATIVE_PENALTY = 0.85

WINDOW = 12          # signature window length (bars)
FORWARD = 6          # forward window for outcome stats
SIMILAR_TOP_K = 5


def _signature(closes: list[float], i: int, w: int) -> tuple[float, float, float] | None:
    """(total return, volatility of bar returns, high-low range) for window ending at i."""
    if i - w + 1 < 0:
        return None
    seg = closes[i - w + 1: i + 1]
    rets = [(seg[k + 1] - seg[k]) / seg[k] for k in range(len(seg) - 1)]
    total = (seg[-1] - seg[0]) / seg[0]
    mean = sum(rets) / len(rets) if rets else 0.0
    vol = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 if rets else 0.0
    hi, lo = max(seg), min(seg)
    rng = (hi - lo) / seg[0] if seg[0] else 0.0
    return total, vol, rng


def _similarity(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    dr = abs(a[0] - b[0]) / (abs(b[0]) + 0.01)
    dv = abs(a[1] - b[1]) / (b[1] + 0.0001)
    dg = abs(a[2] - b[2]) / (b[2] + 0.0001)
    return 1.0 / (1.0 + 0.5 * dr + 0.25 * dv + 0.25 * dg)


class HPITrendPatternEngine:
    def __init__(self, service: HPIService):
        self.service = service

    def analyze(self, symbol: str, timeframe: str = "5m") -> HPIAnalysis:
        sym = symbol.upper()
        coverage: CoverageReport = self.service.get_coverage(sym)

        if not coverage.derivative_enabled:
            return self._empty(sym, timeframe, coverage,
                               note=f"{sym} derivative data is disabled — no derivative confirmation claimed (§2).")

        # Prefer 1m market data, fall back to futures candles.
        candles: list[tuple] = []
        for cat in ("1m_market_data", "futures"):
            if cat in CANDLE_CATEGORIES:
                recs = self.service.store.records(sym, cat)
                if recs:
                    candles = recs
                    break
        if not candles:
            return self._empty(
                sym, timeframe, coverage,
                missing=coverage.missing_datasets[0] if coverage.missing_datasets else None,
                note="No historical candles available — run a Historical Import for this derivative.",
            )
        return self._analyze_candles(sym, timeframe, coverage, candles)

    def _analyze_candles(self, sym: str, timeframe: str, coverage: CoverageReport,
                         candles: list[tuple]) -> HPIAnalysis:
        closes = [float(r[4]) for r in candles]
        sigs = [_signature(closes, i, WINDOW) for i in range(len(closes))]
        current_idx = len(closes) - 1
        current_sig = sigs[current_idx]
        if current_sig is None:
            return self._empty(sym, timeframe, coverage, note="Insufficient bars for analysis.")

        scored = []
        for i, s in enumerate(sigs):
            if s is None or i >= current_idx - FORWARD:
                continue
            fwd_ret = (closes[min(i + FORWARD, len(closes) - 1)] - closes[i]) / closes[i]
            scored.append((i, s, _similarity(current_sig, s), fwd_ret))

        scored.sort(key=lambda x: x[2], reverse=True)
        top = scored[:200]
        similar_setups = len(top)

        setups: list[HPISetup] = []
        bull = neutral = bear = 0
        fwd_sum = 0.0
        for i, s, sim, fwd in top:
            if fwd > 0.001:
                bull += 1
            elif fwd < -0.001:
                bear += 1
            else:
                neutral += 1
            fwd_sum += fwd
        for i, s, sim, fwd in top[:SIMILAR_TOP_K]:
            setups.append(HPISetup(
                signature=f"{s[0] * 100:+.2f}% / vol {s[1] * 100:.2f}% / range {s[2] * 100:.2f}%",
                similar_count=similar_setups,
                bullish_pct=round(100.0 * bull / similar_setups, 1) if similar_setups else 0.0,
                neutral_pct=round(100.0 * neutral / similar_setups, 1) if similar_setups else 0.0,
                bearish_pct=round(100.0 * bear / similar_setups, 1) if similar_setups else 0.0,
                avg_forward_move_pct=round(fwd_sum / similar_setups * 100, 2) if similar_setups else 0.0,
                similarity=round(sim, 3),
            ))

        months = coverage.historical_coverage_months
        coverage_factor = min(1.0, months / FULL_COVERAGE_MONTHS)
        confidence = BASE_CONFIDENCE * coverage_factor
        quality = top[0][2] if top else 0.0
        confidence *= (0.8 + 0.2 * quality)

        warnings: list[str] = []
        if months < LIMITED_SAMPLE_MONTHS:
            warnings.append(f"Limited historical sample ({months:g} months available)")
        if coverage.overall == "PARTIAL":
            warnings.append("Derivative Coverage: Partial — some datasets were deleted or are unavailable")
            confidence *= PARTIAL_DERIVATIVE_PENALTY
        if similar_setups < 30:
            warnings.append("Few comparable historical setups found")

        confidence = round(min(confidence, 95.0), 1)
        label = f"{months:g} months"
        if months < LIMITED_SAMPLE_MONTHS:
            label += " (limited sample)"

        missing = None
        if coverage.overall == "PARTIAL":
            missing = ", ".join(coverage.missing_datasets) if coverage.missing_datasets else (
                coverage.deleted_ranges[0].split(":")[0] if coverage.deleted_ranges else None
            )
        elif coverage.overall == "MISSING" and coverage.missing_datasets:
            missing = coverage.missing_datasets[0]

        return HPIAnalysis(
            symbol=sym,
            timeframe=timeframe,
            historical_coverage_months=months,
            historical_coverage_label=label,
            similar_setups=similar_setups,
            confidence=confidence,
            warnings=warnings,
            derivative_coverage=coverage.overall,
            missing_dataset=missing,
            coverage_report=coverage,
            setups=setups,
            note=None,
        )

    def _empty(self, symbol: str, timeframe: str, coverage: CoverageReport,
               missing: str | None = None, note: str | None = None) -> HPIAnalysis:
        warnings: list[str] = []
        if not coverage.derivative_enabled:
            warnings.append(f"{symbol} derivative data is disabled by the user")
        else:
            warnings.append("No historical derivative data available")
        return HPIAnalysis(
            symbol=symbol.upper(),
            timeframe=timeframe,
            historical_coverage_months=0.0,
            historical_coverage_label="0 months",
            similar_setups=0,
            confidence=0.0,
            warnings=warnings,
            derivative_coverage=coverage.overall,
            missing_dataset=missing,
            coverage_report=coverage,
            setups=[],
            note=note,
        )
