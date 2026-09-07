"""Unit tests for MI reader helpers — pure math + staleness bands.

Covers the fixes for: HEALTHY/STALE header flapping (widened RECENT band),
missing session-VWAP fallback, and missing developing-pivot fallback that left
Levels/Volume tabs empty and breakout_level permanently None.
"""
from types import SimpleNamespace

from app.institutional import mi_service as mi
from app.institutional.snapshot_buffer import synchronized_buffer


def _candle(h, lo, c, v):
    return SimpleNamespace(high=h, low=lo, close=c, volume=v, vwap=None)


class TestHealthBand:
    def test_live(self):
        assert mi.health_band(0) == "LIVE"
        assert mi.health_band(4999) == "LIVE"

    def test_recent_band_covers_rest_poll_cadence(self):
        # The old 5s STALE threshold flapped on every poll; 5-15s is RECENT.
        assert mi.health_band(5001) == "RECENT"
        assert mi.health_band(15000) == "RECENT"

    def test_stale(self):
        assert mi.health_band(15001) == "STALE"
        assert mi.health_band(999999) == "STALE"

    def test_unknown_age_is_stale(self):
        assert mi.health_band(None) == "STALE"

    def test_negative_clamped_to_live(self):
        assert mi.health_band(-50) == "LIVE"


class TestClassicPivots:
    def test_math(self):
        piv = mi.classic_pivots_from_ohlc(100, 90, 95)
        assert piv is not None
        assert piv["pivot"] == 95.0
        assert piv["r1"] == 100.0
        assert piv["s1"] == 90.0
        assert piv["r2"] == 105.0
        assert piv["s2"] == 85.0

    def test_bad_input_none(self):
        assert mi.classic_pivots_from_ohlc(90, 100, 95) is None  # high < low
        assert mi.classic_pivots_from_ohlc(0, 0, 0) is None
        assert mi.classic_pivots_from_ohlc(None, 90, 95) is None  # type: ignore


class TestSessionVwap:
    def test_weighted(self):
        candles = [_candle(100, 90, 95, 10), _candle(110, 100, 105, 30)]
        vwap = mi.session_vwap_from_candles(candles)
        # typical1=95*10 + typical2=105*30 → 4100/40 = 102.5
        assert vwap is not None and abs(float(vwap) - 102.5) < 1e-9

    def test_no_volume_none(self):
        assert mi.session_vwap_from_candles([_candle(100, 90, 95, 0)]) is None
        assert mi.session_vwap_from_candles([]) is None


class TestSessionPivots:
    def test_levels_and_breakout(self):
        candles = [_candle(100, 90, 95, 10), _candle(102, 91, 100, 20)]
        sr, bl = mi.session_pivots_from_candles(candles)
        assert sr is not None and bl is not None
        assert len(sr["support"]) == 2 and len(sr["resistance"]) == 2
        assert float(sr["resistance"][0]) == float(bl)

    def test_empty_none(self):
        assert mi.session_pivots_from_candles([]) == (None, None)


class TestSanitizeOptions:
    def test_zero_pcr_rejected(self):
        cleaned, reason = mi.sanitize_options_data({"pcr": 0.0})
        assert cleaned is None and reason

    def test_negative_pcr_rejected(self):
        cleaned, _ = mi.sanitize_options_data({"pcr": -0.5})
        assert cleaned is None

    def test_zero_totals_rejected(self):
        cleaned, reason = mi.sanitize_options_data({"pcr": 1.1, "total_call_oi": 0, "total_put_oi": 0})
        assert cleaned is None and "empty" in reason

    def test_valid_pcr_kept(self):
        src = {"pcr": 1.32, "total_call_oi": 1000, "total_put_oi": 1320, "pcr_volume": 0.9}
        cleaned, reason = mi.sanitize_options_data(src)
        assert cleaned == src and reason is None

    def test_legacy_pcr_without_totals_kept(self):
        # Ingest-seeded {"pcr": 1.3} has no totals — judge on PCR alone.
        cleaned, reason = mi.sanitize_options_data({"pcr": 1.3})
        assert cleaned == {"pcr": 1.3} and reason is None

    def test_none_passthrough(self):
        assert mi.sanitize_options_data(None) == (None, None)


class TestFeedBlock:
    def test_fresh_is_healthy(self, monkeypatch):
        now = 1_700_000_000_000
        feed = mi.feed_block("NIFTY", now - 1000, now, True, False)
        assert feed["health"] == "HEALTHY" and feed["is_stale"] is False

    def test_recent_not_stale(self):
        now = 1_700_000_000_000
        feed = mi.feed_block("NIFTY", now - 8000, now, True, False)
        assert feed["health"] == "HEALTHY" and feed["is_stale"] is False

    def test_genuinely_stale(self):
        now = 1_700_000_000_000
        feed = mi.feed_block("NIFTY", now - 20000, now, True, False)
        assert feed["health"] == "STALE" and feed["is_stale"] is True

    def test_no_spot_stale(self):
        now = 1_700_000_000_000
        feed = mi.feed_block("NIFTY", now, now, False, False)
        assert feed["health"] == "STALE" and feed["staleness_ms"] == 999999


class TestCrossSnapshot:
    def test_crypto_always_none(self):
        assert mi.build_cross_snapshot("BTCUSD", "CRYPTO", 1_700_000_000_000) is None

    def test_no_peer_snapshot_none(self):
        synchronized_buffer.clear()
        assert mi.build_cross_snapshot("NIFTY", "INDIAN_EQUITY", 1_700_000_000_000) is None
