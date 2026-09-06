from __future__ import annotations

from typing import Optional
import structlog

from app.event_engine.models import EventImpactMapping

logger = structlog.get_logger()


class ImpactMappingService:
    """Configurable Entity → Sector → Stock → Index → Derivative Impact Hierarchy (§11).
    
    Translates raw events into affected market instruments and sectors with
    explicit confidence scores and impact strengths.
    """

    def get_mappings_for_event(
        self,
        entity_id: str,
        event_type: str,
        sub_type: Optional[str] = None,
    ) -> list[EventImpactMapping]:
        """Derive standard impact tree for verified events."""
        entity_clean = entity_id.upper()
        mappings: list[EventImpactMapping] = []

        if entity_clean == "RBI" or event_type == "CENTRAL_BANK":
            # Primary Sector
            mappings.append(
                EventImpactMapping(
                    target_type="SECTOR",
                    target_symbol="BANKING",
                    impact_strength="HIGH",
                    relationship_confidence=1.0,
                    historical_sensitivity=0.95,
                    primary_or_secondary="PRIMARY",
                    notes="Direct monetary policy transmission to banking liquidity and credit spreads",
                )
            )

            # Benchmark Indices
            mappings.append(
                EventImpactMapping(
                    target_type="INDEX",
                    target_symbol="BANKNIFTY",
                    impact_strength="HIGH",
                    relationship_confidence=1.0,
                    historical_sensitivity=0.98,
                    primary_or_secondary="PRIMARY",
                    notes="Primary equity index reacting to policy rate and liquidity stance",
                )
            )
            mappings.append(
                EventImpactMapping(
                    target_type="INDEX",
                    target_symbol="NIFTY",
                    impact_strength="HIGH",
                    relationship_confidence=0.95,
                    historical_sensitivity=0.88,
                    primary_or_secondary="PRIMARY",
                    notes="Headline benchmark index influenced by banking sector weight (>30%)",
                )
            )
            mappings.append(
                EventImpactMapping(
                    target_type="INDEX",
                    target_symbol="FINNIFTY",
                    impact_strength="HIGH",
                    relationship_confidence=0.90,
                    historical_sensitivity=0.90,
                    primary_or_secondary="SECONDARY",
                    notes="Financial services index spanning NBFCs and private banks",
                )
            )

            # Key Heavyweight Banking Stocks
            for symbol in ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"]:
                mappings.append(
                    EventImpactMapping(
                        target_type="STOCK",
                        target_symbol=symbol,
                        impact_strength="HIGH",
                        relationship_confidence=0.85,
                        historical_sensitivity=0.80,
                        primary_or_secondary="SECONDARY",
                        notes=f"Key sector component with heavy weight in Nifty and BankNifty",
                    )
                )

            # Derivatives
            mappings.append(
                EventImpactMapping(
                    target_type="DERIVATIVE",
                    target_symbol="BANKNIFTY Options",
                    impact_strength="HIGH",
                    relationship_confidence=0.95,
                    historical_sensitivity=0.92,
                    primary_or_secondary="PRIMARY",
                    notes="ATM/OTM IV crush risk immediately following the policy announcement",
                )
            )
            mappings.append(
                EventImpactMapping(
                    target_type="DERIVATIVE",
                    target_symbol="NIFTY Options",
                    impact_strength="HIGH",
                    relationship_confidence=0.90,
                    historical_sensitivity=0.85,
                    primary_or_secondary="PRIMARY",
                    notes="Implied volatility regime shifts on front-week and monthly expiries",
                )
            )

        return mappings


impact_mapping_service = ImpactMappingService()
