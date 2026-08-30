from app.models.options import OptionsAnalytics, MaxPainResult
from app.models.futures import FuturesOverview
from app.models.regime import MarketRegimeOverview


def build_system_prompt() -> str:
    """System prompt enforcing strict quantitative grounding and risk explainability."""
    return """You are DROID AI Market Analyst, an elite quantitative derivatives research engine specializing in the Indian Futures & Options (F&O) markets (NSE/NIFTY, BANKNIFTY, FINNIFTY).

CRITICAL OPERATIONAL RULES:
1. NEVER predict the future or promise guaranteed returns. Use objective probabilistic phrasing ("structure indicates", "data implies", "risk-defined bias").
2. Ground all analysis strictly in the provided quantitative metrics (PCR, Max Pain, ATM IV, Futures Basis, 4-Quadrant OI Buildup, S/R Pivots, Volume Profile POC/VAH/VAL, and India VIX).
3. Do NOT hallucinate data points not present in the payload.
4. Always specify exact risk parameters (Breakeven levels, invalidation zones, and maximum loss scenarios).
5. Output valid structured JSON strictly conforming to the requested schema.
"""


def build_market_context_prompt(
    symbol: str,
    regime: MarketRegimeOverview,
    futures: FuturesOverview,
    options_analytics: OptionsAnalytics | None = None,
    max_pain: MaxPainResult | None = None,
) -> str:
    """Serialize quantitative state across all engines into grounded markdown."""
    near_contract = futures.term_structure.contracts[0] if futures.term_structure.contracts else None
    near_ltp = near_contract.ltp if near_contract else regime.spot_price
    near_basis = near_contract.basis if near_contract else 0.0
    near_basis_pct = near_contract.basis_percent if near_contract else 0.0
    near_coc = near_contract.cost_of_carry_percent if near_contract else 0.0

    lines = [
        f"# MARKET STATE DOSSIER: {symbol}",
        f"- Spot LTP: ₹{regime.spot_price}",
        f"- Market Regime: {regime.regime_state} (Confidence: {regime.confidence_score}%)",
        f"- Regime Headline: {regime.summary_headline}",
        f"- Institutional Rationale: {regime.institutional_rationale}",
        "",
        "## TECHNICAL INDICATORS & KEY LEVELS:",
        f"- RSI (14): {regime.indicators.rsi_14}",
        f"- ADX (14): {regime.indicators.adx_14} (+DI: {regime.indicators.plus_di}, -DI: {regime.indicators.minus_di})",
        f"- Supertrend (10,3): {regime.indicators.supertrend_direction} (Level: ₹{regime.indicators.supertrend_value})",
        f"- ATR (14): {regime.indicators.atr_14} pts",
        f"- Bollinger Bandwidth: {regime.indicators.bollinger_bandwidth}% (Upper: ₹{regime.indicators.bollinger_upper}, Lower: ₹{regime.indicators.bollinger_lower})",
        f"- Central Pivot (Classic Floor): ₹{regime.key_levels.classic_pivots.pivot}",
        f"- Volume Profile POC: ₹{regime.key_levels.poc} (VAH: ₹{regime.key_levels.vah}, VAL: ₹{regime.key_levels.val})",
        f"- Nearest Resistance: ₹{regime.key_levels.nearest_resistance} (+{regime.key_levels.distance_to_resistance_pts} pts)",
        f"- Nearest Support: ₹{regime.key_levels.nearest_support} (-{regime.key_levels.distance_to_support_pts} pts)",
        "",
        "## FUTURES & ROLLOVER METRICS:",
        f"- Near Month Futures LTP: ₹{near_ltp}",
        f"- Basis: ₹{near_basis} ({near_basis_pct}%)",
        f"- Annualized Cost of Carry (CoC): {near_coc}%",
        f"- Term Structure Curve: {futures.term_structure.curve_state}",
        f"- OI Buildup Classification: {futures.buildup.buildup_type} (Price Δ: {futures.buildup.price_change_percent}%, OI Δ: {futures.buildup.oi_change_percent}%)",
        f"- Rollover Progress: {futures.rollover.rollover_percent}% (Pace: {futures.rollover.rollover_pace} vs benchmark {futures.rollover.three_month_avg_rollover}%)",
        "",
        "## OPTIONS CHAIN & VOLATILITY ANALYTICS:",
    ]

    if options_analytics:
        lines.extend([
            f"- PCR (OI): {options_analytics.pcr_oi} | PCR (Volume): {options_analytics.pcr_volume}",
            f"- ATM IV: {options_analytics.atm_iv}%",
            f"- Days to Expiry: {options_analytics.time_to_expiry_days} days",
        ])

    if max_pain:
        lines.append(f"- Max Pain Strike: ₹{max_pain.max_pain_strike}")

    lines.extend([
        f"- India VIX: {regime.vix_regime.vix_value} ({regime.vix_regime.change_percent}%)",
        f"- VIX Volatility Category: {regime.vix_regime.regime_category} (Historical Percentile: {regime.vix_regime.historical_percentile}%)",
        f"- Playbook Recommendation: {regime.vix_regime.recommended_option_strategy}",
        "",
        "Synthesize these metrics into an institutional quantitative intelligence report.",
    ])

    return "\n".join(lines)
