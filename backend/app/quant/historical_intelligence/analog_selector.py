"""
Analog Selection, De-Duplication, and Aggregation Engine — §11, §14, §15, §19, §20, §22, §23
"""
from __future__ import annotations

from app.quant.historical_intelligence.models import (
    CandleData, NormalizedFeatures, MarketRegime, HistoricalAnalogMatch, AnalogAnalyticsSummary
)
from app.quant.historical_intelligence.feature_extractor import extract_features
from app.quant.historical_intelligence.regime_classifier import classify_regime, are_regimes_compatible
from app.quant.historical_intelligence.session_context import get_session_phase
from app.quant.historical_intelligence.similarity import compute_composite_similarity, cosine_similarity
from app.quant.historical_intelligence.outcome_engine import compute_forward_outcomes


def find_historical_analogs(
    all_candles: list[CandleData],
    current_window_candles: list[CandleData],
    symbol: str = "NIFTY",
    timeframe: str = "5M",
    min_similarity_threshold: float = 0.70,
    top_k: int = 20,
    forward_horizon_bars: int = 10,
    min_separation_bars: int = 6,
    is_crypto: bool = False,
) -> AnalogAnalyticsSummary:
    """
    Scans historical candle archive for matching pattern analogs, applies de-duplication,
    evaluates forward outcomes with ZERO lookahead, and aggregates empirical distributions.
    """
    pattern_len = len(current_window_candles)
    if pattern_len < 5 or len(all_candles) < (pattern_len + forward_horizon_bars + 10):
        return _empty_summary(symbol, timeframe, pattern_len, 0)

    # 1. Extract features for Current Pattern
    current_f = extract_features(current_window_candles)
    current_regime = classify_regime(current_f)
    current_end_ts = current_window_candles[-1].timestamp_utc

    # 2. Sliding Window Scan over Historical Candles (exclude current live pattern window)
    candidates: list[tuple[float, int, NormalizedFeatures, MarketRegime, dict[str, float]]] = []
    n_all = len(all_candles)

    # Fast screening pass (Cosine similarity pre-filter §11)
    step = 1 if n_all < 5000 else 2  # Adaptive scan step for high performance
    for start_idx in range(0, n_all - pattern_len - forward_horizon_bars, step):
        end_idx = start_idx + pattern_len
        window = all_candles[start_idx:end_idx]

        # Prevent comparing against current pattern (lookahead boundary)
        if window[-1].timestamp_utc >= current_end_ts:
            continue

        # Fast cosine screening on normalized returns
        base_p = window[0].open or 1.0
        candidate_returns = [round(((c.close - base_p) / base_p) * 100.0, 4) for c in window]
        fast_sim = cosine_similarity(current_f.normalized_returns, candidate_returns)

        if fast_sim >= 0.55:  # Pre-filter threshold
            cand_f = extract_features(window)
            cand_regime = classify_regime(cand_f)
            
            # Regime compatibility check (§10, §11)
            if are_regimes_compatible(current_regime, cand_regime):
                composite_score, details = compute_composite_similarity(
                    current_f, current_regime, cand_f, cand_regime
                )
                if composite_score >= min_similarity_threshold:
                    candidates.append((composite_score, start_idx, cand_f, cand_regime, details))

    # 3. Sort by Similarity Score Descending
    candidates.sort(key=lambda x: x[0], reverse=True)

    # 4. Analog De-Duplication (§15 — remove overlapping windows)
    selected_analogs: list[HistoricalAnalogMatch] = []
    used_end_indices: list[int] = []

    for score, start_idx, cand_f, cand_regime, details in candidates:
        end_idx = start_idx + pattern_len
        # Check temporal separation from already selected analogs
        if any(abs(end_idx - u) < min_separation_bars for u in used_end_indices):
            continue

        used_end_indices.append(end_idx)

        # 5. Evaluate Forward Outcomes [T+1 ... T+H]
        forward_slice = all_candles[end_idx : end_idx + forward_horizon_bars]
        entry_p = forward_slice[0].open if forward_slice else all_candles[end_idx - 1].close

        outcome = compute_forward_outcomes(forward_slice, entry_price=entry_p)

        matched_window = all_candles[start_idx:end_idx]
        phase = get_session_phase(matched_window[-1].timestamp_utc, is_crypto=is_crypto)

        analog_match = HistoricalAnalogMatch(
            symbol=symbol,
            timeframe=timeframe,
            pattern_start_ts=matched_window[0].timestamp_utc,
            pattern_end_ts=matched_window[-1].timestamp_utc,
            matched_regime=cand_regime,
            session_phase=phase,
            similarity_score=score,
            price_similarity=details.get("price_similarity", score),
            shape_similarity=details.get("shape_similarity", score),
            volatility_similarity=details.get("volatility_similarity", score),
            volume_similarity=details.get("volume_similarity", score),
            trend_similarity=details.get("trend_similarity", score),
            forward_candles_count=outcome.forward_candles_count,
            forward_returns=outcome.forward_returns,
            mfe_pct=outcome.mfe_pct,
            mae_pct=outcome.mae_pct,
            target_hit=outcome.target_hit,
            stop_hit=outcome.stop_hit,
            time_to_target_bars=outcome.time_to_target_bars,
            session_end_return_pct=outcome.session_end_return_pct,
        )
        selected_analogs.append(analog_match)

        if len(selected_analogs) >= top_k:
            break

    # 6. Aggregate Analytics Summary (§19, §20, §21, §22)
    return _aggregate_analog_summary(
        symbol=symbol,
        timeframe=timeframe,
        pattern_window_size=pattern_len,
        total_scanned=len(candidates),
        analogs=selected_analogs,
        current_price=current_window_candles[-1].close,
    )


