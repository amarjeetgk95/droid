"""S8 IV Regime Mispricing Strategy (S8SPEC_v1.0).

Exploits structural mispricings between Implied Volatility (IV) and Realized Volatility (RV):
- Regime A (IV Compression, IV/RV < 0.85): Options are underpriced relative to realized moves.
  Strategy enters directional long option structures with the prevailing momentum.
- Regime B (IV Expansion, IV/RV > 1.30): Options are overpriced relative to realized moves.
  Strategy enters defined-risk credit spreads fading extended moves to harvest elevated theta.
"""

from __future__ import annotations

from typing import Literal, Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import polars as pl
import numpy as np

from app.quant.strategies.s8_config import S8Config, create_s8_default_config
from app.quant.strategies.strategies import StrategyCandidate, parse_time_to_minute, get_ist_minute


def classify_iv_regime(
    atm_iv: float,
    realized_vol: float,
    iv_percentile: Optional[float] = None,
    config: Optional[S8Config] = None,
) -> Literal["COMPRESSION", "EXPANSION", "NEUTRAL"]:
    """Classifies market volatility into Compression, Expansion, or Neutral regime."""
    cfg = config or create_s8_default_config()
    if realized_vol <= 0.001 or atm_iv <= 0.001:
        return "NEUTRAL"

    iv_rv_ratio = atm_iv / realized_vol

    # Compression: IV is cheap relative to RV, or IV rank is depressed
    is_compression = (iv_rv_ratio <= cfg.regime.iv_rv_compression_threshold) or (
        iv_percentile is not None and iv_percentile <= cfg.regime.iv_pct_compression_max
    )

    # Expansion: IV is expensive relative to RV, or IV rank is elevated
    is_expansion = (iv_rv_ratio >= cfg.regime.iv_rv_expansion_threshold) or (
        iv_percentile is not None and iv_percentile >= cfg.regime.iv_pct_expansion_min
    )

    if is_compression and not is_expansion:
        return "COMPRESSION"
    if is_expansion and not is_compression:
        return "EXPANSION"
    return "NEUTRAL"


