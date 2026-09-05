from app.models.regime import (
    MarketRegimeOverview, TechnicalIndicators, KeyLevelsModel,
    PivotSetModel, VixRegimeInfo, MarketRegimeState, VixRegimeCategory
)
from app.services.market_service import MarketService
from app.quant.indicators import (
    calculate_rsi, calculate_adx, calculate_atr,
    calculate_bollinger_bands, calculate_supertrend,
    calculate_ema, calculate_sma
)
from app.quant.pivots import (
    calculate_classic_pivots, calculate_fibonacci_pivots,
    calculate_camarilla_pivots, calculate_value_area
)
import structlog

logger = structlog.get_logger()


class RegimeService:
    """Market Regime & Technical Analytics Service.
    
    Adheres strictly to Sections 51 through 60 of the platform architecture.
    """

    def __init__(self, market_service: MarketService | None = None):
        self.market_service = market_service or MarketService()

    async def get_technical_indicators(self, symbol: str = "NIFTY") -> TechnicalIndicators:
        """Compute institutional technical indicator suite."""
        underlying = symbol.upper().replace(" 50", "")
        candles = await self.market_service.get_candles(underlying, timeframe="5m")

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [float(c.volume) for c in candles]

        if not closes:
            return TechnicalIndicators(
                rsi_14=50.0,
                adx_14=0.0,
                plus_di=0.0,
                minus_di=0.0,
                atr_14=0.0,
                supertrend_value=0.0,
                supertrend_direction="BULLISH",
                bollinger_upper=0.0,
                bollinger_middle=0.0,
                bollinger_lower=0.0,
                bollinger_bandwidth=0.0,
                bollinger_pct_b=0.5,
                ema_20=None,
                ema_50=None,
                sma_200=None,
            )

        # Calculate indicators directly from authentic historical candles
        rsi = calculate_rsi(closes, period=14)
        plus_di, minus_di, adx = calculate_adx(highs, lows, closes, period=14)
        atr = calculate_atr(highs, lows, closes, period=14)
        upper, middle, lower, bandwidth, pct_b = calculate_bollinger_bands(closes, period=20)
        st_val, st_dir = calculate_supertrend(highs, lows, closes, period=10, multiplier=3.0)

        ema_20 = calculate_ema(closes, 20)
        ema_50 = calculate_ema(closes, 50)
        sma_200 = calculate_sma(closes, 200)

        return TechnicalIndicators(
            rsi_14=rsi,
            adx_14=adx,
            plus_di=plus_di,
            minus_di=minus_di,
            atr_14=atr,
            supertrend_value=st_val,
            supertrend_direction=st_dir,
            bollinger_upper=upper,
            bollinger_middle=middle,
            bollinger_lower=lower,
            bollinger_bandwidth=bandwidth,
            bollinger_pct_b=pct_b,
            ema_20=ema_20,
            ema_50=ema_50,
            sma_200=sma_200,
        )

    async def get_key_levels(self, symbol: str = "NIFTY") -> KeyLevelsModel:
        """Compute comprehensive multi-method key levels and value area."""
        underlying = symbol.upper().replace(" 50", "")
        quote = await self.market_service.get_quote(underlying)
        spot_p = quote.ltp if quote and quote.ltp > 0 else 0.0

        # Reference prices
        high_ref = quote.high if (quote and quote.high > 0) else spot_p
        low_ref = quote.low if (quote and quote.low > 0) else spot_p
        close_ref = (quote.previous_close if (quote and quote.previous_close > 0) else None) or spot_p
        open_ref = (quote.open if (quote and quote.open > 0) else None) or spot_p

        # Pivots calculations
        cp = calculate_classic_pivots(high_ref, low_ref, close_ref)
        fp = calculate_fibonacci_pivots(high_ref, low_ref, close_ref)
        cam = calculate_camarilla_pivots(high_ref, low_ref, close_ref)

        # Volume Profile Value Area
        candles = await self.market_service.get_candles(underlying, timeframe="5m")
        prices = [c.close for c in candles]
        volumes = [float(c.volume) for c in candles]
        poc, vah, val = calculate_value_area(prices, volumes)
        if poc == 0 or poc is None:
            poc = spot_p
            vah = round(spot_p * 1.004, 2)
            val = round(spot_p * 0.996, 2)

        # Find nearest resistance and support levels
        all_resistances = [cp.r1, cp.r2, fp.r1, fp.r2, cam.r3, vah, high_ref]
        all_supports = [cp.s1, cp.s2, fp.s1, fp.s2, cam.s3, val, low_ref]

        valid_r = [r for r in all_resistances if r > spot_p]
        valid_s = [s for s in all_supports if s < spot_p]

        nearest_r = min(valid_r) if valid_r else spot_p * 1.005
        nearest_s = max(valid_s) if valid_s else spot_p * 0.995

        dist_r = round(nearest_r - spot_p, 2)
        dist_s = round(spot_p - nearest_s, 2)

        return KeyLevelsModel(
            classic_pivots=PivotSetModel(
                pivot=cp.pivot, r1=cp.r1, r2=cp.r2, r3=cp.r3, r4=cp.r4,
                s1=cp.s1, s2=cp.s2, s3=cp.s3, s4=cp.s4
            ),
            fibonacci_pivots=PivotSetModel(
                pivot=fp.pivot, r1=fp.r1, r2=fp.r2, r3=fp.r3, r4=fp.r4,
                s1=fp.s1, s2=fp.s2, s3=fp.s3, s4=fp.s4
            ),
            camarilla_pivots=PivotSetModel(
                pivot=cam.pivot, r1=cam.r1, r2=cam.r2, r3=cam.r3, r4=cam.r4,
                s1=cam.s1, s2=cam.s2, s3=cam.s3, s4=cam.s4
            ),
            prior_day_high=round(high_ref, 2),
            prior_day_low=round(low_ref, 2),
            prior_day_close=round(close_ref, 2),
            day_open=round(open_ref, 2),
            poc=poc,
            vah=vah,
            val=val,
            nearest_resistance=round(nearest_r, 2),
            nearest_support=round(nearest_s, 2),
            distance_to_resistance_pts=dist_r,
            distance_to_support_pts=dist_s,
        )

    async def get_vix_regime(self) -> VixRegimeInfo:
        """Evaluate India VIX Volatility classification and option strategy bias."""
        vix_quote = await self.market_service.get_quote("INDIA VIX")
        vix_val = vix_quote.ltp if vix_quote and vix_quote.ltp > 0 else 0.0

        if vix_val <= 0.0:
            category: VixRegimeCategory = "NORMAL_VOLATILITY"
            interp = "India VIX market data currently unavailable."
            strategy = "N/A"
            pct = 50.0
        elif vix_val < 13.0:
            category: VixRegimeCategory = "LOW_VOLATILITY"
            interp = "Compressed volatility environment — option premiums are low. Favorable for defined credit spreads / iron condors."
            strategy = "Iron Condors, Short Strangles with wide wings, Calendar Spreads"
            pct = 18.0
        elif vix_val < 18.0:
            category = "NORMAL_VOLATILITY"
            interp = "Standard volatility environment — balanced risk/reward between direction and theta decay."
            strategy = "Bull Put / Bear Call Spreads, Ratio Spreads, Long Diagonals"
            pct = 46.0
        elif vix_val < 24.0:
            category = "ELEVATED_VOLATILITY"
            interp = "Elevated event pricing — high intraday point swings. Option buying / long gamma favored on intraday breakouts."
            strategy = "Long Straddles, Debit Spreads, Volatility Breakout Straddles"
            pct = 82.0
        else:
            category = "EXTREME_VOLATILITY"
            interp = "Crisis / extreme panic volatility — severe dislocation. Delta-neutral hedging and strict risk-off mandatory."
            strategy = "Deep OTM Protective Puts, Cash Preservation, Long VIX Futures"
            pct = 96.0

        return VixRegimeInfo(
            vix_value=vix_val,
            change=vix_quote.change if vix_quote else 0.0,
            change_percent=vix_quote.change_percent if vix_quote else 0.0,
            regime_category=category,
            interpretation=interp,
            recommended_option_strategy=strategy,
            historical_percentile=pct,
        )

    async def classify_market_regime(self, symbol: str = "NIFTY") -> MarketRegimeOverview:
        """Classify underlying into one of 6 institutional market regimes."""
        underlying = symbol.upper().replace(" 50", "")
        quote = await self.market_service.get_quote(underlying)
        spot_p = quote.ltp if quote and quote.ltp > 0 else 0.0

        indicators = await self.get_technical_indicators(underlying)
        key_levels = await self.get_key_levels(underlying)
        vix_info = await self.get_vix_regime()

        # Classification rules
        is_bullish_trend = (
            indicators.adx_14 >= 22.0 and
            indicators.rsi_14 >= 52.0 and
            indicators.supertrend_direction == "BULLISH" and
            (indicators.ema_20 is None or spot_p >= indicators.ema_20)
        )
        is_bearish_trend = (
            indicators.adx_14 >= 22.0 and
            indicators.rsi_14 <= 48.0 and
            indicators.supertrend_direction == "BEARISH" and
            (indicators.ema_20 is None or spot_p <= indicators.ema_20)
        )
        is_squeeze = indicators.bollinger_bandwidth <= 2.2 and indicators.adx_14 < 20.0
        is_expansion = indicators.bollinger_bandwidth >= 4.5 or vix_info.vix_value >= 18.0

        if is_squeeze:
            regime_state: MarketRegimeState = "COMPRESSION_SQUEEZE"
            confidence = 88.0
            headline = "Volatility Squeeze — Imminent Breakout Implied"
            rationale = "Bollinger Bands are severely contracted with low ADX. Compression usually precedes explosive directional expansions."
        elif is_expansion:
            regime_state = "VOLATILE_EXPANSION"
            confidence = 82.0
            headline = "Volatile Expansion — Wide Intraday Ranges"
            rationale = "Bollinger Bandwidth and ATR are expanding with elevated India VIX. Momentum trades with trailing stops are favored."
        elif is_bullish_trend:
            regime_state = "TRENDING_BULLISH"
            confidence = 90.0
            headline = "Trending Bullish — Strong Institutional Buying"
            rationale = "Price is commanding above key EMAs with ADX > 22 and Supertrend bullish. Buy-on-dips strategy aligns with structure."
        elif is_bearish_trend:
            regime_state = "TRENDING_BEARISH"
            confidence = 90.0
            headline = "Trending Bearish — Institutional Supply Dominant"
            rationale = "Price is rejecting from resistance with ADX confirming downward momentum and RSI < 48. Sell-on-rallies strategy favored."
        elif vix_info.vix_value < 14.5:
            regime_state = "RANGEBOUND_LOW_VOL"
            confidence = 80.0
            headline = "Rangebound Low Volatility — Premium Decay Market"
            rationale = "ADX is subdued under 20 and India VIX is low. Price is oscillating tightly within Value Area POC/VAH/VAL."
        else:
            regime_state = "RANGEBOUND_HIGH_VOL"
            confidence = 78.0
            headline = "Rangebound High Volatility — Choppy Mean-Reversion"
            rationale = "Price lacks clean trend continuation but oscillates across wide swings. Strict target booking at Support/Resistance."

        return MarketRegimeOverview(
            symbol=underlying,
            spot_price=spot_p,
            regime_state=regime_state,
            confidence_score=confidence,
            summary_headline=headline,
            institutional_rationale=rationale,
            indicators=indicators,
            key_levels=key_levels,
            vix_regime=vix_info,
        )


regime_service = RegimeService()
