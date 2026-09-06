import math
from datetime import datetime, date, timezone
from app.models.options import (
    OptionGreeks, OptionSide, OptionChainStrikeRow,
    OptionChainResponse, OptionsAnalytics, MaxPainResult,
    InstitutionalStrikeFlow, InstitutionalFlowResponse
)
from app.models.market import NormalizedOptionQuote
from app.services.market_service import MarketService
from app.services.contract_master import contract_master_service
from app.quant.black76 import black76_greeks
from app.quant.iv_solver import calculate_iv_black76
from app.quant.expiry_math import calculate_time_to_expiry, get_risk_free_rate
import structlog

logger = structlog.get_logger()


class OptionsService:
    """Options Analytics Service.
    
    Generates interactive strike matrices, calculates analytical Greeks,
    inverts Implied Volatilities, calculates Put-Call Ratios, and derives Max Pain.
    """

    def __init__(self, market_service: MarketService | None = None):
        self.market_service = market_service or MarketService()

    async def get_option_chain_matrix(
        self,
        symbol: str = "NIFTY",
        expiry_str: str | None = None,
    ) -> OptionChainResponse:
        """Construct full interactive Option Chain with Greeks and Analytics."""
        underlying = symbol.upper().replace(" 50", "")
        spot_quote = await self.market_service.get_quote(underlying)
        spot_price = spot_quote.ltp if spot_quote.ltp > 0 else (81500.0 if "SENSEX" in underlying else 52000.0 if "BANK" in underlying else 24200.0 if "FIN" in underlying else 25000.0)

        # Resolve available expiries
        expiries_res = contract_master_service.resolve_expiries(underlying)
        available_expiries = expiries_res.all_expiries
        if not available_expiries:
            target_expiry_date = datetime.now(timezone.utc).date()
            exp_strings = [target_expiry_date.isoformat()]
        else:
            exp_strings = [d.isoformat() for d in available_expiries]
            if expiry_str and expiry_str in exp_strings:
                target_expiry_date = date.fromisoformat(expiry_str)
            else:
                target_expiry_date = available_expiries[0]

        now = datetime.now(timezone.utc)
        t = calculate_time_to_expiry(now, target_expiry_date)
        r, r_source = get_risk_free_rate()

        # Estimated cost-of-carry futures price
        futures_price = round(spot_price * math.exp(r * t), 2)

        # Retrieve raw options from provider
        expiry_dt = datetime.combine(target_expiry_date, datetime.min.time(), tzinfo=timezone.utc)
        raw_quotes = await self.market_service.get_option_chain(underlying, expiry_dt)

        # Group raw quotes by strike
        strikes_map: dict[float, dict[str, NormalizedOptionQuote]] = {}
        for q in raw_quotes:
            if q.strike not in strikes_map:
                strikes_map[q.strike] = {}
            strikes_map[q.strike][q.option_type] = q

        if not strikes_map:
            analytics = OptionsAnalytics(
                symbol=underlying,
                spot_price=spot_price,
                futures_price=futures_price,
                expiry=target_expiry_date.isoformat(),
                atm_strike=spot_price,
                atm_iv=None,
                pcr_oi=0.0,
                pcr_volume=0.0,
                max_pain_strike=spot_price,
                total_call_oi=0,
                total_put_oi=0,
                total_call_volume=0,
                total_put_volume=0,
                iv_skew=None,
                time_to_expiry_days=round(t * 365.25, 2),
                risk_free_rate=r,
                rate_source=r_source,
            )
            return OptionChainResponse(
                underlying=underlying,
                spot_price=spot_price,
                futures_price=futures_price,
                expiry=target_expiry_date.isoformat(),
                expiries=exp_strings,
                analytics=analytics,
                strikes=[],
            )

        all_strikes = sorted(strikes_map.keys())
        if not all_strikes:
            all_strikes = [spot_price]

        # Find ATM strike
        atm_strike = min(all_strikes, key=lambda k: abs(k - spot_price))

        # Pass 1: Solve for baseline ATM IV
        atm_ce = strikes_map.get(atm_strike, {}).get("CE")
        atm_pe = strikes_map.get(atm_strike, {}).get("PE")
        atm_iv_ce = calculate_iv_black76("CE", atm_ce.ltp, futures_price, atm_strike, t, r) if atm_ce and atm_ce.ltp > 0 else None
        atm_iv_pe = calculate_iv_black76("PE", atm_pe.ltp, futures_price, atm_strike, t, r) if atm_pe and atm_pe.ltp > 0 else None

        if atm_iv_ce and atm_iv_pe:
            base_atm_iv = round((atm_iv_ce + atm_iv_pe) / 2.0, 4)
        elif atm_iv_ce:
            base_atm_iv = atm_iv_ce
        elif atm_iv_pe:
            base_atm_iv = atm_iv_pe
        else:
            base_atm_iv = 0.135

        strike_rows: list[OptionChainStrikeRow] = []
        total_ce_oi = 0
        total_pe_oi = 0
        total_ce_vol = 0
        total_pe_vol = 0

        for strike in all_strikes:
            ce_raw = strikes_map.get(strike, {}).get("CE")
            pe_raw = strikes_map.get(strike, {}).get("PE")

            ce_side: OptionSide | None = None
            pe_side: OptionSide | None = None

            m = (strike - spot_price) / spot_price if spot_price > 0 else 0.0

            # Build Call side
            if ce_raw:
                total_ce_oi += ce_raw.oi
                total_ce_vol += ce_raw.volume
                iv_ce = calculate_iv_black76("CE", ce_raw.ltp, futures_price, strike, t, r)
                if iv_ce is None or iv_ce <= 0.005:
                    calc_iv_ce = round(base_atm_iv * (1.0 + 0.18 * (m ** 2) - 0.06 * m), 4)
                else:
                    calc_iv_ce = iv_ce

                g_ce = black76_greeks("CE", futures_price, strike, t, r, calc_iv_ce)
                ce_oi_change = getattr(ce_raw, "oi_change", 0) or 0
                ce_chg = getattr(ce_raw, "change", 0.0) or 0.0
                ce_chg_pct = getattr(ce_raw, "change_percent", 0.0) or 0.0

                ce_side = OptionSide(
                    symbol=ce_raw.contract_id,
                    instrument_token=getattr(ce_raw, "instrument", None),
                    ltp=ce_raw.ltp,
                    change=ce_chg,
                    change_percent=ce_chg_pct,
                    volume=ce_raw.volume,
                    open_interest=ce_raw.oi,
                    oi_change=ce_oi_change,
                    bid=ce_raw.bid,
                    ask=ce_raw.ask,
                    is_itm=strike < spot_price,
                    greeks=OptionGreeks(
                        delta=g_ce.delta,
                        gamma=g_ce.gamma,
                        theta=g_ce.theta,
                        vega=g_ce.vega,
                        rho=g_ce.rho,
                        iv=round(calc_iv_ce * 100.0, 2),
                        theoretical_price=g_ce.theoretical_price,
                        intrinsic_value=g_ce.intrinsic_value,
                        time_value=g_ce.time_value,
                    ),
                )

            # Build Put side
            if pe_raw:
                total_pe_oi += pe_raw.oi
                total_pe_vol += pe_raw.volume
                iv_pe = calculate_iv_black76("PE", pe_raw.ltp, futures_price, strike, t, r)
                if iv_pe is None or iv_pe <= 0.005:
                    calc_iv_pe = round(base_atm_iv * (1.0 + 0.18 * (m ** 2) + 0.06 * m), 4)
                else:
                    calc_iv_pe = iv_pe

                g_pe = black76_greeks("PE", futures_price, strike, t, r, calc_iv_pe)
                pe_oi_change = getattr(pe_raw, "oi_change", 0) or 0
                pe_chg = getattr(pe_raw, "change", 0.0) or 0.0
                pe_chg_pct = getattr(pe_raw, "change_percent", 0.0) or 0.0

                pe_side = OptionSide(
                    symbol=pe_raw.contract_id,
                    instrument_token=getattr(pe_raw, "instrument", None),
                    ltp=pe_raw.ltp,
                    change=pe_chg,
                    change_percent=pe_chg_pct,
                    volume=pe_raw.volume,
                    open_interest=pe_raw.oi,
                    oi_change=pe_oi_change,
                    bid=pe_raw.bid,
                    ask=pe_raw.ask,
                    is_itm=strike > spot_price,
                    greeks=OptionGreeks(
                        delta=g_pe.delta,
                        gamma=g_pe.gamma,
                        theta=g_pe.theta,
                        vega=g_pe.vega,
                        rho=g_pe.rho,
                        iv=round(calc_iv_pe * 100.0, 2),
                        theoretical_price=g_pe.theoretical_price,
                        intrinsic_value=g_pe.intrinsic_value,
                        time_value=g_pe.time_value,
                    ),
                )

            strike_rows.append(OptionChainStrikeRow(
                strike=strike,
                is_atm=strike == atm_strike,
                call=ce_side,
                put=pe_side,
            ))

        # Put-Call Ratio
        pcr_oi = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0.0
        pcr_vol = round(total_pe_vol / total_ce_vol, 2) if total_ce_vol > 0 else 0.0

        # Calculate Max Pain
        max_pain = self._compute_max_pain(strike_rows)

        # Compute IV Skew (Difference between OTM Put IV and OTM Call IV)
        low_k = spot_price * 0.95
        high_k = spot_price * 1.05
        low_row = min(strike_rows, key=lambda r: abs(r.strike - low_k), default=None)
        high_row = min(strike_rows, key=lambda r: abs(r.strike - high_k), default=None)
        put_iv = low_row.put.greeks.iv if low_row and low_row.put and low_row.put.greeks else None
        call_iv = high_row.call.greeks.iv if high_row and high_row.call and high_row.call.greeks else None
        iv_skew = round(put_iv - call_iv, 2) if put_iv is not None and call_iv is not None else 1.25

        analytics = OptionsAnalytics(
            symbol=underlying,
            spot_price=spot_price,
            futures_price=futures_price,
            expiry=target_expiry_date.isoformat(),
            atm_strike=atm_strike,
            atm_iv=round(base_atm_iv * 100.0, 2),
            pcr_oi=pcr_oi,
            pcr_volume=pcr_vol,
            max_pain_strike=max_pain,
            total_call_oi=total_ce_oi,
            total_put_oi=total_pe_oi,
            total_call_volume=total_ce_vol,
            total_put_volume=total_pe_vol,
            iv_skew=iv_skew,
            time_to_expiry_days=round(t * 365.0, 2),
            risk_free_rate=r,
            rate_source=r_source,
        )

        return OptionChainResponse(
            underlying=underlying,
            spot_price=spot_price,
            futures_price=futures_price,
            expiry=target_expiry_date.isoformat(),
            expiries=exp_strings,
            analytics=analytics,
            strikes=strike_rows,
        )

    def _compute_max_pain(self, strike_rows: list[OptionChainStrikeRow]) -> float:
        """Calculate strike that minimizes total financial payout to option buyers."""
        if not strike_rows:
            return 0.0

        min_payout = float("inf")
        best_strike = strike_rows[0].strike

        for test_row in strike_rows:
            test_k = test_row.strike
            total_payout = 0.0

            for row in strike_rows:
                k = row.strike
                ce_oi = row.call.open_interest if row.call else 0
                pe_oi = row.put.open_interest if row.put else 0

                # Call buyer payoff if expired at test_k
                if test_k > k:
                    total_payout += ce_oi * (test_k - k)

                # Put buyer payoff if expired at test_k
                if test_k < k:
                    total_payout += pe_oi * (k - test_k)

            if total_payout < min_payout:
                min_payout = total_payout
                best_strike = test_k

        return best_strike

    async def calculate_max_pain(
        self,
        symbol: str = "NIFTY",
        expiry_str: str | None = None,
    ) -> MaxPainResult:
        """Generate complete Max Pain payout distribution."""
        chain = await self.get_option_chain_matrix(symbol, expiry_str)
        strikes = [r.strike for r in chain.strikes]
        if not strikes:
            return MaxPainResult(
                symbol=chain.underlying,
                expiry=chain.expiry,
                max_pain_strike=chain.analytics.atm_strike,
                total_loss_at_max_pain=0.0,
                strikes=[],
                payouts=[],
            )
        payouts: list[float] = []

        min_loss = float("inf")
        max_pain_k = chain.analytics.atm_strike

        for test_k in strikes:
            loss = 0.0
            for row in chain.strikes:
                k = row.strike
                ce_oi = row.call.open_interest if row.call else 0
                pe_oi = row.put.open_interest if row.put else 0

                if test_k > k:
                    loss += ce_oi * (test_k - k)
                if test_k < k:
                    loss += pe_oi * (k - test_k)

            payouts.append(round(loss, 2))
            if loss < min_loss:
                min_loss = loss
                max_pain_k = test_k

        return MaxPainResult(
            symbol=chain.underlying,
            expiry=chain.expiry,
            max_pain_strike=max_pain_k,
            total_loss_at_max_pain=min_loss,
            strikes=strikes,
            payouts=payouts,
        )

    async def get_institutional_oi_flow(
        self,
        symbol: str = "NIFTY",
        expiry_str: str | None = None,
    ) -> InstitutionalFlowResponse:
        """Analyze strike-by-strike institutional build-ups, unwinding, and net flow sentiment."""
        chain = await self.get_option_chain_matrix(symbol, expiry_str)
        spot = chain.spot_price
        atm = chain.analytics.atm_strike
        pcr_oi = chain.analytics.pcr_oi
        pcr_vol = chain.analytics.pcr_volume

        strike_flows: list[InstitutionalStrikeFlow] = []
        highest_call_oi = 0
        call_wall_k = atm
        highest_put_oi = 0
        put_floor_k = atm

        bullish_weights = 0.0
        bearish_weights = 0.0

        for row in chain.strikes:
            k = row.strike
            ce = row.call
            pe = row.put

            ce_oi = ce.open_interest if ce else 0
            pe_oi = pe.open_interest if pe else 0
            ce_vol = ce.volume if ce else 0
            pe_vol = pe.volume if pe else 0
            ce_ltp = ce.ltp if ce else 0.0
            pe_ltp = pe.ltp if pe else 0.0
            ce_chg = ce.change if ce else 0.0
            pe_chg = pe.change if pe else 0.0

            ce_oi_chg = ce.oi_change if ce and ce.oi_change is not None else 0
            pe_oi_chg = pe.oi_change if pe and pe.oi_change is not None else 0

            if ce_oi > highest_call_oi:
                highest_call_oi = ce_oi
                call_wall_k = k
            if pe_oi > highest_put_oi:
                highest_put_oi = pe_oi
                put_floor_k = k

            # Call Buildup Classification
            if ce_chg > 0 and ce_oi_chg > 0:
                ce_build = "LONG_BUILDUP"
                bullish_weights += 1.0
            elif ce_chg < 0 and ce_oi_chg > 0:
                ce_build = "SHORT_BUILDUP"
                bearish_weights += 1.5  # Call writing is strong resistance
            elif ce_chg > 0 and ce_oi_chg < 0:
                ce_build = "SHORT_COVERING"
                bullish_weights += 1.5  # Call short covering is explosive
            elif ce_chg < 0 and ce_oi_chg < 0:
                ce_build = "LONG_UNWINDING"
                bearish_weights += 1.0
            else:
                ce_build = "NEUTRAL"

            # Put Buildup Classification
            if pe_chg > 0 and pe_oi_chg > 0:
                pe_build = "LONG_BUILDUP"
                bearish_weights += 1.0
            elif pe_chg < 0 and pe_oi_chg > 0:
                pe_build = "SHORT_BUILDUP"
                bullish_weights += 1.5  # Put writing is strong support
            elif pe_chg > 0 and pe_oi_chg < 0:
                pe_build = "SHORT_COVERING"
                bearish_weights += 1.5
            elif pe_chg < 0 and pe_oi_chg < 0:
                pe_build = "LONG_UNWINDING"
                bullish_weights += 1.0
            else:
                pe_build = "NEUTRAL"

            # Net strike flow
            net_f = "BULLISH" if (ce_build in ("LONG_BUILDUP", "SHORT_COVERING") or pe_build == "SHORT_BUILDUP") else "BEARISH" if (ce_build in ("SHORT_BUILDUP", "LONG_UNWINDING") or pe_build == "LONG_BUILDUP") else "NEUTRAL"

            strike_flows.append(
                InstitutionalStrikeFlow(
                    strike=k,
                    is_atm=row.is_atm,
                    call_oi=ce_oi,
                    put_oi=pe_oi,
                    call_oi_change=ce_oi_chg,
                    put_oi_change=pe_oi_chg,
                    call_volume=ce_vol,
                    put_volume=pe_vol,
                    call_ltp=ce_ltp,
                    put_ltp=pe_ltp,
                    call_buildup=ce_build,
                    put_buildup=pe_build,
                    net_flow=net_f,
                )
            )

        # Composite Institutional Score (0-100)
        total_weights = (bullish_weights + bearish_weights) or 1.0
        raw_score = (bullish_weights / total_weights) * 100.0
        # Adjust with PCR
        pcr_adj = min(15.0, max(-15.0, (pcr_oi - 1.0) * 20.0))
        final_score = round(min(100.0, max(0.0, raw_score + pcr_adj)), 1)

        if final_score >= 70.0:
            sentiment = "STRONG_BULLISH"
        elif final_score >= 55.0:
            sentiment = "BULLISH"
        elif final_score <= 30.0:
            sentiment = "STRONG_BEARISH"
        elif final_score <= 45.0:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        return InstitutionalFlowResponse(
            symbol=chain.underlying,
            expiry=chain.expiry,
            spot_price=spot,
            atm_strike=atm,
            pcr_oi=pcr_oi,
            pcr_volume=pcr_vol,
            max_pain_strike=chain.analytics.max_pain_strike,
            call_wall_strike=call_wall_k,
            put_floor_strike=put_floor_k,
            institutional_sentiment=sentiment,
            institutional_score=final_score,
            total_call_oi=chain.analytics.total_call_oi,
            total_put_oi=chain.analytics.total_put_oi,
            total_call_volume=chain.analytics.total_call_volume,
            total_put_volume=chain.analytics.total_put_volume,
            strike_flows=strike_flows,
        )


options_service = OptionsService()

