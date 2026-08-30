from datetime import date
from app.services.contract_master import ContractMasterService
from app.models.contracts import ContractType, OptionType, ExpiryType


class TestContractMasterService:
    def setup_method(self):
        self.cms = ContractMasterService()

    def test_catalog_populated(self):
        contracts = self.cms.search_contracts(underlying="NIFTY")
        assert len(contracts) > 0
        # Should have spot, futures, and options
        types = {c.contract_type for c in contracts}
        assert ContractType.INDEX_SPOT in types
        assert ContractType.INDEX_FUTURE in types
        assert ContractType.INDEX_OPTION in types

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
        ce_options = self.cms.search_contracts(
            underlying="NIFTY",
            contract_type=ContractType.INDEX_OPTION,
            option_type=OptionType.CE
        )
        assert len(ce_options) > 0
        for ce in ce_options:
            assert ce.strike is not None
            assert ce.option_type == OptionType.CE

    def test_banknifty_lot_size(self):
        spot = self.cms.get_by_token("BANKNIFTY_INDEX")
        assert spot is not None
        assert spot.lot_size == 15