def _aggregate_analog_summary(
    symbol: str,
    timeframe: str,
    pattern_window_size: int,
    total_scanned: int,
    analogs: list[HistoricalAnalogMatch],
    current_price: float,
) -> AnalogAnalyticsSummary:
    valid_count = len(analogs)
    if valid_count == 0:
        return _empty_summary(symbol, timeframe, pattern_window_size, total_scanned)

    # Sample Confidence (§3, §22)
    if valid_count >= 30:
        sample_conf: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_SAMPLE"] = "HIGH"
    elif valid_count >= 15:
        sample_conf = "MEDIUM"
    elif valid_count >= 8:
        sample_conf = "LOW"
    else:
        sample_conf = "INSUFFICIENT_SAMPLE"

    # Directional probabilities based on session end return
    bullish_ct = sum(1 for a in analogs if a.session_end_return_pct > 0.05)
    bearish_ct = sum(1 for a in analogs if a.session_end_return_pct < -0.05)
    neutral_ct = valid_count - bullish_ct - bearish_ct

    raw_bullish = bullish_ct / valid_count
    raw_bearish = bearish_ct / valid_count
    raw_neutral = neutral_ct / valid_count

    # Similarity-weighted probabilities (§23)
    sum_sim = sum(a.similarity_score for a in analogs) or 1.0
    weighted_bullish = sum(a.similarity_score for a in analogs if a.session_end_return_pct > 0.05) / sum_sim
    weighted_bearish = sum(a.similarity_score for a in analogs if a.session_end_return_pct < -0.05) / sum_sim

    target_hit_prob = sum(1 for a in analogs if a.target_hit) / valid_count
    stop_hit_prob = sum(1 for a in analogs if a.stop_hit) / valid_count

    # MFE & MAE distributions
    mfes = sorted(a.mfe_pct for a in analogs)
    maes = sorted(a.mae_pct for a in analogs)  # negative values

    median_mfe = _percentile(mfes, 0.50)
    mean_mfe = sum(mfes) / valid_count
    p25_mfe = _percentile(mfes, 0.25)
    p75_mfe = _percentile(mfes, 0.75)
    p90_mfe = _percentile(mfes, 0.90)

    median_mae = _percentile(maes, 0.50)
    p75_mae = _percentile(maes, 0.25)  # 75th percentile severity
    p90_mae = _percentile(maes, 0.10)  # 90th percentile severity
    max_mae = min(maes)

    # Time to target
    times = [a.time_to_target_bars for a in analogs if a.time_to_target_bars is not None]
    avg_time = sum(times) / len(times) if times else None

    # Expected Target & Stop Prices
    exp_target_p = round(current_price * (1.0 + (median_mfe / 100.0)), 2) if current_price > 0 else None
    emp_stop_p = round(current_price * (1.0 + (p75_mae / 100.0)), 2) if current_price > 0 else None

    # Empirical Risk to Reward
    risk_rew = abs(median_mfe / max(1e-4, abs(p75_mae)))

    # Composite Historical Intelligence Score (0 - 100)
    avg_sim = sum(a.similarity_score for a in analogs) / valid_count
    dir_edge = abs(weighted_bullish - weighted_bearish)
    hist_score = (avg_sim * 40.0) + (dir_edge * 35.0) + (min(2.0, risk_rew) / 2.0 * 25.0)

    return AnalogAnalyticsSummary(
        symbol=symbol,
        timeframe=timeframe,
        pattern_window_size=pattern_window_size,
        lookback_days=30,
        total_candidates_scanned=total_scanned,
        valid_analogs_found=valid_count,
        sample_confidence=sample_conf,
        raw_bullish_prob=round(raw_bullish, 4),
        raw_bearish_prob=round(raw_bearish, 4),
        raw_neutral_prob=round(raw_neutral, 4),
        weighted_bullish_prob=round(weighted_bullish, 4),
        weighted_bearish_prob=round(weighted_bearish, 4),
        target_hit_probability=round(target_hit_prob, 4),
        stop_hit_probability=round(stop_hit_prob, 4),
        median_mfe_pct=round(median_mfe, 4),
        mean_mfe_pct=round(mean_mfe, 4),
        p25_mfe_pct=round(p25_mfe, 4),
        p75_mfe_pct=round(p75_mfe, 4),
        p90_mfe_pct=round(p90_mfe, 4),
        expected_target_price=exp_target_p,
        median_mae_pct=round(median_mae, 4),
        p75_mae_pct=round(p75_mae, 4),
        p90_mae_pct=round(p90_mae, 4),
        max_mae_pct=round(max_mae, 4),
        empirical_stop_price=emp_stop_p,
        avg_time_to_target_bars=round(avg_time, 1) if avg_time else None,
        empirical_risk_reward=round(risk_rew, 2),
        historical_intelligence_score=round(hist_score, 2),
        top_analogs=analogs,
    )


