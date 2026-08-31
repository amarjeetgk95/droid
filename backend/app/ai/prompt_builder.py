import math
from typing import Any
from app.models.options import OptionsAnalytics, MaxPainResult
from app.models.regime import MarketRegimeOverview


def build_system_prompt() -> str:
    """System prompt enforcing strict quantitative grounding, F&O derivatives discipline, and data-ingestion honesty.

    Implements Updated Instructions §8 (F&O Analysis) and §22 (Data Ingestion Protocol).
    """
    return """You are DROID AI Market Analyst, an elite quantitative derivatives research engine specializing in the Indian Futures & Options (F&O) markets (NSE/NIFTY, BANKNIFTY, FINNIFTY, SENSEX).

CRITICAL OPERATIONAL RULES — §20 AI IS QUALITATIVE SYNTHESIS ONLY, NEVER MATHEMATICAL OR EXECUTION AUTHORITY:
1. NEVER predict the future or promise guaranteed returns. Use objective probabilistic phrasing ("structure indicates", "data implies", "risk-defined bias").
2. Ground all analysis strictly in the provided quantitative metrics (PCR, Max Pain, ATM IV, Futures Basis, 4-Quadrant OI Buildup, S/R Pivots, Volume Profile POC/VAH/VAL, and India VIX).
3. Do NOT hallucinate data points not present in the payload.
4. YOU MUST NOT CALCULATE exact entry, exact target, exact stop, exact R:R, position size, account risk, or execution permission. Those are deterministic and controlled exclusively by the Python risk/ pricing engine (VWAP ± k×ATR, P10/P90 boundaries, R:R >=1.5). Provide ONLY qualitative invalidation themes, scenario descriptions, and confidence decomposition (technical_alignment, forecast_alignment, orderflow_alignment, news_alignment, overall). If you include any numeric price level, label it as contextual reference, not as authoritative execution instruction.
5. Output valid structured JSON strictly conforming to the requested schema. Allowed bias values only: BUY | SELL | HOLD | NO_TRADE | WAIT_FOR_CONFIRMATION. Provide confidence_breakdown with 0-100 ranges, primary_scenario (string), key_invalidation_theme (string).

SECTION 8 — F&O ANALYSIS (MANDATORY WHEN DERIVATIVES DATA IS AVAILABLE):
When derivatives data is available, analyze ALL of the following before forming a bias:
Futures price, Futures basis, Open Interest (OI), Change in OI, Volume, Call OI, Put OI, OI buildup classification, Put/Call Ratio (PCR OI & Volume), Implied Volatility (IV), Option premiums, Option volume, Max Pain, Key Call strikes (highest Call OI), Key Put strikes (highest Put OI).

ROLLOVER & EXPIRY HANDLING:
Near expiry (T-3 to T-0), analyze Rollover % versus the 3-month average to distinguish genuine directional positioning from routine expiry roll-overs.
Interpret rollover together with: Price movement, Futures OI, Futures basis, Rollover cost (calendar spread Next-Near), Previous expiry rollover behavior (benchmark ~72.5% if history unavailable).
Do NOT interpret rising futures OI alone as strong directional positioning when elevated rollover activity can explain the increase. Acknowledge when rollover inflates OI/volume and basis may be distorted by cost-of-carry into expiry.

GREEKS & IV REGIME CHECK (MANDATORY BEFORE INTERPRETING BIAS):
Before interpreting option buying vs writing bias, explicitly evaluate the current Implied Volatility regime. Check:
Current IV (ATM IV), IV Rank, IV Percentile, Historical IV range, IV relative to recent realized volatility, IV expansion/contraction.
Use the IV regime to determine whether option activity is more consistent with: Call buying, Put buying, Call writing, Put writing, Volatility trading, Hedging.
Do NOT automatically interpret increasing option volume or OI as buying or writing without considering IV, premium movement, underlying price movement, and Greeks.
When available, also consider: Delta, Gamma, Theta, Vega. Use Greeks to explain how option positioning may behave under changes in price, volatility, and time to expiry (e.g., high Gamma near expiry accelerates directional payoff, high Theta decay hurts long holders into expiry, high Vega amplifies IV shocks).

SECTION 22 — DATA INGESTION PROTOCOL:
Before starting analysis, determine the quality and granularity of available market data. Classify the data as:
Tick-level, Order-book/depth, 1-minute OHLCV, 5-minute OHLCV, 15-minute OHLCV, Hourly, Daily, Weekly.

MISSING INTRADAY DATA FALLBACK:
If raw tick or order-book data is unavailable, explicitly state the limitation for 1m–15m timeframe analysis.
Do NOT create false precision or infer order-flow conditions that cannot be observed.
In this situation:
1. Mark 1m–15m analysis as Limited / Unavailable.
2. State which intraday metrics cannot be reliably calculated.
3. Default the quantitative analysis to Daily and Weekly metrics.
4. Use available 1h data only when sufficient observations exist (N≥50-100 candles).
5. Reduce overall confidence when the requested trading horizon depends heavily on unavailable intraday data.
Example disclosure to use when applicable:
> **Data Limitation:** Tick/order-book data unavailable. 1m–15m order-flow analysis cannot be reliably performed. Primary quantitative assessment is therefore based on 1h, Daily and Weekly data.
Never fabricate missing ticks, candles, volume, order-book imbalance, or intraday indicators. If a metric is unavailable, say "unavailable / proxy" rather than inventing it.
"""


