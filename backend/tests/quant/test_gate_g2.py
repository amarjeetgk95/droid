"""Unit tests for Gate G2 robustness evaluator."""

import polars as pl

from app.quant.validation.gate_g2_evaluator import GateG2Evaluator
from app.quant.backtest.backtest_harness import BacktestHarness
from scripts.fetch_fyers_history import generate_synthetic_history
from app.quant.features.feature_engine import CausalFeatureEngine


def _dataset() -> pl.DataFrame:
    return generate_synthetic_history("BSE:SENSEX-INDEX", days=3, base_price=80000.0)


class TestGateG2:
    def test_evaluate_shape(self):
        df = _dataset()
        evaluator = GateG2Evaluator(k_tp=2.0, k_sl=1.0)
        report = evaluator.evaluate(df, strategy_key="S1")
        d = report.to_dict()
        assert d["strategy_key"] == "S1"
        assert d["gate_g2_verdict"] in ("PASSED", "FAILED", "INCONCLUSIVE")
        assert len(d["stress_curve"]) == 4
        assert d["sensitivity_total"] == 3
        assert isinstance(d["verdict_reasons"], list) and d["verdict_reasons"]

    def test_underpowered_inconclusive(self):
        df = _dataset().head(60)
        evaluator = GateG2Evaluator()
        report = evaluator.evaluate(df, strategy_key="S1")
        assert report.gate_g2_verdict == "INCONCLUSIVE"

    def test_s8_included_in_all(self):
        df_raw = _dataset()
        engine_feat = CausalFeatureEngine()
        df = engine_feat.compute_features(df_raw)
        harness = BacktestHarness(trend_aligned=False)
        _, m_all = harness.run_backtest(df=df_raw, strategy_key="ALL")
        _, m_s8 = harness.run_backtest(df=df_raw, strategy_key="S8")
        # ALL must contain at least the S8 candidates.
        assert m_all.total_trades >= m_s8.total_trades
        assert m_s8.total_candidates >= 0
        _ = len(df)
