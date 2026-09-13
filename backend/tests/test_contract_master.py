from datetime import date
from app.services.contract_master import ContractMasterService
from app.models.contracts import ContractType, OptionType, ExpiryType


class TestContractMasterService:
    def setup_method(self):
        self.cms = ContractMasterService()

    def test_catalog_populated(self):
        contracts = self.cms.search_contracts(underlying="NIFTY")
        assert len(contracts) > 0
        # Bootstrap seeds spot + futures expiry shells only (no fake option strikes).
        # Live option strikes come from FYERS sync_strikes_from_fyers.
        types = {c.contract_type for c in contracts}
        assert ContractType.INDEX_SPOT in types
        assert ContractType.INDEX_FUTURE in types

    def test_dynamic_expiry_resolution(self):
        res = self.cms.resolve_expiries("NIFTY")
        assert res.underlying == "NIFTY"
        assert res.current_expiry is not None
        assert res.next_expiry is not None
        assert res.current_expiry < res.next_expiry
        assert len(res.all_expiries) >= 2

    def test_contract_lookup_by_token(self):
        spot = self.cms.get_by_token("NIFTY_INDEX")
        assert spot is not None
        assert spot.symbol == "NIFTY 50"
        assert spot.lot_size == 25

    def test_option_strikes_and_types(self):
        # Bootstrap has no fake strikes; sync live FYERS strikes then verify.
        from datetime import timedelta
        today = date.today()
        exp = self.cms.get_expiries("NIFTY")[0]
        n = self.cms.sync_strikes_from_fyers("NIFTY", exp, [24800.0, 24850.0], 50.0, 25)
        assert n == 4  # 2 strikes x CE/PE
        ce_options = self.cms.search_contracts(
            underlying="NIFTY",
            contract_type=ContractType.INDEX_OPTION,
            option_type=OptionType.CE
        )
        assert len(ce_options) > 0
        for ce in ce_options:
            assert ce.strike is not None
            assert ce.option_type == OptionType.CE
            assert ce.provider == "fyers"

    def test_banknifty_lot_size(self):
        spot = self.cms.get_by_token("BANKNIFTY_INDEX")
        assert spot is not None
        assert spot.lot_size == 15