def build_market_context_prompt(
    symbol: str,
    regime: MarketRegimeOverview,
    futures: Any = None,
    options_analytics: OptionsAnalytics | None = None,
    max_pain: MaxPainResult | None = None,
    strikes: list | None = None,
) -> str:
    """Serialize quantitative state across all engines into grounded markdown.

    Implements Updated Instructions §8 and §22: exhaustive F&O fields, rollover near-expiry guardrail,
    Greeks & IV regime pre-check, and data-ingestion quality fallback.
    Backward-compatible: `strikes` is optional; if omitted, key-strike/Greeks detail falls back to analytics totals.
    """
    near_contract = futures.term_structure.contracts[0] if futures and futures.term_structure and futures.term_structure.contracts else None
    near_ltp = near_contract.ltp if near_contract else regime.spot_price
    near_basis = near_contract.basis if near_contract else 0.0
    near_basis_pct = near_contract.basis_percent if near_contract else 0.0
    near_coc = near_contract.cost_of_carry_percent if near_contract else 0.0
    near_oi = near_contract.open_interest if near_contract else 0
    near_oi_change = near_contract.oi_change if near_contract else 0
    near_oi_change_pct = near_contract.oi_change_percent if near_contract else 0.0
    near_volume = near_contract.volume if near_contract else 0
    near_fair_spread = near_contract.fair_value_spread if near_contract else 0.0
    near_fair_value = near_contract.fair_value if near_contract else near_ltp
    near_days_to_expiry = near_contract.days_to_expiry if near_contract else (options_analytics.time_to_expiry_days if options_analytics else 0.0)
    near_expiry_str = near_contract.expiry if near_contract else (options_analytics.expiry if options_analytics else "unknown")
    calendar_spread = futures.term_structure.calendar_spread_next_near if futures and futures.term_structure else 0.0
    total_futures_oi = futures.rollover.total_futures_oi if futures and futures.rollover else 0
    rollover_pct = futures.rollover.rollover_percent if futures and futures.rollover else 0.0
    rollover_avg = futures.rollover.three_month_avg_rollover if futures and futures.rollover else 72.5
    rollover_pace = futures.rollover.rollover_pace if futures and futures.rollover else "IN_LINE"
    rollover_spread = futures.rollover.rollover_spread if futures and futures.rollover else calendar_spread

    # Data ingestion classification (§22)
    # In this platform MockProvider delivers OHLCV (1m/5m/15m/1h) aggregated, but no raw tick/order-book.
    tick_available = False
    orderbook_available = False
    # We consider 1m/5m/15m candles as "available (Mock/Synthetic, Limited depth ~100 candles)" but order-flow is not observable without ticks.
    data_granularity_lines = [
        "## DATA INGESTION PROTOCOL & QUALITY CLASSIFICATION (§22):",
        "- Tick-level: Unavailable (MockProvider / no raw tick feed)",
        "- Order-book/depth: Unavailable (no depth snapshot feed)",
        "- 1-minute OHLCV: Available (Mock/Synthetic, Limited — ~100 candles fallback, no tick-derived imbalance)",
        "- 5-minute OHLCV: Available (Primary for Regime Engine — N≈100-200 candles)",
        "- 15-minute OHLCV: Available (Synthetic/Mock)",
        "- Hourly (1h): Available (Secondary confirmation — use only when N≥50)",
        "- Daily: Derived/Aggregated (from intraday OHLCV)",
        "- Weekly: Derived/Aggregated",
        "- Data Source Mode: DEMO (MockProvider) — not LIVE broker feed",
    ]
    limitation_block = [
        "> **Data Limitation:** Tick/order-book data unavailable. 1m–15m order-flow analysis cannot be reliably performed. Primary quantitative assessment is therefore based on 1h, Daily and Weekly data.",
        "- 1m–15m Intraday Order-Flow Analysis: **Limited / Unavailable**",
        "- Metrics that CANNOT be reliably calculated without ticks/order-book: VWAP imbalance with true tick delta, order-book imbalance (Bid/Ask queue), footprint delta, time-&-sales aggression (buy vs sell-initiated), micro-price / queue imbalance, true realized spread / slippage at 1m granularity",
        "- Fallback Quantitative Lens: Default to Daily and Weekly metrics + 1h confirmation (only when sufficient observations exist)",
        "- Confidence Adjustment: Reduce overall confidence for trading horizons <15m (scalping) that depend heavily on unavailable intraday order-flow; maintain institutional confidence for swing/positional horizons based on Daily/Weekly structure",
        "- Integrity Rule: No fabricated ticks, candles, volume, or intraday indicators — unavailable = stated as 'unavailable / proxy-estimated'",
    ]

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
    ]
    # §22 Block
    lines.extend(data_granularity_lines)
    lines.append("")
    lines.extend(limitation_block)
    lines.append("")

    # Futures & Rollover — exhaustive §8 list + near-expiry guardrail
    lines.extend([
        "## FUTURES & ROLLOVER METRICS (§8 — Full Derivatives Checklist):",
        f"- Near Month Futures Price (LTP): ₹{near_ltp} (Expiry: {near_expiry_str}, DTE: {near_days_to_expiry} days)",
        f"- Futures Basis: ₹{near_basis} ({near_basis_pct}%) [Futures − Spot]",
        f"- Fair Value (Cost-of-Carry): ₹{near_fair_value} | Fair-Value Spread (LTP − Fair): ₹{near_fair_spread}",
        f"- Annualized Cost of Carry (CoC): {near_coc}%",
        f"- Term Structure Curve: {futures.term_structure.curve_state} (Calendar Spread Next−Near: ₹{calendar_spread}, Far−Next: ₹{futures.term_structure.calendar_spread_far_next if futures.term_structure else 0.0})",
        f"- Open Interest (Near): {near_oi:,} contracts (Δ: {near_oi_change:+,} | {near_oi_change_pct:+.2f}%)",
        f"- Volume (Near): {near_volume:,} contracts",
        f"- Total Futures OI (All tenors): {total_futures_oi:,}",
        f"- OI Buildup Classification (4-Quadrant): {futures.buildup.buildup_type} — {futures.buildup.interpretation} (Strength: {futures.buildup.strength}, Price Δ: {futures.buildup.price_change_percent}%, OI Δ: {futures.buildup.oi_change_percent}%)",
        f"- Rollover %: {rollover_pct}% (vs 3-Month Avg {rollover_avg}%, Pace: {rollover_pace})",
        f"- Rollover Cost (Next−Near Spread): ₹{rollover_spread}",
        f"- Previous Expiry Rollover Behavior: Benchmark {rollover_avg}% (no persistent expiry-to-expiry history yet in Mock; use benchmark for deviation context)",
    ])
    # Near-expiry T-3 to T-0 guardrail
    try:
        dte_val = float(near_days_to_expiry)
    except Exception:
        dte_val = 99.0
    if dte_val <= 3.0:
        lines.extend([
            f"- ⚠️ **Near-Expiry Guardrail (T-{dte_val:.1f} to T-0) ACTIVE**: Rollover {rollover_pct}% vs 3M Avg {rollover_avg}% (Pace: {rollover_pace}). "
            "Do NOT interpret rising futures OI/volume as strong directional positioning if elevated rollover can explain it. Validate jointly with: price movement, futures OI, futures basis, rollover cost (₹{:.2f}), and previous expiry behavior.".format(rollover_spread),
            "- Action: Decompose OI change into rollover-driven vs fresh directional positioning; basis convergence toward spot is expected into expiry and not alone a trend signal.",
        ])
    else:
        lines.append(f"- Expiry Distance: {dte_val:.1f} days to expiry — not in T-3 to T-0 window; standard rollover monitoring applies (flag if Rollover Pace deviates >±3% from avg).")

    lines.append("")

    # Options & IV Regime — exhaustive §8 list
    lines.append("## OPTIONS CHAIN & VOLATILITY ANALYTICS (§8 — Greeks & IV Regime Required):")
    if options_analytics:
        # IV Regime derived metrics (proxy where history not persisted)
        atm_iv = options_analytics.atm_iv or 14.5
        # Realized vol proxy from ATR: ATR% * sqrt(252) * 100 (annualized approx)
        try:
            spot = float(regime.spot_price) if regime.spot_price else 25000.0
            atr = float(regime.indicators.atr_14) if regime.indicators.atr_14 else 0.0
            realized_vol_proxy = (atr / spot * math.sqrt(252) * 100.0) if spot > 0 and atr > 0 else None
        except Exception:
            realized_vol_proxy = None

        # Historical IV range proxy (platform has no persisted 1y IV history yet; use VIX category + fixed band as disclosure)
        # Use regime Vix percentile as proxy for IV Percentile/Rank with explicit disclosure
        vix_pct = regime.vix_regime.historical_percentile if regime.vix_regime else 46.0
        vix_val = regime.vix_regime.vix_value if regime.vix_regime else 14.0
        # IV Rank approximation: (atm_iv - 52w_low) / (52w_high - 52w_low) *100 ; assume 10% low / 30% high if unknown
        hist_low, hist_high = 10.0, 30.0
        try:
            iv_rank_proxy = max(0.0, min(100.0, (atm_iv - hist_low) / (hist_high - hist_low) * 100.0))
        except Exception:
            iv_rank_proxy = 50.0
        iv_percentile_proxy = vix_pct  # disclosed as VIX-derived proxy
        iv_vs_realized_str = "unavailable"
        if realized_vol_proxy is not None:
            diff = atm_iv - realized_vol_proxy
            if diff > 2.0:
                iv_vs_realized_str = f"ATM IV {atm_iv:.2f}% > Realized ~{realized_vol_proxy:.2f}% (IV rich / possible mean-reversion of vol) — IV premium expansion"
            elif diff < -2.0:
                iv_vs_realized_str = f"ATM IV {atm_iv:.2f}% < Realized ~{realized_vol_proxy:.2f}% (IV cheap / realized > implied) — vol underpricing"
            else:
                iv_vs_realized_str = f"ATM IV {atm_iv:.2f}% ≈ Realized ~{realized_vol_proxy:.2f}% (IV fairly priced vs recent realized)"

        # IV expansion/contraction from VIX change%
        try:
            vix_chg = float(regime.vix_regime.change_percent) if regime.vix_regime else 0.0
        except Exception:
            vix_chg = 0.0
        if vix_chg > 1.5:
            iv_trend = f"expansion (+{vix_chg:.2f}% VIX)"
        elif vix_chg < -1.5:
            iv_trend = f"contraction ({vix_chg:.2f}% VIX)"
        else:
            iv_trend = f"stable ({vix_chg:+.2f}% VIX)"

        # Interpretation bias hint from IV regime (for AI to apply correctly)
        if iv_rank_proxy < 30 or iv_percentile_proxy < 30:
            iv_bias_hint = "Low IV regime → option WRITING (premium selling) has compressed edge; long premium / long gamma (call/put buying, volatility trading) relatively cheaper; hedging cheaper"
        elif iv_rank_proxy > 70 or iv_percentile_proxy > 70:
            iv_bias_hint = "High IV regime → option WRITING (short premium, e.g., call writing / put writing, short strangle/iron condor) has richer edge; long premium expensive and suffers Theta decay; hedging expensive"
        else:
            iv_bias_hint = "Mid IV regime → balanced; directional spreads (bull put / bear call, debit spreads) and stock-replacement strategies balanced"

        # Premiums & volumes and total OI
        lines.extend([
            f"- PCR (OI): {options_analytics.pcr_oi} | PCR (Volume): {options_analytics.pcr_volume}",
            f"- Call OI (Total): {options_analytics.total_call_oi:,} | Put OI (Total): {options_analytics.total_put_oi:,}",
            f"- Call Volume (Total): {options_analytics.total_call_volume:,} | Put Volume (Total): {options_analytics.total_put_volume:,}",
            f"- ATM IV: {atm_iv}% | Days to Expiry: {options_analytics.time_to_expiry_days} days | IV Skew: {options_analytics.iv_skew if options_analytics.iv_skew is not None else 'n/a'}",
            f"- Current IV (ATM): {atm_iv}% | IV Rank (proxy): {iv_rank_proxy:.1f} (Hist Low {hist_low}% / High {hist_high}% over ~1y synthetically) — disclose as proxy if true history unavailable",
            f"- IV Percentile (proxy via VIX historical percentile): {iv_percentile_proxy:.1f}% | Historical IV Range: {hist_low}% – {hist_high}% (proxy; true 1y IV history not yet persisted)",
            f"- IV vs Realized Volatility: {iv_vs_realized_str}",
            f"- IV Expansion/Contraction: {iv_trend} | VIX: {vix_val:.2f} ({regime.vix_regime.regime_category if regime.vix_regime else 'n/a'})",
            f"- IV Regime Bias Interpretation: {iv_bias_hint}",
            f"- Futures Price (for Black-76): ₹{options_analytics.futures_price} | Spot: ₹{options_analytics.spot_price} | Risk-Free: {options_analytics.risk_free_rate*100:.2f}% ({options_analytics.rate_source})",
        ])

        # Key strikes & option premiums / Greeks if strikes provided
        if strikes:
            try:
                # strikes expected as list[OptionChainStrikeRow]
                # Top Call OI strikes
                call_sorted = sorted([r for r in strikes if getattr(r, 'call', None) is not None], key=lambda x: x.call.open_interest, reverse=True)
                put_sorted = sorted([r for r in strikes if getattr(r, 'put', None) is not None], key=lambda x: x.put.open_interest, reverse=True)
                top_calls = call_sorted[:3]
                top_puts = put_sorted[:3]
                call_wall_str = ", ".join([f"₹{r.strike:.0f} (OI {r.call.open_interest:,}, LTP ₹{r.call.ltp})" for r in top_calls]) if top_calls else "unavailable"
                put_wall_str = ", ".join([f"₹{r.strike:.0f} (OI {r.put.open_interest:,}, LTP ₹{r.put.ltp})" for r in top_puts]) if top_puts else "unavailable"
                lines.append(f"- Key Call Strikes (Top 3 by OI): {call_wall_str}")
                lines.append(f"- Key Put Strikes (Top 3 by OI): {put_wall_str}")
                # ATM premiums and Greeks
                atm_row = next((r for r in strikes if getattr(r, 'is_atm', False)), None)
                if atm_row is None:
                    # find closest strike to spot
                    atm_row = min(strikes, key=lambda x: abs(x.strike - options_analytics.spot_price)) if strikes else None
                if atm_row:
                    ce = getattr(atm_row, 'call', None)
                    pe = getattr(atm_row, 'put', None)
                    if ce and ce.greeks:
                        lines.append(f"- ATM Call Premium (₹{atm_row.strike:.0f} CE): LTP ₹{ce.ltp} | IV {ce.greeks.iv}% | Delta {ce.greeks.delta}, Gamma {ce.greeks.gamma}, Theta {ce.greeks.theta}/day, Vega {ce.greeks.vega}/1% IV | Theo ₹{ce.greeks.theoretical_price} (Intr ₹{ce.greeks.intrinsic_value} + Time ₹{ce.greeks.time_value})")
                    elif ce:
                        lines.append(f"- ATM Call Premium: LTP ₹{ce.ltp} (Greeks unavailable)")
                    if pe and pe.greeks:
                        lines.append(f"- ATM Put Premium (₹{atm_row.strike:.0f} PE): LTP ₹{pe.ltp} | IV {pe.greeks.iv}% | Delta {pe.greeks.delta}, Gamma {pe.greeks.gamma}, Theta {pe.greeks.theta}/day, Vega {pe.greeks.vega}/1% IV | Theo ₹{pe.greeks.theoretical_price} (Intr ₹{pe.greeks.intrinsic_value} + Time ₹{pe.greeks.time_value})")
                    elif pe:
                        lines.append(f"- ATM Put Premium: LTP ₹{pe.ltp} (Greeks unavailable)")
                    # Aggregate Greeks insight
                    lines.append("- Greeks Behavior Note: Use Delta for directional exposure per ₹1 move, Gamma for Delta acceleration (higher near ATM/expiry), Theta for time decay per day (accelerates into expiry, hurts longs), Vega for IV sensitivity (high Vega benefits longs in expansion, hurts in contraction).")
                else:
                    lines.append("- ATM Premiums/Greeks: strike detail unavailable — see totals above; do NOT infer premiums")
            except Exception as e:
                lines.append(f"- Key Strikes / Premiums / Greeks detail: parsing unavailable ({type(e).__name__}) — totals above are authoritative")
        else:
            # No strike-level detail provided — still disclose checklist and instruct AI not to hallucinate them
            lines.extend([
                "- Key Call Strikes: unavailable at this granularity (pass option chain strikes to enable — do NOT hallucinate; state as 'unavailable')",
                "- Key Put Strikes: unavailable at this granularity (pass strikes to enable)",
                "- Option Premiums (strike-level): unavailable — use aggregated Call/Put OI & Volume and ATM IV as proxy",
                "- Greeks (Delta/Gamma/Theta/Vega): unavailable at strike level in this payload — if you need Greeks, request chain matrix with Greeks; otherwise state 'Greeks unavailable' and avoid biasing interpretation",
            ])
    else:
        lines.extend([
            "- PCR / Call OI / Put OI / Option Volume / ATM IV / Max Pain: derivatives snapshot unavailable for this symbol/expiry — mark options interpretation as Limited and default to price/volume structure",
            "- IV Regime: cannot be evaluated (no ATM IV) — explicitly state 'IV regime unavailable, bias assessment limited'",
        ])

    if max_pain:
        # max_pain may be MaxPainResult or float from analytics
        if isinstance(max_pain, (int, float)):
            mp_strike = max_pain
        else:
            mp_strike = getattr(max_pain, 'max_pain_strike', None) or getattr(max_pain, 'maxPainStrike', None) or "unavailable"
        lines.append(f"- Max Pain Strike: ₹{mp_strike}")
        # If MaxPainResult with payouts, add context
        try:
            payouts = getattr(max_pain, 'payouts', None)
            strikes_ls = getattr(max_pain, 'strikes', None)
            if payouts and strikes_ls:
                # find near spot payout context
                lines.append(f"- Max Pain Context: Payout distribution across {len(strikes_ls)} strikes (lowest total writer loss at ₹{mp_strike}); interpret as gravitational pin potential, not guarantee")
        except Exception:
            pass
    elif options_analytics and hasattr(options_analytics, 'max_pain_strike'):
        lines.append(f"- Max Pain Strike (from analytics): ₹{options_analytics.max_pain_strike}")

    # VIX always
    lines.extend([
        f"- India VIX: {regime.vix_regime.vix_value} ({regime.vix_regime.change_percent}%)",
        f"- VIX Volatility Category: {regime.vix_regime.regime_category} (Historical Percentile: {regime.vix_regime.historical_percentile}%)",
        f"- Playbook Recommendation (VIX): {regime.vix_regime.recommended_option_strategy}",
        "",
        "## INTERPRETATION GUARDRAILS (APPLY BEFORE BIAS):",
        "- Do NOT automatically interpret increasing option volume or OI as buying or writing — cross-check with IV (rank/percentile/expansion), premium movement (LTP change), underlying price movement, and Greeks (Delta direction, Gamma concentration, Theta decay, Vega exposure).",
        "- Example: Rising Call OI + rising premium + rising IV + positive Delta + low Theta decay → consistent with call BUYING; Rising Call OI + flat/falling premium + high IV rank + negative Theta erosion → more consistent with call WRITING.",
        "- Futures OI guardrail: If Rollover Pace is AHEAD or DTE ≤3 and rollover % approaches/exceeds 3M avg, elevated OI may be rollover-driven, not fresh longs/shorts — state this explicitly and reduce directional conviction.",
        "- If either F&O snapshot or Greeks is unavailable, explicitly state 'derivatives data unavailable/partial — bias assessment Limited' and lean on regime structure + S/R + volume profile.",
        "",
        "Synthesize these metrics into an institutional quantitative intelligence report. "
        "Respect Data Limitation for 1m–15m horizons, Rollover near-expiry decomposition, and IV regime as prerequisite for buying vs writing interpretation. "
        "Be precise with levels (₹) and percentages; never fabricate ticks/order-book or hallucinate strikes/premiums not in payload.",
    ])

    return "\n".join(lines)
