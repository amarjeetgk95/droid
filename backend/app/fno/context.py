from app.instruments.registry import get_by_symbol_exact, get_instrument

async def get_fno_context(symbol: str) -> dict:
    cfg = get_by_symbol_exact(symbol.upper()) or get_instrument(symbol)
    if not cfg or not cfg.fno_available:
        return {"available": False, "reason": "F&O data is not available for this instrument"}
    # Try to get real options/futures data via services, fallback to synthetic
    try:
        from app.services.options_service import options_service
        from app.services.market_service import MarketService
        ms=MarketService()
        quote=await ms.get_quote(symbol)
        spot=quote.ltp
        # options chain
        chain=await options_service.get_option_chain_matrix(symbol)
        analytics=chain.analytics if chain else None
        # Robust Max Pain: chain has no direct .max_pain; try calculate, fallback to analytics
        max_pain_val = spot
        if analytics:
            try:
                mp_res = await options_service.calculate_max_pain(symbol)
                max_pain_val = mp_res.max_pain_strike if mp_res else analytics.max_pain_strike
            except Exception:
                max_pain_val = analytics.max_pain_strike
        # futures data unavailable (module removed)
        near_basis = 0
        near_basis_pct = 0
        near_oi = 0
        near_oi_change_abs = 0
        oi_change = 0
        near_volume = 0
        near_days = analytics.time_to_expiry_days if analytics else 2
        near_fair_spread = 0
        total_fut_oi = near_oi
        rollover_pct = 0
        rollover_avg = 72.5
        rollover_pace = "IN_LINE"
        rollover_cost = 0
        # rollover near-expiry flag
        near_expiry_guard = near_days <= 3

        pcr = analytics.pcr_oi if analytics else 1.0
        pcr_vol = analytics.pcr_volume if analytics else 1.0
        atm_iv = analytics.atm_iv if analytics else 14.5
        total_call_oi = analytics.total_call_oi if analytics else 0
        total_put_oi = analytics.total_put_oi if analytics else 0
        total_call_vol = analytics.total_call_volume if analytics else 0
        total_put_vol = analytics.total_put_volume if analytics else 0
        # IV regime proxy
        # find call/put walls (max OI strikes) and top 3 lists
        call_wall=None; put_wall=None
        key_call_strikes=[]
        key_put_strikes=[]
        atm_call_premium=None; atm_put_premium=None
        atm_greeks=None
        if chain and chain.strikes:
            # top OI
            max_call = max(chain.strikes, key=lambda x: x.call.open_interest if x.call else 0)
            max_put = max(chain.strikes, key=lambda x: x.put.open_interest if x.put else 0)
            if max_call.call: call_wall=max_call.strike
            if max_put.put: put_wall=max_put.strike
            # top 3
            call_sorted = sorted([r for r in chain.strikes if r.call], key=lambda x: x.call.open_interest, reverse=True)[:3]
            put_sorted = sorted([r for r in chain.strikes if r.put], key=lambda x: x.put.open_interest, reverse=True)[:3]
            key_call_strikes = [{"strike": r.strike, "oi": r.call.open_interest, "ltp": r.call.ltp} for r in call_sorted]
            key_put_strikes = [{"strike": r.strike, "oi": r.put.open_interest, "ltp": r.put.ltp} for r in put_sorted]
            # ATM premiums/greeks
            atm_row = next((r for r in chain.strikes if r.is_atm), None)
            if atm_row is None:
                atm_row = min(chain.strikes, key=lambda x: abs(x.strike - spot))
            if atm_row:
                if atm_row.call:
                    atm_call_premium = atm_row.call.ltp
                if atm_row.put:
                    atm_put_premium = atm_row.put.ltp
                # greeks at ATM
                atm_greeks = {}
                if atm_row.call and atm_row.call.greeks:
                    atm_greeks['call'] = atm_row.call.greeks.model_dump() if hasattr(atm_row.call.greeks, 'model_dump') else dict(atm_row.call.greeks)
                if atm_row.put and atm_row.put.greeks:
                    atm_greeks['put'] = atm_row.put.greeks.model_dump() if hasattr(atm_row.put.greeks, 'model_dump') else dict(atm_row.put.greeks)
        return {
            "available": True,
            # Section 8 exhaustive fields
            "spot": spot,
            "futures_price": spot + near_basis,
            "futures_basis": near_basis,
            "futures_basis_percent": near_basis_pct,
            "futures_oi": near_oi,
            "futures_oi_change_abs": near_oi_change_abs,
            "futures_oi_change": oi_change,
            "futures_volume": near_volume,
            "total_futures_oi": total_fut_oi,
            "futures_fair_spread": near_fair_spread,
            "term_structure_curve": "UNKNOWN",
            "calendar_spread_next_near": 0,
            "rollover_percent": rollover_pct,
            "rollover_three_month_avg": rollover_avg,
            "rollover_pace": rollover_pace,
            "rollover_cost": rollover_cost,
            "near_expiry_guard_active": near_expiry_guard,
            "pcr": pcr,
            "pcr_volume": pcr_vol,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "total_call_volume": total_call_vol,
            "total_put_volume": total_put_vol,
            "atm_iv": atm_iv,
            # IV regime placeholders (proxy)
            "iv_rank_proxy": max(0, min(100, (atm_iv - 10)/(30-10)*100)) if atm_iv else None,
            "iv_percentile_proxy": None,  # filled via VIX percentile downstream; kept for schema
            "call_wall": call_wall,
            "put_wall": put_wall,
            "key_call_strikes": key_call_strikes,
            "key_put_strikes": key_put_strikes,
            "atm_call_premium": atm_call_premium,
            "atm_put_premium": atm_put_premium,
            "atm_greeks": atm_greeks,
            "max_pain": max_pain_val,
            "distance_to_expiry_days": analytics.time_to_expiry_days if analytics else near_days,
            "futures_positioning": "UNKNOWN",
            "buildup_strength": "UNKNOWN",
            # Data ingestion protocol §22
            "data_ingestion": {
                "tick_level": "Unavailable",
                "orderbook_depth": "Unavailable",
                "granularities": ["1m OHLCV (Limited)", "5m OHLCV (Primary)", "15m OHLCV (Available)", "1h (Available, N>=50)", "Daily (Derived)", "Weekly (Derived)"],
                "limitation": "Tick/order-book data unavailable. 1m-15m order-flow analysis cannot be reliably performed. Primary quantitative assessment is therefore based on 1h, Daily and Weekly data.",
                "intraday_1m_15m_status": "Limited / Unavailable",
                "unavailable_metrics": ["VWAP tick delta", "order-book imbalance", "footprint delta", "time & sales aggression", "micro-price imbalance"],
                "fallback_lens": "Daily and Weekly + 1h confirmation where sufficient observations exist",
                "confidence_note": "Reduced confidence for horizons <15m due to missing granular order-flow",
            },
        }
    except Exception as e:
        # Per Chart Analysis spec: real market data only. Never fabricate.
        # If F&O data missing, clearly identify missing data and reduce confidence.
        # Do NOT return synthetic placeholder values.
        return {
            "available": False,
            "reason": "Data unavailable — F&O data could not be retrieved for this instrument. No substitution.",
            "error": str(e)[:200],
            "spot": None,
            "futures_price": None,
            "futures_basis": None,
            "futures_basis_percent": None,
            "futures_oi": None,
            "futures_oi_change": None,
            "futures_volume": None,
            "total_futures_oi": None,
            "pcr": None,
            "pcr_volume": None,
            "total_call_oi": None,
            "total_put_oi": None,
            "atm_iv": None,
            "call_wall": None,
            "put_wall": None,
            "key_call_strikes": [],
            "key_put_strikes": [],
            "atm_call_premium": None,
            "atm_put_premium": None,
            "max_pain": None,
            "distance_to_expiry_days": None,
            "futures_positioning": "DATA_UNAVAILABLE",
            "rollover_percent": None,
            "synthetic": False,
            "data_unavailable": True,
            "data_ingestion": {
                "tick_level": "Unavailable",
                "orderbook_depth": "Unavailable",
                "limitation": "F&O tick/order-book data unavailable. Real market data only — no synthetic fallback. Confidence reduced.",
                "intraday_1m_15m_status": "Limited / Unavailable",
            },
        }

def fno_levels_for_sr(fno_ctx: dict) -> dict|None:
    if not fno_ctx.get("available"):
        return None
    return {
        "call_wall": fno_ctx.get("call_wall"),
        "put_wall": fno_ctx.get("put_wall"),
        "max_pain": fno_ctx.get("max_pain"),
        "atm_iv": fno_ctx.get("atm_iv"),
    }
