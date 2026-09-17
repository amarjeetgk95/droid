"""TEMP diagnostic - spy on the guard inputs that cause the slippage rejection."""
import json


def _show(tag, res):
    try:
        body = json.dumps(res.json())[:700]
    except Exception:
        body = res.text[:700]
    print(f"\n@@@ {tag} status={res.status_code}\n{body}")


PAPER = {
    "instrument_id": "NIFTY",
    "candle_timeframe": "5M",
    "direction": "BULLISH",
    "status": "CONFIRMED",
    "trigger_level": 24940.0,
    "current_price": 24915.0,
    "confidence": 88.0,
    "execute_paper": True,
    "notify_telegram": False,
    "allow_closed_market": True,
}


def test_spy_guard(client, mock_market_feed, monkeypatch):
    from app.signals.safety import execution_guard as eg

    orig_guard = eg.final_execution_guard

    def spy_guard(**kw):
        spec = kw.get("contract_spec") or {}
        print(
            "\n@@@ GUARD_INPUTS"
            f" order_price={kw.get('order_price')!r}"
            f" latest_price={kw.get('latest_price')!r}"
            f" qty={kw.get('order_quantity')!r}"
            f" symbol={spec.get('broker_symbol')!r}"
            f" strike={spec.get('strike')!r}"
            f" otype={spec.get('option_type')!r}"
            f" live_premium={spec.get('live_premium')!r}"
        )
        res = orig_guard(**kw)
        print(f"@@@ GUARD_RESULT passed={res.passed} check={res.failed_check} reason={res.reason}")
        return res

    monkeypatch.setattr(eg, "final_execution_guard", spy_guard)
    _show("PAPER", client.post("/api/v1/signals/generate", json=PAPER))


def test_spy_contract(client, mock_market_feed, monkeypatch):
    """What contract does the resolver pick, and what premium does it carry?"""
    import app.signals.contract_resolver as cr

    orig = cr.resolve_option_contract

    def spy(*a, **kw):
        out = orig(*a, **kw)
        try:
            d = out.model_dump() if hasattr(out, "model_dump") else dict(out)
            print(f"\n@@@ CONTRACT_PICKED {json.dumps(d, default=str)[:700]}")
        except Exception as e:  # noqa: BLE001
            print(f"\n@@@ CONTRACT_PICKED raw={out!r} err={e}")
        return out

    monkeypatch.setattr(cr, "resolve_option_contract", spy)
    _show("PAPER2", client.post("/api/v1/signals/generate", json=PAPER))


def test_spy_pinned_feed(mock_market_feed):
    """Confirm the pinned feed is what the service actually sees."""
    import asyncio
    from app.services.market_service import MarketService

    q = asyncio.run(MarketService().get_quote("NIFTY"))
    print(f"\n@@@ PINNED ltp={q.ltp} status={q.status} provider={q.provider} symbol={q.symbol}")
    print(f"@@@ TABLE {mock_market_feed}")