def _percentile(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * p
    f = int(k)
    c = min(len(sorted_data) - 1, f + 1)
    d = k - f
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * d


def _empty_summary(symbol: str, timeframe: str, window_size: int, total_scanned: int) -> AnalogAnalyticsSummary:
    return AnalogAnalyticsSummary(
        symbol=symbol,
        timeframe=timeframe,
        pattern_window_size=window_size,
        lookback_days=0,
        total_candidates_scanned=total_scanned,
        valid_analogs_found=0,
        sample_confidence="INSUFFICIENT_SAMPLE",
        raw_bullish_prob=0.33,
        raw_bearish_prob=0.33,
        raw_neutral_prob=0.34,
        weighted_bullish_prob=0.33,
        weighted_bearish_prob=0.33,
        target_hit_probability=0.0,
        stop_hit_probability=0.0,
        median_mfe_pct=0.0,
        mean_mfe_pct=0.0,
        p25_mfe_pct=0.0,
        p75_mfe_pct=0.0,
        p90_mfe_pct=0.0,
        expected_target_price=None,
        median_mae_pct=0.0,
        p75_mae_pct=0.0,
        p90_mae_pct=0.0,
        max_mae_pct=0.0,
        empirical_stop_price=None,
        avg_time_to_target_bars=None,
        empirical_risk_reward=1.0,
        historical_intelligence_score=0.0,
        top_analogs=[],
    )
