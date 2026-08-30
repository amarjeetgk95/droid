from datetime import datetime, timezone
from app.instruments.registry import get_by_symbol_exact, get_instrument

async def get_fno_context(symbol: str) -> dict:
    cfg = get_by_symbol_exact(symbol.upper()) or get_instrument(symbol)
    if not cfg or not cfg.fno_available:
        return {"available": False, "reason": "F&O data is not available for this instrument"}
    # Try to get real options/futures data via services, fallback to synthetic
    try:
        from app.services.options_service import options_service
        from app.services.futures_service import futures_service
        from app.services.market_service import MarketService
        ms=MarketService()
        quote=await ms.get_quote(symbol)
        spot=quote.ltp
        # options chain
        chain=await options_service.get_option_chain_matrix(symbol)
        analytics=chain.analytics if chain else None
        max_pain_val=chain.max_pain.max_pain_strike if chain and chain.max_pain else spot
        # futures
        fut = await futures_service.get_futures_overview(symbol)
        ts=fut.term_structure if fut else None
        near_basis = ts.contracts[0].basis if ts and ts.contracts else 0
        near_oi = ts.contracts[0].open_interest if ts and ts.contracts else 0
        oi_change = ts.contracts[0].oi_change_percent if ts and ts.contracts else 0
        pcr = analytics.pcr_oi if analytics else 1.0
        pcr_vol = analytics.pcr_volume if analytics else 1.0
        atm_iv = analytics.atm_iv if analytics else 14.5
        # find call/put walls (max OI strikes)
        call_wall=None; put_wall=None
        if chain and chain.strikes:
            max_call = max(chain.strikes, key=lambda x: x.call.open_interest if x.call else 0)
            max_put = max(chain.strikes, key=lambda x: x.put.open_interest if x.put else 0)
            if max_call.call: call_wall=max_call.strike
            if max_put.put: put_wall=max_put.strike
        return {
            "available": True,
            "spot": spot,
            "futures_price": spot + near_basis,
            "basis": near_basis,
            "futures_oi": near_oi,
            "futures_oi_change": oi_change,
            "pcr": pcr,
            "pcr_volume": pcr_vol,
            "atm_iv": atm_iv,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "max_pain": max_pain_val,
            "distance_to_expiry_days": analytics.time_to_expiry_days if analytics else 2,
            "futures_positioning": fut.buildup.buildup_type if fut and fut.buildup else "UNKNOWN",
        }
    except Exception as e:
        # synthetic fallback
        return {
            "available": True,
            "spot": 25000,
            "futures_price": 25025,
            "basis": 25,
            "futures_oi": 1000000,
            "futures_oi_change": 2.5,
            "pcr": 1.08,
            "pcr_volume": 1.02,
            "atm_iv": 14.8,
            "call_wall": 25200,
            "put_wall": 24800,
            "max_pain": 25000,
            "distance_to_expiry_days": 3,
            "futures_positioning": "LONG_BUILDUP",
            "synthetic": True,
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
