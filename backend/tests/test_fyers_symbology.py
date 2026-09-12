"""FYERS v3 option symbology: weekly uses single-letter month, monthly uses MMM."""
from datetime import date
from decimal import Decimal

from app.signals.contract_resolver import (
    parse_fyers_option_symbol,
    resolve_nearest_expiry,
    resolve_option_contract,
)


def test_weekly_symbol_uses_single_letter_month():
    # Wed 09 Sep 2026 -> SENSEX weekly expiry Fri 11 Sep 2026 (holiday-adjusted at most).
    c = resolve_option_contract("SENSEX", Decimal("75139.6"), "PE", ref_date=date(2026, 9, 9))
    exp = c.expiry_date
    assert exp is not None
    if c.expiry_type == "MONTHLY":
        assert c.broker_symbol == f"BSE:SENSEX{str(exp.year)[-2:]}{exp.strftime('%b').upper()}{int(c.strike)}PE"
    else:
        code = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
                10: "O", 11: "N", 12: "D"}[exp.month]
        assert c.broker_symbol == (
            f"BSE:SENSEX{str(exp.year)[-2:]}{code}{exp.day:02d}{int(c.strike)}PE"
        )
    # The Sept-11-2026 weekly shape that sparked this: day+strike run together.
    assert "SEP11" not in c.broker_symbol or c.expiry_type == "MONTHLY"


def test_known_weekly_symbol_shape():
    # Canonical example from FYERS docs pattern: NIFTY weekly, single-letter month.
    c = resolve_option_contract("NIFTY", Decimal("24835.0"), "CE", ref_date=date(2026, 9, 9))
    assert c.broker_symbol.startswith("NSE:NIFTY")
    assert c.broker_symbol.endswith(f"{int(c.strike)}CE")
    parsed = parse_fyers_option_symbol(c.broker_symbol)
    assert parsed is not None
    assert parsed["underlying"] == "NIFTY"
    assert parsed["strike"] == int(c.strike)
    assert parsed["option_type"] == "CE"


def test_parse_monthly_and_weekly_forms():
    m = parse_fyers_option_symbol("BSE:SENSEX26SEP75200PE")
    assert m is not None and m["expiry_kind"] == "MONTHLY"
    assert (m["year"], m["month"], m["day"], m["strike"]) == (2026, 9, None, 75200)

    w = parse_fyers_option_symbol("BSE:SENSEX2691175200PE")
    assert w is not None and w["expiry_kind"] == "WEEKLY"
    assert (w["year"], w["month"], w["day"], w["strike"], w["option_type"]) == (2026, 9, 11, 75200, "PE")

    # The old builder output: parses as MONTHLY with an absurd 11,75,200
    # strike — well-formed-looking but untradable. This is the bug we fixed.
    old = parse_fyers_option_symbol("BSE:SENSEX26SEP1175200PE")
    assert old is not None and old["strike"] == 1175200
    assert parse_fyers_option_symbol("NSE:NIFTY50-INDEX") is None
    assert parse_fyers_option_symbol("garbage") is None


def test_october_november_december_codes():
    assert parse_fyers_option_symbol("NSE:NIFTY26O0824800CE")["month"] == 10
    assert parse_fyers_option_symbol("NSE:NIFTY26N0824800CE")["month"] == 11
    assert parse_fyers_option_symbol("NSE:NIFTY26D0824800CE")["month"] == 12


def test_post_2025_expiry_weekdays():
    # SEBI Sep-2025 map: NIFTY Tue, SENSEX Thu, BANKNIFTY monthly-only (last Thu).
    wed = date(2026, 9, 9)  # Wednesday
    s_exp, s_kind = resolve_nearest_expiry("SENSEX", wed)
    assert (s_exp, s_kind) == (date(2026, 9, 10), "WEEKLY"), (s_exp, s_kind)
    n_exp, n_kind = resolve_nearest_expiry("NIFTY", wed)
    assert (n_exp, n_kind) == (date(2026, 9, 15), "WEEKLY"), (n_exp, n_kind)
    b_exp, b_kind = resolve_nearest_expiry("BANKNIFTY", wed)
    assert (b_exp, b_kind) == (date(2026, 9, 24), "MONTHLY"), (b_exp, b_kind)


def test_sensex_thursday_contract_symbol():
    c = resolve_option_contract("SENSEX", Decimal("75139.6"), "PE", ref_date=date(2026, 9, 9))
    assert c.expiry_date == date(2026, 9, 10)
    assert c.broker_symbol == f"BSE:SENSEX26910{int(c.strike)}PE"
    assert parse_fyers_option_symbol(c.broker_symbol)["day"] == 10
