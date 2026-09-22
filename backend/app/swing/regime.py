"""
Market Regime Engine for Swing Trading (v5.0 §8 & §9).
Classifies broad market environment (NIFTY 50 / BANKNIFTY) into:
  - BULL (normal risk)
  - NEUTRAL (selective setups)
  - DISTRIBUTION (stricter filters, lower size)
  - BEAR (restrict new longs)
  - HIGH_VOLATILITY (reduce position size)
  - DATA_UNCERTAIN (ABSTAIN)
Includes hysteresis to prevent daily whipsaws.
"""
from __future__ import annotations

from typing import Any
from app.swing.models import MarketRegime, MarketRegimeType
from app.swing.technical import compute_ema, compute_sma, compute_atr


class RegimeClassifier:
    def __init__(self, hysteresis_bars: int = 2):
        self.hysteresis_bars = hysteresis_bars
        self._last_regime: MarketRegimeType = "NEUTRAL"
        self._persistence_counter: int = 0

    def evaluate_benchmark(
        self,
        nifty_candles: list[dict[str, Any]],
        symbol: str = "NIFTY",
    ) -> MarketRegime:
        """Evaluates completed daily candles of NIFTY to detect market regime.

        Fail-closed: confidence is None + INSUFFICIENT_DATA/UNVETTED, never fixed
        60/65/75/80/85 presented as measured. Regime label is deterministic from
        MA structure; confidence is unmeasured.
        """
        if not nifty_candles or len(nifty_candles) < 20:
            return MarketRegime(
                regime="DATA_UNCERTAIN",
                confidence=None,
                confidence_status="INSUFFICIENT_DATA",
                benchmark_symbol=symbol,
                reasons=["Insufficient benchmark candle history for regime determination."],
            )

        closes = [float(c["close"]) for c in nifty_candles]
        highs = [float(c["high"]) for c in nifty_candles]
        lows = [float(c["low"]) for c in nifty_candles]

        curr_close = closes[-1]
        prev_close = closes[-2] if len(closes) > 1 else curr_close
        day_chg_pct = round(((curr_close - prev_close) / prev_close) * 100.0, 2)

        ema20_series = compute_ema(closes, 20)
        sma50_series = compute_sma(closes, 50)
        sma200_series = compute_sma(closes, 200)

        ema20 = ema20_series[-1] if len(ema20_series) >= 20 else curr_close
        sma50 = sma50_series[-1] if len(sma50_series) >= 50 else curr_close
        sma200 = sma200_series[-1] if len(sma200_series) >= 200 else None

        # 20-day high and drawdown
        recent_20_high = max(highs[-20:])
        drawdown_pct = round(((curr_close - recent_20_high) / recent_20_high) * 100.0, 2)

        # Volatility check via 14-day ATR %
        atr_series = compute_atr(nifty_candles, 14)
        atr14 = atr_series[-1]
        atr_pct = (atr14 / curr_close * 100.0) if curr_close > 0 else 1.0

        reasons: list[str] = []
        raw_regime: MarketRegimeType = "NEUTRAL"
        # Unmeasured by construction: None + UNVETTED, never 60/65/75/80/85.
        confidence: float | None = None
        confidence_status: str = "UNVETTED"

        above_ema20 = curr_close > ema20
        above_sma50 = curr_close > sma50
        above_sma200 = (curr_close > sma200) if sma200 else True

        if above_ema20:
            reasons.append(f"Price above 20 EMA ({round(ema20, 1)})")
        else:
            reasons.append(f"Price below 20 EMA ({round(ema20, 1)})")

        if above_sma50:
            reasons.append(f"Price above 50 SMA ({round(sma50, 1)})")
        else:
            reasons.append(f"Price below 50 SMA ({round(sma50, 1)})")

        if atr_pct > 1.8:
            raw_regime = "HIGH_VOLATILITY"
            reasons.append(f"NIFTY Daily ATR is elevated at {round(atr_pct, 2)}% (High Volatility).")
        elif above_ema20 and above_sma50 and above_sma200:
            raw_regime = "BULL"
            reasons.append("Full bullish moving-average stack (Price > 20 EMA > 50 SMA > 200 SMA).")
        elif not above_ema20 and above_sma50:
            raw_regime = "DISTRIBUTION"
            reasons.append("Mild distribution: Broken 20 EMA but holding 50 SMA.")
        elif not above_ema20 and not above_sma50:
            raw_regime = "BEAR"
            reasons.append("Bearish regime: Price below both 20 EMA and 50 SMA.")
        else:
            raw_regime = "NEUTRAL"
            reasons.append("Mixed signals across moving average structure.")
        reasons.append("Regime confidence unmeasured (UNVETTED): fixed 60/65/75/80/85 removed.")

        # Hysteresis (§9): avoid single-day regime flips. Confidence is unmeasured
        # (UNVETTED), so hysteresis is purely bar-count + BEAR/HIGH_VOLATILITY
        # priority — never a confidence-gated flip off fixed 60/65/75/80/85.
        if raw_regime == self._last_regime:
            self._persistence_counter += 1
        else:
            if self._persistence_counter >= self.hysteresis_bars or raw_regime in ("BEAR", "HIGH_VOLATILITY"):
                self._last_regime = raw_regime
                self._persistence_counter = 1
            else:
                reasons.append(f"Hysteresis applied: candidate {raw_regime} deferred (retained {self._last_regime}).")
                raw_regime = self._last_regime
                self._persistence_counter += 1

        # MA alignment is structural (not a measured confidence): None when the
        # MA stack is incomplete, else the deterministic stack score with explicit
        # fallback status. Never a silent 50.0 presented as measured.
        try:
            _stack_complete = len(closes) >= 50
        except Exception:
            _stack_complete = False
        if not _stack_complete:
            ma_score = None
            _ma_status = "INSUFFICIENT_DATA"
        else:
            if raw_regime == "BULL":
                ma_score = 90.0
            elif raw_regime == "DISTRIBUTION":
                ma_score = 45.0
            elif raw_regime == "BEAR":
                ma_score = 15.0
            else:
                ma_score = 50.0
            _ma_status = "fallback"

        return MarketRegime(
            regime=raw_regime,
            confidence=confidence,
            confidence_status=confidence_status,
            persistence_bars=self._persistence_counter,
            benchmark_symbol=symbol,
            benchmark_price=round(curr_close, 2),
            benchmark_change_pct=day_chg_pct,
            ma_alignment_score=ma_score,
            ma_alignment_status=_ma_status,
            recent_drawdown_pct=drawdown_pct,
            reasons=reasons,
        )

    def enrich_regime_with_iv(
        self,
        regime: MarketRegime,
        current_iv: float,
        iv_history: list[float] | None = None,
    ) -> MarketRegime:
        """
        Enriches technical regime with IV percentile and classification.
        Fail-closed: empty IV history yields None + INSUFFICIENT_DATA, never a
        silent 50.0 percentile.
        """
        from app.swing.technical import compute_iv_percentile, classify_iv_regime
        if not iv_history:
            regime.iv_percentile = None
            try:
                regime.iv_percentile_status = "INSUFFICIENT_DATA"  # type: ignore[attr-defined]
            except Exception:
                pass
            regime.iv_regime = "UNKNOWN"
            regime.reasons.append("Implied Volatility environment: UNKNOWN (INSUFFICIENT_DATA: empty IV history, no 50.0 fallback)")
            return regime
        pctl = compute_iv_percentile(current_iv, iv_history or [])
        iv_reg = classify_iv_regime(pctl)
        regime.iv_percentile = pctl
        regime.iv_regime = iv_reg
        regime.reasons.append(f"Implied Volatility environment: {iv_reg} (IV Rank: {pctl:.1f}%)")
        return regime


market_regime_classifier = RegimeClassifier(hysteresis_bars=2)

