"""TEMP smoke test: does FYERS /data/quotes return data for OPTION contract symbols?

The whole Tier-1 mark-freshness design rests on this one assumption. Read the
chain plumbing all you like — only a live call settles it.
"""
import asyncio
import time

SYMS = [
    "NSE:NIFTY50-INDEX",
    "NSE:NIFTYBANK-INDEX",
    "NSE:NIFTY2691523350PE",
    "NSE:BANKNIFTY26SEP56000CE",
    "BSE:SENSEX2691774400CE",
]


def mask(v):
    if isinstance(v, str) and len(v) > 12:
        return v[:6] + "..." + v[-4:]
    return v


async def main():
    from app.providers import get_provider

    p = get_provider()
    print("provider class:", type(p).__name__)
    for a in ("provider_name", "name", "mode"):
        print("  ", a, "=", getattr(p, a, None))
    for a in ("is_authenticated", "authenticated", "access_token", "token"):
        v = getattr(p, a, None)
        if callable(v):
            try:
                v = v()
            except Exception as e:  # noqa: BLE001
                v = f"<err {e}>"
        print("  ", a, "=", mask(v))
    for a in ("_access_token", "_token", "_fyers_token"):
        if hasattr(p, a):
            print("  ", a, "=", mask(getattr(p, a)))

    fn = getattr(p, "_fetch_fyers_quotes", None)
    print("has _fetch_fyers_quotes:", callable(fn))
    if not callable(fn):
        print("ABORT: provider has no _fetch_fyers_quotes")
        return

    # one symbol at a time first, so a failure isolates cleanly
    for s in SYMS:
        t0 = time.time()
        try:
            out = await fn([s])
        except Exception as e:  # noqa: BLE001
            print(f"  {s:32s} EXC {type(e).__name__}: {str(e)[:120]}")
            continue
        dt = (time.time() - t0) * 1000
        q = (out or {}).get(s)
        if q is None:
            keys = list((out or {}).keys())[:5]
            print(f"  {s:32s} MISSING ({dt:.0f}ms) returned_keys={keys}")
            continue
        ltp = getattr(q, "ltp", None)
        extra = {a: getattr(q, a) for a in ("bid", "ask", "oi", "volume", "provider", "symbol") if hasattr(q, a)}
        print(f"  {s:32s} OK ltp={ltp} ({dt:.0f}ms) {extra}")

    print("\n-- batch call (all 5) --")
    t0 = time.time()
    out = await fn(SYMS)
    print(f"returned={len(out or {})} in {(time.time() - t0) * 1000:.0f}ms keys={list((out or {}).keys())}")

    print("\n-- OptionMarkService end-to-end --")
    from app.signals.option_marks import option_mark_service, option_mark_registry
    marks = await option_mark_service.refresh_and_register(SYMS[2:])
    for sym, m in marks.items():
        print(f"  mark {sym}: source={m.source} price={m.price} mid={m.mid} ltp={m.ltp} age={m.age_ms()}ms usable={m.is_usable}")
    print("registry stats:", option_mark_registry.stats())


asyncio.run(main())
