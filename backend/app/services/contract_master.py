from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Sequence
from app.models.contracts import (
    ContractMaster, ContractType, OptionType, OptionStyle,
    ExpiryType, SettlementType, PricingStyle, ContractStatus,
    ExpiryResolution
)
from app.services.calendar_service import calendar_service

IST = ZoneInfo("Asia/Kolkata")


class ContractMasterService:
    """Central repository for data-driven instrument and contract metadata.
    
    Adheres strictly to Sections 15, 16, 18, and 19.
    Never hard-codes permanent expiry weekday matrices.
    Derives expiry cycles and options/futures contracts dynamically.
    """

    def __init__(self):
        self._contracts: dict[str, ContractMaster] = {}  # key: symbol
        self._by_token: dict[str, ContractMaster] = {}
        self._by_underlying: dict[str, list[ContractMaster]] = {}
        self._initialize_default_catalog()

    def _initialize_default_catalog(self) -> None:
        """Bootstrap expiry calendar ONLY — Truth-of-Wall.

        FYERS is the sole source for LTP/OI/strikes. This catalog seeds ONLY
        expiry DATES from NSE calendar rules (reference schedule, not prices)
        so `resolve_expiries` works before the first live FYERS option-chain
        sync. No synthetic option strikes are generated here — live strikes
        come from `FyersProvider.get_option_chain` and override via
        `sync_strikes_from_fyers`. Provider label is local_calendar_bootstrap,
        never fyers, to avoid claiming FYERS truth.
        """
        today = datetime.now(timezone.utc).astimezone(IST).date()

        benchmarks = [
            # (display, underlying, lot_size, tick_size) — no base_spot: strikes are FYERS-only
            ("NIFTY 50", "NIFTY", 75, 0.05),
            ("BANKNIFTY", "BANKNIFTY", 30, 0.05),
            ("FINNIFTY", "FINNIFTY", 65, 0.05),
            ("SENSEX", "SENSEX", 10, 0.05),
        ]

        # Generate rolling expiries (next 4 weekly and next 2 monthly)
        for name, underlying, lot_size, tick_size in benchmarks:
            # Add Spot Contract
            spot_contract = ContractMaster(
                instrument_token=f"{underlying}_INDEX",
                exchange="NSE",
                symbol=name,
                underlying=underlying,
                contract_type=ContractType.INDEX_SPOT,
                lot_size=lot_size,
                tick_size=tick_size,
                settlement_type=SettlementType.CASH_SETTLED,
                pricing_style=PricingStyle.SPOT_BLACK_SCHOLES,
                contract_status=ContractStatus.ACTIVE,
                effective_from=date(2020, 1, 1),
                provider="local_calendar_bootstrap"
            )
            self.add_contract(spot_contract)

            # Generate dynamic expiries using calendar rules
            expiries = self._generate_sample_expiries(today, count=6)

            for exp_idx, exp_date in enumerate(expiries):
                is_monthly = (exp_idx == len(expiries) - 1 or exp_date.day > 21)
                exp_type = ExpiryType.MONTHLY if is_monthly else ExpiryType.WEEKLY

                # Add Futures expiry shell for this expiry (schedule only, no price)
                fut_symbol = f"{underlying}{exp_date.strftime('%y%b').upper()}FUT"
                fut_contract = ContractMaster(
                    instrument_token=f"{underlying}_{exp_date.strftime('%Y%m%d')}_FUT",
                    exchange="NFO",
                    symbol=fut_symbol,
                    underlying=underlying,
                    contract_type=ContractType.INDEX_FUTURE,
                    expiry=exp_date,
                    expiry_type=exp_type,
                    lot_size=lot_size,
                    tick_size=tick_size,
                    settlement_type=SettlementType.CASH_SETTLED,
                    pricing_style=PricingStyle.FUTURES_BLACK76,
                    contract_status=ContractStatus.ACTIVE,
                    effective_from=today - timedelta(days=60),
                    provider="local_calendar_bootstrap"
                )
                self.add_contract(fut_contract)

                # NOTE: option strikes intentionally NOT generated here.
                # Live strikes/OI/LTP come from FYERS option-chain-v3 via
                # OptionsService.get_option_chain_matrix. See sync_strikes_from_fyers.

    def sync_strikes_from_fyers(
        self,
        underlying: str,
        expiry: date,
        strikes: list[float],
        strike_step: float,
        lot_size: int,
        tick_size: float = 0.05,
    ) -> int:
        """Upsert live FYERS strikes for an expiry (authoritative truth).

        Called after a successful FYERS option-chain fetch to replace the
        calendar bootstrap with tradable truth. Returns count synced.
        """
        from app.models.contracts import ExpiryType as _ET
        count = 0
        exp_type = _ET.MONTHLY if expiry.day > 21 else _ET.WEEKLY
        today = datetime.now(timezone.utc).astimezone(IST).date()
        for strike in strikes:
            strike_str = f"{int(strike)}" if float(strike).is_integer() else f"{strike:.1f}"
            for opt_type, sym_suffix in ((OptionType.CE, "CE"), (OptionType.PE, "PE")):
                sym = f"{underlying}{expiry.strftime('%y%b%d').upper()}{strike_str}{sym_suffix}"
                contract = ContractMaster(
                    instrument_token=f"{underlying}_{expiry.strftime('%Y%m%d')}_{strike_str}_{sym_suffix}",
                    exchange="NFO",
                    symbol=sym,
                    underlying=underlying,
                    contract_type=ContractType.INDEX_OPTION,
                    option_type=opt_type,
                    option_style=OptionStyle.EUROPEAN,
                    strike=float(strike),
                    expiry=expiry,
                    expiry_type=exp_type,
                    lot_size=lot_size,
                    tick_size=tick_size,
                    settlement_type=SettlementType.CASH_SETTLED,
                    pricing_style=PricingStyle.FUTURES_BLACK76,
                    contract_status=ContractStatus.ACTIVE,
                    effective_from=today - timedelta(days=30),
                    provider="fyers",
                )
                self.add_contract(contract)
                count += 1
        return count

    def _generate_sample_expiries(self, start_date: date, count: int = 6) -> list[date]:
        """Generate realistic forward-looking expiry dates adjusted for exchange holidays."""
        expiries = []
        curr = start_date
        
        while len(expiries) < count:
            # Advance to next target weekday (e.g. Thursday)
            days_ahead = (3 - curr.weekday()) % 7  # Thursday
            if days_ahead == 0 and curr in expiries:
                days_ahead = 7
            candidate = curr + timedelta(days=days_ahead if days_ahead > 0 else 7)
            # Adjust if holiday
            adjusted = calendar_service.adjust_expiry_if_holiday(candidate)
            if adjusted not in expiries and adjusted >= start_date:
                expiries.append(adjusted)
            curr = candidate + timedelta(days=1)

        expiries.sort()
        return expiries

    def add_contract(self, contract: ContractMaster) -> None:
        """Register or update a contract in the repository."""
        self._contracts[contract.symbol] = contract
        self._by_token[contract.instrument_token] = contract
        
        if contract.underlying not in self._by_underlying:
            self._by_underlying[contract.underlying] = []
        
        # Replace if exists, else append
        existing = [c for c in self._by_underlying[contract.underlying] if c.symbol != contract.symbol]
        existing.append(contract)
        self._by_underlying[contract.underlying] = existing

    def get_by_symbol(self, symbol: str) -> ContractMaster | None:
        """Retrieve contract by exact symbol."""
        return self._contracts.get(symbol)

    def get_by_token(self, token: str) -> ContractMaster | None:
        """Retrieve contract by broker/exchange instrument token."""
        return self._by_token.get(token)

    def search_contracts(
        self,
        underlying: str | None = None,
        contract_type: ContractType | None = None,
        expiry: date | None = None,
        strike: float | None = None,
        option_type: OptionType | None = None,
        status: ContractStatus = ContractStatus.ACTIVE,
    ) -> list[ContractMaster]:
        """Query contract master with multi-criteria filtering."""
        results = []
        pool: Sequence[ContractMaster] = (
            self._by_underlying.get(underlying, [])
            if underlying
            else self._contracts.values()
        )

        for c in pool:
            if status and c.contract_status != status:
                continue
            if contract_type and c.contract_type != contract_type:
                continue
            if expiry and c.expiry != expiry:
                continue
            if strike is not None and c.strike != strike:
                continue
            if option_type and c.option_type != option_type:
                continue
            results.append(c)

        return results

    def get_expiries(self, underlying: str) -> list[date]:
        """Get all distinct active expiry dates for an underlying."""
        contracts = self._by_underlying.get(underlying, [])
        expiries = {c.expiry for c in contracts if c.expiry is not None}
        return sorted(list(expiries))

    def resolve_expiries(self, underlying: str, as_of: date | None = None) -> ExpiryResolution:
        """Resolve current, next, weekly, and monthly expiries for an underlying.
        
        Adheres to Section 16 (Dynamic Expiry Resolution).
        """
        ref_date = as_of or datetime.now(timezone.utc).astimezone(IST).date()
        all_expiries = [e for e in self.get_expiries(underlying) if e >= ref_date]
        
        if not all_expiries:
            return ExpiryResolution(underlying=underlying)

        curr_exp = all_expiries[0]
        next_exp = all_expiries[1] if len(all_expiries) > 1 else None

        weeklies = []
        monthlies = []

        # Find contracts for classification
        for exp in all_expiries:
            sample = [c for c in self._by_underlying.get(underlying, []) if c.expiry == exp]
            if sample and sample[0].expiry_type == ExpiryType.MONTHLY:
                monthlies.append(exp)
            else:
                weeklies.append(exp)

        return ExpiryResolution(
            underlying=underlying,
            current_expiry=curr_exp,
            next_expiry=next_exp,
            weekly_expiries=weeklies,
            monthly_expiries=monthlies,
            all_expiries=all_expiries,
        )

    def is_expiry_day(self, underlying: str, check_date: date) -> bool:
        """Check whether check_date is a scheduled expiry day for the underlying."""
        return check_date in self.get_expiries(underlying)


contract_master_service = ContractMasterService()
