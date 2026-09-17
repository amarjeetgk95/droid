"""Selector viability: all-rejected -> is_viable False -> gates refuse."""
from decimal import Decimal


def _cand(**over):
    from app.signals.strategies.base import SignalCandidate
    base = dict(
        underlying="NIFTY", strategy="BREAKOUT", direction="LONG_CALL",
        timeframe="5M", spot_price=Decimal("24870"),
        entry_min=Decimal("24880"), entry_max=Decimal("24890"),
        trigger=Decimal("24885"), stop_loss=Decimal("24800"),
        target_1=Decimal("25000"), target_2=Decimal("25100"),
        risk_points=Decimal("85"), risk_reward_t1=1.5, risk_reward_t2=3.0,
    )
    base.update(over)
    return SignalCandidate(**base)


def test_no_chain_quotes_returns_none():
    from app.signals.options_intelligence.selector import quantitative_contract_selector
    res = quantitative_contract_selector.select_optimal_contract(
        underlying="NIFTY", spot_price=24870.0, direction="LONG_CALL",
        option_chain_quotes=None)
    assert res is None  # fail-closed: no broker quotes, no selection


def test_all_rejected_is_not_viable():
    from app.signals.options_intelligence.selector import quantitative_contract_selector
    quotes = {24750.0: 200.0, 24800.0: 150.0, 24850.0: 120.0,
              24900.0: 90.0, 24950.0: 60.0}
    res = quantitative_contract_selector.select_optimal_contract(
        underlying="NIFTY", spot_price=24870.0, direction="LONG_CALL",
        option_chain_quotes=quotes, min_net_rr=999.0)
    # Fail-closed: None (no acceptable chain-backed candidate) or explicit
    # is_viable False — either way the pipeline must refuse registration.
    assert res is None or res.is_viable is False
    if res is not None:
        assert res.non_viability_reasons


def test_chain_mark_gate_refuses_formula_contract():
    from app.signals.contract_resolver import resolve_option_contract
    from app.signals.pipeline.gates import ChainMarkGate, OptionViabilityGate
    c = resolve_option_contract("NIFTY", Decimal("24870"), "CE", strike_offset=0)
    cand = _cand(option_contract=c)
    r = ChainMarkGate().evaluate(cand)
    if c.contract_source != "fyers_chain":
        assert r.passed is False
        assert r.reason_code == "CHAIN_MARK_UNAVAILABLE"
    bad = _cand(path_simulation={"is_economically_viable": False,
                                 "viability_rationale": ["no edge"]})
    r2 = OptionViabilityGate().evaluate(bad)
    assert r2.passed is False
