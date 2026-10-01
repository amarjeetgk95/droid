"""PAP live + research contract tests: real-data-only, shadow-only, honest failures.

No broker, no network: MarketService/regime/options are mocked. Asserts:
- probability distributions sum to ~100 and stay visible (no bare BUY/SELL),
- confidence is null unless calibrated,
- unavailable paths return explicit codes (never zero-filled horizons),
- PAP modules never import execution/risk/broker/order paths,
- research metrics derive from settled rows; ablation/tradability are
  NOT_AVAILABLE (never fabricated).
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.market import DataStatus, NormalizedCandle, NormalizedQuote
from app.services import pap_research, pap_service
from app.services.pap_service import (
    PapUnavailable,
    _alignment,
    _consensus,
    _prediction_label,
    fisher_transform,
    linreg_slope,
    session_vwap,
)


def _quote(ltp: float = 25000.0) -> NormalizedQuote:
    return NormalizedQuote(
        symbol="NSE:NIFTY50-INDEX",
        display_name="NIFTY 50",
        timestamp=datetime.now(timezone.utc),
        ltp=ltp,
        open=24900.0,
        high=25050.0,
        low=24850.0,
        previous_close=24900.0,
        change=100.0,
        change_percent=0.4,
        volume=1000000,
        status=DataStatus.LIVE,
    )


def _candles(n: int = 60, base: float = 25000.0) -> list[NormalizedCandle]:
    out = []
    for i in range(n):
        c = base + i * 0.5 + (i % 5)
        out.append(
            NormalizedCandle(
                timestamp=datetime.now(timezone.utc),
                open=c - 1.0,
                high=c + 2.0,
                low=c - 2.0,
                close=c,
                volume=10000.0 + i * 10.0,
            )
        )
    return out


def _indicators() -> SimpleNamespace:
    return SimpleNamespace(
        rsi_14=58.0,
        adx_14=27.8,
        plus_di=29.0,
        minus_di=17.0,
        atr_14=42.0,
        supertrend_value=24900.0,
        supertrend_direction="BULLISH",
        bollinger_upper=25100.0,
        bollinger_middle=25000.0,
        bollinger_lower=24900.0,
        bollinger_bandwidth=0.8,
        bollinger_pct_b=0.6,
        ema_20=24950.0,
        ema_50=24800.0,
        sma_200=24000.0,
    )


def _key_levels() -> SimpleNamespace:
    piv = SimpleNamespace(pivot=24980.0, r1=25050.0, r2=25100.0, r3=25150.0, r4=None,
                          s1=24900.0, s2=24850.0, s3=24800.0, s4=None)
    return SimpleNamespace(
        classic_pivots=piv, fibonacci_pivots=piv, camarilla_pivots=piv,
        prior_day_high=25000.0, prior_day_low=24800.0, prior_day_close=24900.0,
        day_open=24910.0, poc=24970.0, vah=25020.0, val=24920.0,
        nearest_resistance=25050.0, nearest_support=24900.0,
        distance_to_resistance_pts=50.0, distance_to_support_pts=100.0,
    )


class TestPapMath:
    def test_fisher_needs_data(self):
        assert fisher_transform([1.0, 2.0]) is None
        v = fisher_transform([float(i) for i in range(20)])
        assert v is not None and -4.0 <= v <= 4.0

    def test_lr_slope_needs_data(self):
        assert linreg_slope([1.0, 2.0]) is None
        assert linreg_slope([float(i) for i in range(20)]) is not None
        flat = linreg_slope([100.0] * 20)
        assert flat is not None and abs(flat) < 1e-9

    def test_session_vwap_none_without_volume(self):
        assert session_vwap([]) is None

    def test_prediction_label_never_bare_signal(self):
        assert _prediction_label(68.0, 13.0) == "UP"
        assert _prediction_label(10.0, 70.0) == "DOWN"
        assert _prediction_label(34.0, 33.0) in ("UP", "NEUTRAL", "DOWN")

    def test_consensus_conflict(self):
        assert _consensus({"3m": "UP", "5m": "UP", "10m": "DOWN"}) == "HORIZON CONFLICT"
        assert _consensus({"3m": "UP", "5m": "UP", "10m": "UP"}) == "SHORT-TERM BULLISH"
        assert _consensus({"3m": "DOWN", "5m": "DOWN", "10m": "DOWN"}) == "SHORT-TERM BEARISH"

    def test_alignment_states(self):
        assert _alignment("UP", "LONG") == "ALIGNED"
        assert _alignment("DOWN", "LONG") == "CONFLICT"
        assert _alignment("NEUTRAL", "LONG") == "NEUTRAL"
        assert _alignment("UP", None) == "NO_DROID_SIGNAL"
        assert _alignment(None, "LONG") == "PAP_UNAVAILABLE"


class TestPapLive:
    @pytest.mark.asyncio
    async def test_live_payload_from_real_data(self):
        candles = _candles()
        with (
            patch.object(pap_service.MarketService, "get_quote", new=AsyncMock(return_value=_quote())),
            patch.object(pap_service.MarketService, "get_candles", new=AsyncMock(return_value=candles)),
            patch.object(pap_service.regime_service, "get_technical_indicators", new=AsyncMock(return_value=_indicators())),
            patch.object(pap_service.regime_service, "get_key_levels", new=AsyncMock(return_value=_key_levels())),
            patch("app.services.options_service.options_service.get_option_chain_matrix", new=AsyncMock(side_effect=Exception("no chain"))),
            patch("app.signals.fsm.signal_fsm.list_active", return_value=[]),
        ):
            payload = await pap_service.get_pap_live("NIFTY")
        assert payload["available"] is True
        assert payload["mode"] == "SHADOW" and payload["execution"] == "DISABLED"
        assert payload["model"]["execution"] == "DISABLED"
        assert set(payload["horizons"]) == {"3m", "5m", "10m"}
        for key, h in payload["horizons"].items():
            total = h["up"] + h["neutral"] + h["down"]
            assert 99.0 <= total <= 101.0, key
            assert h["prediction"] in ("UP", "NEUTRAL", "DOWN")
            # Uncalibrated horizons must not carry false-precision confidence.
            if not h["calibrated"]:
                assert h["confidence"] is None
        ms = payload["market_state"]
        for fam in ("fisher", "price_vs_vwap_pct", "adx", "lr_slope", "bb_width_pct"):
            assert fam in ms
        assert payload["droid_alignment"]["alignment"] == "NO_DROID_SIGNAL"
        assert payload["droid_alignment"]["advisory_only"] is True
        assert "explanatory only" in payload["evidence_note"].lower() or "Explanatory" in payload["evidence_note"]

    @pytest.mark.asyncio
    async def test_no_quote_is_unavailable_not_zeros(self):
        with patch.object(pap_service.MarketService, "get_quote", new=AsyncMock(return_value=None)):
            with pytest.raises(PapUnavailable) as exc:
                await pap_service.get_pap_live("NIFTY")
        assert exc.value.code == "NO_MARKET_DATA"
        dead = pap_service.unavailable_payload("NIFTY", exc.value.code, exc.value.detail)
        assert dead["available"] is False
        assert dead["horizons"] is None
        assert dead["droid_alignment"]["alignment"] == "PAP_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_insufficient_candles_is_unavailable(self):
        with (
            patch.object(pap_service.MarketService, "get_quote", new=AsyncMock(return_value=_quote())),
            patch.object(pap_service.MarketService, "get_candles", new=AsyncMock(return_value=_candles(n=5))),
        ):
            with pytest.raises(PapUnavailable) as exc:
                await pap_service.get_pap_live("NIFTY")
        assert exc.value.code == "INSUFFICIENT_HISTORICAL_DATA"

    @pytest.mark.asyncio
    async def test_unknown_instrument_rejected(self):
        with pytest.raises(PapUnavailable) as exc:
            await pap_service.get_pap_live("FAKECOIN")
        assert exc.value.code == "UNKNOWN_INSTRUMENT"

    def test_shadow_only_no_execution_imports(self):
        import re

        import app.services.pap_service as mod
        import app.api.pap as api

        # Only real import statements count — prose/docstrings mentioning
        # "risk limits" or "broker sessions" as prohibitions are fine.
        import_re = re.compile(r"^\s*(?:import|from)\s+([a-z0-9_.]+)", re.MULTILINE)
        forbidden = ("order", "execution", "broker", "risk_engine", "position_siz", "paper_engine", "kill_switch", "telegram")
        from pathlib import Path

        for m in (mod, api):
            src = Path(m.__file__).read_text(encoding="utf-8")
            imported = " ".join(import_re.findall(src)).lower()
            for token in forbidden:
                assert token not in imported, f"{m.__name__} imports forbidden '{token}'"
            # No order lifecycle verbs in the PAP stack at all.
            lowered = src.lower()
            for verb in ("execute-paper", "execute_paper", "cancel_order", "modify_order", "place_order"):
                assert verb not in lowered, f"{m.__name__} contains '{verb}'"


class TestPapResearch:
    def _settled(self, n: int = 40, pred: str = "BULLISH", outcome: str = "BULLISH") -> list[dict]:
        rows = []
        for i in range(n):
            rows.append({
                "time": f"2026-09-2{i % 9}T04:3{i % 10}:00+00:00",
                "predicted_bias": pred,
                "outcome_name": outcome,
                "p_up": 68.0 if pred == "BULLISH" else (13.0 if pred == "BEARISH" else 20.0),
                "p_neutral": 19.0,
                "p_down": 13.0 if pred == "BULLISH" else (68.0 if pred == "BEARISH" else 20.0),
                "max_prob": 0.68,
                "correct": pred == outcome,
                "target_spec_version": "v1-atr-band",
                "market_regime": "TRENDING_BULLISH",
            })
        return rows

    def test_insufficient_sample_has_nulls_not_zeros(self):
        out = pap_research.summarize(self._settled(n=5))
        assert out["status"] == "INSUFFICIENT_SAMPLE"
        assert out["metrics"] is None and out["lift"] is None

    def test_summary_reports_baseline_and_lift(self):
        rows = self._settled(n=20, pred="BULLISH", outcome="BULLISH") + self._settled(n=20, pred="BEARISH", outcome="NEUTRAL")
        out = pap_research.summarize(rows)
        assert out["status"] == "OK"
        assert out["metrics"]["balanced_accuracy"] is not None
        assert out["baseline"]["balanced_accuracy"] is not None
        assert out["lift"]["balanced_accuracy"] is not None
        assert out["walk_forward"]["status"] in ("PASS", "FAIL", "INCONCLUSIVE", "INSUFFICIENT_SAMPLE")
        # Economic filter unevaluated -> verdict can never be a false PASS.
        if out["walk_forward"]["status"] == "PASS":
            assert out["walk_forward"]["economic_evaluated"] is True
        else:
            assert out["walk_forward"].get("economic_evaluated") in (True, False)

    def test_walk_forward_caps_without_cost_model(self):
        rows = self._settled(n=60, pred="BULLISH", outcome="BULLISH")
        wf = pap_research._walk_forward(rows)
        assert wf["status"] in ("FAIL", "INCONCLUSIVE", "INSUFFICIENT_SAMPLE")
        assert wf.get("economic_evaluated") is False or wf["status"] == "INSUFFICIENT_SAMPLE"

    def test_calibration_buckets_honest(self):
        out = pap_research.calibration_buckets(self._settled(n=10))
        assert len(out["buckets"]) == 5
        empty = [b for b in out["buckets"] if b["n"] == 0]
        for b in empty:
            assert b["predicted"] is None and b["status"] == "INSUFFICIENT_SAMPLE"

    def test_group_by_flags_small_cells(self):
        rows = self._settled(n=5)
        groups = pap_research.group_by(rows, "market_regime")
        assert groups and all(g["status"] == "INSUFFICIENT_SAMPLE" for g in groups)

    def test_research_guard_without_db(self):
        from app.api import pap as pap_api

        guard = pap_api._research_db_guard(None)
        assert guard["data"]["status"] == "INSUFFICIENT_SAMPLE"
        assert guard["data"]["n"] == 0

    @pytest.mark.asyncio
    async def test_chart_joins_real_candles_only(self):
        from app.api import pap as pap_api

        candles = [
            SimpleNamespace(
                timestamp=datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc),
                open=25000.0, high=25010.0, low=24990.0, close=25005.0, volume=1000.0,
            ),
            SimpleNamespace(
                timestamp=datetime(2026, 9, 23, 4, 1, tzinfo=timezone.utc),
                open=25005.0, high=25015.0, low=25000.0, close=25012.0, volume=1000.0,
            ),
        ]
        with patch.object(pap_service.MarketService, "get_candles", new=AsyncMock(return_value=candles)):
            res = await pap_api.pap_research_chart(instrument="NIFTY", horizon_minutes=None, limit=200, session=None)
        assert len(res["data"]["candles"]) == 2
        # No DB -> no markers invented.
        assert res["data"]["markers"] == []
        assert res["data"]["status"] == "INSUFFICIENT_SAMPLE"

    @pytest.mark.asyncio
    async def test_chart_without_candles_is_insufficient(self):
        from app.api import pap as pap_api

        with patch.object(pap_service.MarketService, "get_candles", new=AsyncMock(return_value=[])):
            res = await pap_api.pap_research_chart(instrument="NIFTY", horizon_minutes=None, limit=200, session=None)
        assert res["data"]["status"] == "INSUFFICIENT_SAMPLE"
        assert res["data"]["candles"] == []

    @pytest.mark.asyncio
    async def test_ablation_and_tradability_not_available(self):
        from app.api import pap as pap_api

        abl = await pap_api.pap_research_ablation()
        assert abl["data"]["status"] == "NOT_AVAILABLE"
        assert abl["data"]["experiments"] == []
        tr = await pap_api.pap_research_tradability()
        assert tr["data"]["status"] == "NOT_AVAILABLE"
        assert tr["data"]["net_expectancy_pct"] is None
