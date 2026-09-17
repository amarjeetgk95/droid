"""Chain-mark gate: formula contract on generate, REJECTED execute without mark."""
from tests.conftest import PINNED_FEED


def test_generate_without_chain_is_formula(client, mock_market_feed, mock_market_open, monkeypatch):
    from app.signals import live_contract_cache as lcc
    monkeypatch.setattr(lcc.live_contract_cache, "lookup", lambda *a, **k: None)
    ltp = PINNED_FEED["NIFTY 50"]
    res = client.post("/api/v1/signals/generate", json={
        "underlying": "NIFTY", "strategy": "BREAKOUT", "direction": "LONG_CALL",
        "timeframe": "5M", "current_price": ltp,
        "notify_telegram": False, "allow_closed_market": True,
    })
    assert res.status_code == 200, res.text
    opt = res.json()["signal"]["option_contract"]
    assert opt.get("live_premium") in (None, 0)
    assert str(opt.get("contract_source")) != "fyers_chain"


def test_execute_without_mark_rejected(client, mock_market_feed, mock_market_open, monkeypatch):
    from app.services.paper_service import paper_service
    from app.signals import live_contract_cache as lcc
    paper_service.reset_portfolio()
    monkeypatch.setattr(lcc.live_contract_cache, "lookup", lambda *a, **k: None)
    ltp = PINNED_FEED["NIFTY 50"]
    gen = client.post("/api/v1/signals/generate", json={
        "underlying": "NIFTY", "strategy": "BREAKOUT", "direction": "LONG_CALL",
        "timeframe": "5M", "current_price": ltp,
        "notify_telegram": False, "allow_closed_market": True,
    })
    assert gen.status_code == 200, gen.text
    sid = gen.json()["signal"]["signal_id"]
    res = client.post(f"/api/v1/signals/{sid}/execute-paper", json={"lots": 1})
    # Fail-closed without a broker mark: 400 REJECTED (or 500 wrapper).
    assert res.status_code in (400, 500), res.text
    body = res.text.lower()
    assert "chain_mark" in body or "rejected" in body or "no live" in body
