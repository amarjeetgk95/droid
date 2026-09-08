"""
Crypto Multi-Domain Confluence Engine with Dynamic Weight Renormalization — §16, §35
Weights:
  - Technical Structure: 40%
  - Multi-Timeframe Alignment (1M, 5M, 15M): 20%
  - Derivatives & Order Book (Funding Rate, OI, Depth Imbalance): 20%
  - Market Regime (Trend, Range, Compression Squeeze): 10%
  - Sentiment & Advisory AI (Fear & Greed, Dominance): 10%

Quality target: 80% win rate.
Baseline is neutral (50.0) — each domain must EARN its contribution by scoring > 55.
Scores below 45 are penalized. ARMED threshold raised to 78.0.
"""
from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

DEFAULT_CRYPTO_WEIGHTS = {
    "technical": 0.40,
    "mtf": 0.20,
    "derivatives": 0.20,
    "regime": 0.10,
    "sentiment": 0.10,
}

ARMED_THRESHOLD = 78.0
ORDERBOOK_DEGRADED_HAIRCUT = 8.0
DERIVATIVES_DEGRADED_HAIRCUT = 8.0
AI_UNAVAILABLE_HAIRCUT = 6.0
VWAP_DEGRADED_HAIRCUT = 6.0


class CryptoConfluenceEngine:
    """
    Fuses technical, multi-timeframe, order book, derivatives, and sentiment metrics
    into a calibrated confidence score with dynamic weight renormalization and haircuts.
    """

    def __init__(self, weights: Optional[dict] = None):
        self.weights = weights or DEFAULT_CRYPTO_WEIGHTS

    def evaluate_technical_score(self, ctx: Any, direction: str) -> float:
        """Score technical indicators: EMA stack, VWAP distance, and volume surge.
        Baseline 50.0 — domain must EARN its weight. Penalize misalignment."""
        score = 50.0
        is_long = direction == "LONG"

        try:
            ema_9 = float(getattr(ctx, "ema_9_1m", 0.0) or 0.0)
            ema_21 = float(getattr(ctx, "ema_21_1m", 0.0) or 0.0)
            ema_50 = float(getattr(ctx, "ema_50_1m", 0.0) or 0.0)

            if ema_9 > 0 and ema_21 > 0:
                if is_long and ema_9 > ema_21:
                    score += 12.0
                    if ema_50 > 0 and ema_21 > ema_50:
                        score += 8.0
                elif not is_long and ema_9 < ema_21:
                    score += 12.0
                    if ema_50 > 0 and ema_21 < ema_50:
                        score += 8.0
                else:
                    score -= 12.0

            vwap = float(getattr(ctx, "vwap_session", 0.0) or 0.0)
            curr = float(getattr(ctx, "current_price", 0.0) or 0.0)
            if vwap > 0 and curr > 0:
                if is_long and curr >= vwap:
                    score += 10.0
                elif not is_long and curr <= vwap:
                    score += 10.0
                else:
                    score -= 8.0

            rsi = float(getattr(ctx, "rsi_14_1m", 50.0) or 50.0)
            if is_long and rsi >= 55 and rsi <= 75:
                score += 8.0
            elif not is_long and rsi <= 45 and rsi >= 25:
                score += 8.0
            elif is_long and rsi > 80:
                score -= 10.0
            elif not is_long and rsi < 20:
                score -= 10.0

            vol_ratio = float(getattr(ctx, "volume_surge_ratio", 1.0) or 1.0)
            if vol_ratio >= 2.0:
                score += 10.0
            elif vol_ratio >= 1.5:
                score += 5.0
            elif vol_ratio < 0.7:
                score -= 10.0

        except Exception as e:
            logger.debug("crypto_technical_scoring_error", error=str(e))

        return max(15.0, min(95.0, score))

    def evaluate_mtf_score(self, ctx: Any, direction: str) -> float:
        """Score multi-timeframe alignment across 1m, 5m, and 15m candles.
        Baseline 50.0 — both 5m AND 15m must align to earn the weight."""
        score = 50.0
        is_long = direction == "LONG"

        try:
            c_5m = getattr(ctx, "candles_5m", []) or []
            c_15m = getattr(ctx, "candles_15m", []) or []

            m5_aligned = False
            m15_aligned = False

            if len(c_5m) >= 3:
                c5_close = c_5m[-1].close
                c5_open = c_5m[-3].open
                if is_long and c5_close > c5_open:
                    score += 15.0
                    m5_aligned = True
                elif not is_long and c5_close < c5_open:
                    score += 15.0
                    m5_aligned = True
                else:
                    score -= 10.0

            if len(c_15m) >= 2:
                c15_close = c_15m[-1].close
                c15_open = c_15m[-2].open
                if is_long and c15_close > c15_open:
                    score += 15.0
                    m15_aligned = True
                elif not is_long and c15_close < c15_open:
                    score += 15.0
                    m15_aligned = True
                else:
                    score -= 10.0

            if m5_aligned and m15_aligned:
                score += 5.0

        except Exception as e:
            logger.debug("crypto_mtf_scoring_error", error=str(e))

        return max(15.0, min(95.0, score))

    def evaluate_derivatives_score(self, ctx: Any, direction: str) -> tuple[float, bool]:
        """Score funding rate, order book depth imbalance, and open interest.
        Baseline 50.0 — both OB AND funding must align."""
        score = 50.0
        degraded = False
        is_long = direction == "LONG"
        ob_aligned = False
        fr_aligned = False

        try:
            ob = getattr(ctx, "orderbook", None)
            derivs = getattr(ctx, "derivatives", None)

            if ob and hasattr(ob, "depth_imbalance_pct"):
                imb = float(getattr(ob, "depth_imbalance_pct", 0.0) or 0.0) / 100.0
                if is_long and imb > 0.15:
                    score += 15.0
                    ob_aligned = True
                elif not is_long and imb < -0.15:
                    score += 15.0
                    ob_aligned = True
                elif (is_long and imb < -0.20) or (not is_long and imb > 0.20):
                    score -= 15.0
            else:
                degraded = True

            if derivs and hasattr(derivs, "funding_rate"):
                fr = float(derivs.funding_rate or 0.0)
                if is_long and fr < -0.0002:
                    score += 12.0
                    fr_aligned = True
                elif not is_long and fr > 0.0004:
                    score += 12.0
                    fr_aligned = True
            else:
                degraded = True

            if not ob_aligned or not fr_aligned:
                score -= 8.0

        except Exception as e:
            logger.debug("crypto_derivatives_scoring_error", error=str(e))
            degraded = True

        return max(15.0, min(95.0, score)), degraded

    def fuse(
        self,
        symbol: str,
        direction: str,
        strategy: str,
        ctx: Any,
        regime: str = "TREND_UP",
        sentiment_score: Optional[float] = None,
    ) -> tuple[float, dict[str, Any]]:
        """Compute final fused confidence score with dynamic weight renormalization."""
        tech_score = self.evaluate_technical_score(ctx, direction)
        mtf_score = self.evaluate_mtf_score(ctx, direction)
        derivs_score, derivs_degraded = self.evaluate_derivatives_score(ctx, direction)

        # Regime score
        r_up = str(regime or "RANGE").upper()
        is_long = direction == "LONG"
        regime_score = 70.0
        if "TREND" in r_up:
            if (is_long and "UP" in r_up) or (not is_long and "DOWN" in r_up):
                regime_score = 85.0
            else:
                regime_score = 45.0
        elif "COMPRESSION" in r_up:
            regime_score = 65.0
        elif "HIGH_VOL" in r_up:
            regime_score = 75.0

        sent_score = sentiment_score if sentiment_score is not None else 65.0

        active_weights = {
            "technical": self.weights["technical"],
            "mtf": self.weights["mtf"],
            "derivatives": self.weights["derivatives"],
            "regime": self.weights["regime"],
            "sentiment": self.weights["sentiment"],
        }
        scores = {
            "technical": tech_score,
            "mtf": mtf_score,
            "derivatives": derivs_score,
            "regime": regime_score,
            "sentiment": sent_score,
        }

        total_w = 0.0
        fused = 0.0
        penalty_count = 0
        for domain, w in active_weights.items():
            s = scores[domain]
            if s >= 55.0:
                contribution = s * w
                fused += contribution
                total_w += w
            elif s < 45.0:
                penalty_count += 1
            else:
                total_w += w

        if total_w > 0:
            fused = fused / total_w
        else:
            fused = 50.0

        if penalty_count >= 2:
            fused -= 10.0

        if derivs_degraded:
            fused -= DERIVATIVES_DEGRADED_HAIRCUT

        vwap_val = getattr(ctx, "vwap_session", 0.0)
        if not vwap_val or vwap_val <= 0:
            fused -= VWAP_DEGRADED_HAIRCUT

        final_score = round(float(max(15.0, min(96.0, fused))), 1)

        breakdown = {
            "technical": round(tech_score, 1),
            "mtf": round(mtf_score, 1),
            "derivatives": round(derivs_score, 1),
            "regime": round(regime_score, 1),
            "sentiment": round(sent_score, 1),
            "derivatives_degraded": derivs_degraded,
            "fused_confidence": final_score,
        }

        return final_score, breakdown


crypto_confluence_engine = CryptoConfluenceEngine()
