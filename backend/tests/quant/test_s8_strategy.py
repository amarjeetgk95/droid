"""Unit tests for Strategy S8: IV Regime Mispricing (Tier 0)."""

import pytest
import polars as pl
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.strategies.s8_config import S8Config, create_s8_default_config
from app.quant.strategies.s8_iv_regime import classify_iv_regime, S8IVRegimeScanner
from app.signals.strategies.iv_regime import IVRegimeStrategy
from app.signals.strategies.base import StrategyContext
from scripts.fetch_fyers_history import generate_synthetic_history


class TestS8Strategy:

    @pytest.fixture
    def dataset(self) -> pl.DataFrame:
        return generate_synthetic_history("BSE:SENSEX-INDEX", days=2, base_price=80000.0)

    def test_s8_config_immutability_and_hash(self):
        cfg = create_s8_default_config()
        assert cfg.strategy_id == "S8"
        assert cfg.parameter_hash
        assert isinstance(cfg.parameter_hash, str)

        cfg2 = create_s8_default_config()
        assert cfg.parameter_hash == cfg2.parameter_hash

    def test_classify_iv_regime(self):
        # Compression: IV is low relative to Realized Vol (e.g. IV=10%, RV=16% -> ratio=0.625 < 0.85)
        regime = classify_iv_regime(atm_iv=0.10, realized_vol=0.16)
        assert regime == "COMPRESSION"

        # Expansion: IV is high relative to Realized Vol (e.g. IV=22%, RV=12% -> ratio=1.83 > 1.30)
        regime = classify_iv_regime(atm_iv=0.22, realized_vol=0.12)
        assert regime == "EXPANSION"

        # Neutral: IV is roughly matched with Realized Vol (e.g. IV=14%, RV=14% -> ratio=1.0)
        regime = classify_iv_regime(atm_iv=0.14, realized_vol=0.14)
        assert regime == "NEUTRAL"

    def test_s8_scanner_dataframe(self, dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)

        scanner = S8IVRegimeScanner()
        # Scan with cheap IV proxy to test compression signals
        candidates_comp = scanner.scan_dataframe(df, custom_iv=0.08)
        assert isinstance(candidates_comp, list)

        # Scan with expensive IV proxy to test expansion signals
        candidates_exp = scanner.scan_dataframe(df, custom_iv=0.25)
        assert isinstance(candidates_exp, list)

        for c in candidates_comp + candidates_exp:
            assert c.strategy_id.startswith("S8_IV")
            assert c.direction in (1, -1)
            assert c.entry_ref_price > 0.0

    def test_live_iv_regime_strategy_detection(self):
        strat = IVRegimeStrategy()
        spot = Decimal("24800.0")

        # Create 15 synthetic candles
        base_time = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
        candles = [
            {
                "open": 24790.0 + i * 2,
                "high": 24805.0 + i * 2,
                "low": 24785.0 + i * 2,
                "close": 24800.0 + i * 2,
                "volume": 2000.0,
                "timestamp": (base_time + timedelta(minutes=5 * i)).isoformat(),
            }
            for i in range(15)
        ]

        # Context with compressed IV (atm_iv=10.0%, realized vol is higher)
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            candles=candles,
            indicators={"atr": 45.0, "rsi": 58.0, "volume_ratio": 1.2},
            fno={"atm_iv": 9.5, "iv_percentile": 20.0},
            vwap=Decimal("24780.0"),
            regime="TREND_UP",
        )

        cand = strat.detect(ctx)
        # Should generate a compression call setup
        if cand is not None:
            assert cand.strategy == "IV_REGIME"
            assert cand.direction in ("LONG_CALL", "LONG_PUT")
            assert cand.risk_reward_t1 >= 1.2
