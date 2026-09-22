"""
HUD data-contract tests for VORTEX-SNAP (§43): strict real-data default,
explicit low-trust regime fallbacks, real ATR-14, and typed structural levels.
"""
import pytest
from fastapi.testclient import TestClient

import app.api.vortex as vortex_api
from app.main import app
from app.quant.data.dataset_manager import DatasetManager
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from scripts.fetch_fyers_history import generate_synthetic_history
from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.features.translation import TranslationRatioEngine
from app.signals.strategies.vortex_snap.features.regime import MarketRegimeEngine
from app.signals.strategies.vortex_snap.types import MarketRegime
from app.signals.strategies.vortex_snap.tests.conftest import (
    create_candle,
    generate_flat_candles,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestStrictRealDataDefault:
    def test_unverified_parquet_503s_on_live_hud_path(self, client, monkeypatch, tmp_path):
        """A parquet that exists but is not market data must be refused too.

        Regression test for the defeated guard: a generated series was persisted to
        a real-data path and the loader read file *presence* as authenticity, so the
        live HUD served simulated candles tagged ``is_simulated: false``. The fixture
        here is built from the repository's own generator and deliberately labelled
        with a real broker source, which only the statistical screen can catch.
        """
        monkeypatch.delenv("VORTEX_SNAP_REQUIRE_REAL_DATA", raising=False)

        frame = generate_synthetic_history(symbol="BSE:SENSEX-INDEX", days=5, base_price=80000.0)
        DatasetManager(base_dir=tmp_path).save_dataset(
            frame, instrument="sensex", timeframe="1m", source="fyers_api_v3"
        )
        # Swap in a fully isolated loader: all lookup roots derive from this
        # tmp root, so real datasets on disk cannot be reached.
        monkeypatch.setattr(
            vortex_api, "_data_loader", HistoricalDataLoader(raw_data_dir=tmp_path)
        )

        resp = client.get("/api/v1/strategies/vortex-snap/microstructure/SENSEX?bars=60")
        assert resp.status_code == 503

    def test_missing_parquet_503s_on_live_hud_path(self, client, monkeypatch, tmp_path):
        # Isolate from any real dataset on disk (data/historical/parquet or
        # data/raw): point the loader at an empty tree so the live HUD path has
        # neither live WS bars nor a parquet to fall back to. Strict default
        # must 503, never silently serve the seed-42 simulation.
        monkeypatch.delenv("VORTEX_SNAP_REQUIRE_REAL_DATA", raising=False)
        empty_root = tmp_path / "raw"
        empty_root.mkdir()
        monkeypatch.setattr(
            vortex_api, "_data_loader", HistoricalDataLoader(raw_data_dir=empty_root)
        )
        resp = client.get("/api/v1/strategies/vortex-snap/microstructure/NIFTY?bars=60")
        assert resp.status_code == 503
        assert "Real market data required" in resp.json().get("detail", "")

    def test_backtest_explicit_synthetic_flag_still_works(self, client):
        # Backtest carries an explicit synthetic opt-in, but a verified real
        # dataset (data/historical/parquet) is still preferred when present.
        # The contract asserted here is honesty, not the storage form: the
        # reported source must never claim real data when it is simulated.
        resp = client.post(
            "/api/v1/strategies/vortex-snap/backtest",
            json={"symbol": "NIFTY", "slippage_stress": 1.0, "execution_lag": 0,
                  "initial_capital": 1000000.0, "max_bars": 300},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        src = data["data_source"]
        assert src["type"] in ("synthetic", "parquet")
        assert src["is_simulated"] == (src["type"] == "synthetic" or not src["provenance_verified"])

    def test_ablation_explicit_synthetic_flag_still_works(self, client):
        resp = client.get("/api/v1/strategies/vortex-snap/ablation?symbol=NIFTY&sample_bars=400")
        assert resp.status_code == 200
        data = resp.json()["data"]
        src = data["data_source"]
        assert src["type"] in ("synthetic", "parquet")
        assert src["is_simulated"] == (src["type"] == "synthetic" or not src["provenance_verified"])


class TestRegimeFallbackMarked:
    def setup_method(self):
        self.regime_engine = MarketRegimeEngine()
        self.comp_engine = CompressionEngine()
        self.press_engine = DirectionalPressureEngine()
        self.trans_engine = TranslationRatioEngine()

    def test_insufficient_history_is_low_trust_unknown(self):
        candles = generate_flat_candles(10)
        comp = self.comp_engine.compute(candles)
        press = self.press_engine.compute(candles)
        trans = self.trans_engine.compute(candles, press)
        res = self.regime_engine.compute(candles, comp, press, trans)
        assert res.regime == MarketRegime.UNKNOWN
        assert 0.0 <= res.regime_confidence <= 0.30

    def test_no_hardcoded_060_confidence_anywhere(self):
        # Sweep a full deterministic synthetic session: no regime call may ever
        # return exactly the old hardcoded 0.60 "as if measured".
        from datetime import datetime, timezone

        candles = HistoricalDataLoader.generate_synthetic_session(
            date_obj=datetime.now(timezone.utc), seed=42
        )
        for end in range(20, len(candles), 15):
            window = candles[max(0, end - 60):end]
            comp = self.comp_engine.compute(window)
            press = self.press_engine.compute(window)
            trans = self.trans_engine.compute(window, press)
            res = self.regime_engine.compute(window, comp, press, trans)
            assert res.regime_confidence != 0.60


class TestHudPayloadContract:
    def test_hud_carries_source_timestamps_atr_and_typed_levels(self, client, monkeypatch):
        # Strict-by-default on the live path; opt in explicitly so this contract
        # test does not depend on a verified real dataset being on disk.
        monkeypatch.setenv("VORTEX_SNAP_REQUIRE_REAL_DATA", "false")
        resp = client.get("/api/v1/strategies/vortex-snap/microstructure/SENSEX?bars=60")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # data_source block
        src = data["data_source"]
        assert src["type"] in ("parquet", "synthetic")
        assert src["is_simulated"] == (src["type"] == "synthetic" or not src["provenance_verified"])
        assert src["provenance_verified"] == (not src["is_simulated"])
        assert "path" in src and "note" in src

        # last-candle freshness for frontend-side age handling
        assert isinstance(data["last_candle_timestamp_ms"], int)
        assert isinstance(data["last_candle_timestamp"], str)
        assert isinstance(data["server_now_ms"], int)

        # real ATR-14, never the 0.0 placeholder
        assert data["market_regime"]["atr_14"] > 0.0
        assert "is_fallback" in data["market_regime"]

        # typed levels passthrough
        lvls = data["structural_levels"]
        assert "nearest_support_type" in lvls and "nearest_resistance_type" in lvls
        assert "nearest_support_detail" in lvls and "nearest_resistance_detail" in lvls
        assert isinstance(lvls["levels"], list) and len(lvls["levels"]) > 0
        sample = lvls["levels"][0]
        for key in ("level_type", "relevance", "touches", "rejections",
                    "is_broken", "is_retest", "distance_points"):
            assert key in sample, f"level missing passthrough key: {key}"

    def test_nearest_support_type_is_labeled_even_when_high_type(self):
        # Price broke above a prior swing high: nearest support below price keeps
        # its native HIGH type — labeled, never silently relabelled.
        from app.signals.strategies.vortex_snap.features.structural_levels import (
            StructuralLevelEngine,
        )

        candles = [create_candle(1000 + i * 60000, 24090, 24105, 24085, 24100) for i in range(20)]
        engine = StructuralLevelEngine()
        res = engine.compute(candles_1m=candles, pdh=24050.0)
        assert res.nearest_support is not None
        assert res.nearest_support.price < candles[-1].close
        # The type travels with the level — the HUD exposes it verbatim.
        assert res.nearest_support.level_type is not None
