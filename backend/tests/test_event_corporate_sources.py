import pytest
from app.event_engine.sources.nse_bse import NSECorporateSourceAdapter, BSECorporateSourceAdapter
from app.event_engine.sources.sebi import SEBISourceAdapter
from app.event_engine.dedup_service import dedup_service


@pytest.mark.asyncio
async def test_nse_and_bse_corporate_adapters():
    nse = NSECorporateSourceAdapter()
    nse_items = await nse.fetch()
    assert len(nse_items) > 0

    norm = nse.normalize(nse_items[0])
    valid, err = nse.validate(norm)
    assert valid is True
    assert norm.source_type == "EXCHANGE"

    bse = BSECorporateSourceAdapter()
    bse_items = await bse.fetch()
    assert len(bse_items) > 0
    bse_norm = bse.normalize(bse_items[0])
    valid, _ = bse.validate(bse_norm)
    assert valid is True


@pytest.mark.asyncio
async def test_sebi_regulatory_adapter():
    sebi = SEBISourceAdapter()
    items = await sebi.fetch()
    assert len(items) > 0
    norm = sebi.normalize(items[0])
    valid, _ = sebi.validate(norm)
    assert valid is True
    assert norm.source_type == "REGULATOR"
