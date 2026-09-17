"""Quote-quality policy matrix + 4 legacy call-site conformance (Phase-1 ticket)."""
from types import SimpleNamespace

from app.signals import quote_quality as qq


def _q(status, provider="fyers", ltp=24870.0):
    return SimpleNamespace(status=status, provider=provider, ltp=ltp)


def test_classify_matrix():
    assert qq.classify_quote(_q("LIVE")) == "LIVE"
    for s in ("DEGRADED", "STALE", "CLOSED", "OFFLINE", "INVALID"):
        assert qq.classify_quote(_q(s)) != "LIVE", s
    # Synthetic provider poisons even a LIVE status.
    assert qq.classify_quote(_q("LIVE", "fallback")) == "INVALID"
    assert qq.classify_quote(_q("LIVE", "synthetic")) == "INVALID"
    assert qq.classify_quote(_q("LIVE", "mock")) == "INVALID"
    assert qq.classify_quote(None) == "OFFLINE"


def test_fallback_and_usable_flags():
    assert qq.is_fallback_quote(_q("LIVE")) is False
    assert qq.is_fallback_quote(_q("STALE")) is True
    assert qq.is_fallback_quote(_q("DEGRADED")) is True
    assert qq.is_generation_usable(_q("LIVE")) is True
    assert qq.is_generation_usable(_q("STALE")) is False
    assert qq.is_generation_usable(_q("LIVE", "mock")) is False
    assert qq.is_generation_usable(_q("LIVE", ltp=0)) is False


def test_legacy_helpers_conform_on_core_cases():
    """Phase-1 rewire ticket: scanner+pipeline already match the canonical
    policy; manual+api are narrower (OFFLINE-only) and must be rewired to
    quote_quality (tests 1-2). This pins the agreed subset so the gap is
    visible instead of silent."""
    from app.signals.pipeline.data_acquisition import is_fallback_quote as pipe_fb
    from app.signals.scanner import SignalScanner
    from app.signals.manual_signal_service import _quote_is_fallback as man_fb
    from app.api.signals import _quote_is_fallback as api_fb

    scan_fb = SignalScanner._is_fallback_quote
    # Full agreement on the safety-critical core.
    for fb in (pipe_fb, scan_fb, man_fb, api_fb):
        assert fb(_q("LIVE")) is False
        assert fb(_q("OFFLINE")) is True
        assert fb(_q("LIVE", "fallback")) is True
    # All four call sites now delegate to the unified policy (Phase-1 done):
    # strict set enforced everywhere.
    for fb in (pipe_fb, scan_fb, man_fb, api_fb):
        assert fb(_q("DEGRADED")) is True
        assert fb(_q("STALE")) is True
        assert fb(_q("CLOSED")) is True
    assert qq.is_fallback_quote(_q("DEGRADED")) is True