class S8IVRegimeScanner:
    """Quantitative scanner for S8 IV Regime Mispricing."""

    def __init__(self, config: S8Config | None = None):
        self.config = config or create_s8_default_config()
        self.window_a_start = parse_time_to_minute(self.config.limits.regime_a_window_start)
        self.window_a_end = parse_time_to_minute(self.config.limits.regime_a_window_end)
        self.window_b_start = parse_time_to_minute(self.config.limits.regime_b_window_start)
        self.window_b_end = parse_time_to_minute(self.config.limits.regime_b_window_end)

    def scan_dataframe(
        self,
        df: pl.DataFrame,
        custom_iv: Optional[float] = None,
    ) -> list[StrategyCandidate]:
        """Evaluates historical DataFrame using realized volatility and optional IV inputs."""
        if len(df) == 0:
            return []

        timestamps = df["timestamp"].to_list()
        closes = df["close"].to_list()
        atrs = df["atr"].to_list()
        realized_vols = df["realized_vol_20"].to_list()
        ema_fasts = df["ema_fast"].to_list()
        ema_slows = df["ema_slow"].to_list()
        ema_slopes = df["ema_slope_50"].to_list()
        rsis = df["rsi"].to_list()
        vwaps = df["vwap"].to_list()

        candidates: list[StrategyCandidate] = []
        last_signal_bar = -9999
        daily_trades: dict[str, int] = {}
        n = len(df)

        for i in range(25, n):
            if i - last_signal_bar < self.config.limits.cooldown_bars:
                continue

            c = closes[i]
            atr = atrs[i]
            rv = realized_vols[i]
            efast = ema_fasts[i]
            eslow = ema_slows[i]
            slope = ema_slopes[i]
            rsi = rsis[i]
            v = vwaps[i]

            if any(x is None for x in (c, atr, rv, efast, eslow, slope, rsi)):
                continue

            t = timestamps[i]
            ist_min = get_ist_minute(t)

            if hasattr(t, "tzinfo") and t.tzinfo is not None:
                date_key = t.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
            else:
                date_key = str(t)[:10]

            if daily_trades.get(date_key, 0) >= self.config.limits.max_trades_per_day:
                continue

            # IV proxy: use custom_iv if provided, else use annualized ATR proxy.
            # Honesty: 0.90 factor is an ASSUMPTION (not measured IV). Surfaced
            # in gate_margins as iv_proxy assumption, never silent.
            if custom_iv is not None:
                iv_val = float(custom_iv)
                _iv_proxy_assumption: str | None = None
            else:
                iv_val = float(atr / c * np.sqrt(252.0 * 375.0) * 0.90)
                _iv_proxy_assumption = "atr-annualized-0.90-assumption-not-measured-IV"
            regime = classify_iv_regime(iv_val, rv, config=self.config)

            # Regime A: Volatility Compression (Buy Option with Trend Momentum)
            if regime == "COMPRESSION" and (self.window_a_start <= ist_min <= self.window_a_end):
                if efast > eslow and slope > 0.0 and rsi > 50.0:
                    strat_id = "S8_IV_COMPRESSION_LONG"
                    reason = (
                        f"IV Compression regime (IV={iv_val:.3f}, RV={rv:.3f}, Ratio={iv_val/max(rv, 1e-4):.2f}): "
                        f"Trend alignment Long (EMA9 {efast:.1f} > EMA21 {eslow:.1f}, slope={slope:.3f})"
                    )
                    candidates.append(StrategyCandidate(
                        bar_index=i,
                        direction=1,
                        strategy_id=strat_id,
                        entry_ref_price=c,
                        trigger_reason=reason,
                        gate_margins={
                            "iv_rv_ratio": iv_val / max(rv, 1e-4),
                            "regime": 1.0,
                            "k_sl": self.config.exit.k_sl_atr,
                            "k_tp": self.config.exit.k_tp_atr,
                            "atr": atr,
                            "iv_proxy": _iv_proxy_assumption or "measured-custom-iv",
                            "iv_available": custom_iv is not None,
                        },
                    ))
                    last_signal_bar = i
                    daily_trades[date_key] = daily_trades.get(date_key, 0) + 1

                elif efast < eslow and slope < 0.0 and rsi < 50.0:
                    strat_id = "S8_IV_COMPRESSION_SHORT"
                    reason = (
                        f"IV Compression regime (IV={iv_val:.3f}, RV={rv:.3f}, Ratio={iv_val/max(rv, 1e-4):.2f}): "
                        f"Trend alignment Short (EMA9 {efast:.1f} < EMA21 {eslow:.1f}, slope={slope:.3f})"
                    )
                    candidates.append(StrategyCandidate(
                        bar_index=i,
                        direction=-1,
                        strategy_id=strat_id,
                        entry_ref_price=c,
                        trigger_reason=reason,
                        gate_margins={
                            "iv_rv_ratio": iv_val / max(rv, 1e-4),
                            "regime": 1.0,
                            "k_sl": self.config.exit.k_sl_atr,
                            "k_tp": self.config.exit.k_tp_atr,
                            "atr": atr,
                            "iv_proxy": _iv_proxy_assumption or "measured-custom-iv",
                            "iv_available": custom_iv is not None,
                        },
                    ))
                    last_signal_bar = i
                    daily_trades[date_key] = daily_trades.get(date_key, 0) + 1

            # Regime B: Volatility Expansion (Credit Spread Fade / Mean Reversion)
            elif regime == "EXPANSION" and (self.window_b_start <= ist_min <= self.window_b_end):
                # Fade extended upper move (Bear Call Spread bias)
                if rsi >= 65.0 and (c > v + atr if v else True):
                    strat_id = "S8_IV_EXPANSION_FADE_CALL"
                    reason = (
                        f"IV Expansion regime (IV={iv_val:.3f}, RV={rv:.3f}, Ratio={iv_val/max(rv, 1e-4):.2f}): "
                        f"Elevated vol fade on overbought condition (RSI={rsi:.1f}>=65)"
                    )
                    candidates.append(StrategyCandidate(
                        bar_index=i,
                        direction=-1,
                        strategy_id=strat_id,
                        entry_ref_price=c,
                        trigger_reason=reason,
                        gate_margins={
                            "iv_rv_ratio": iv_val / max(rv, 1e-4),
                            "regime": 2.0,
                            "k_sl": 0.8,
                            "k_tp": 1.2,
                            "atr": atr,
                            "iv_proxy": _iv_proxy_assumption or "measured-custom-iv",
                            "iv_available": custom_iv is not None,
                        },
                    ))
                    last_signal_bar = i
                    daily_trades[date_key] = daily_trades.get(date_key, 0) + 1

                # Fade extended lower move (Bull Put Spread bias)
                elif rsi <= 35.0 and (c < v - atr if v else True):
                    strat_id = "S8_IV_EXPANSION_FADE_PUT"
                    reason = (
                        f"IV Expansion regime (IV={iv_val:.3f}, RV={rv:.3f}, Ratio={iv_val/max(rv, 1e-4):.2f}): "
                        f"Elevated vol fade on oversold condition (RSI={rsi:.1f}<=35)"
                    )
                    candidates.append(StrategyCandidate(
                        bar_index=i,
                        direction=1,
                        strategy_id=strat_id,
                        entry_ref_price=c,
                        trigger_reason=reason,
                        gate_margins={
                            "iv_rv_ratio": iv_val / max(rv, 1e-4),
                            "regime": 2.0,
                            "k_sl": 0.8,
                            "k_tp": 1.2,
                            "atr": atr,
                            "iv_proxy": _iv_proxy_assumption or "measured-custom-iv",
                            "iv_available": custom_iv is not None,
                        },
                    ))
                    last_signal_bar = i
                    daily_trades[date_key] = daily_trades.get(date_key, 0) + 1

        return candidates
