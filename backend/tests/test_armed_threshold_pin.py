"""Pin ARMED_THRESHOLD to scoring_weights.json (fail on 70/78 drift)."""
import json
from pathlib import Path


def _weights_path():
    for p in (Path("backend/config/scoring_weights.json"),
              Path(__file__).resolve().parents[1] / "config" / "scoring_weights.json",
              Path(__file__).resolve().parents[2] / "config" / "scoring_weights.json"):
        if p.exists():
            return p
    raise AssertionError("scoring_weights.json not found")


def test_armed_threshold_matches_file():
    cfg = json.loads(_weights_path().read_text(encoding="utf-8"))
    file_armed = float(cfg["thresholds"]["armed"])
    from app.signals.confluence import ARMED_THRESHOLD
    assert ARMED_THRESHOLD == file_armed, f"code {ARMED_THRESHOLD} != file {file_armed}"


def test_all_consumers_agree():
    from app.signals.confluence import ARMED_THRESHOLD as c
    from app.signals.pipeline.signal_factory import ARMED_THRESHOLD as f  # noqa
    import app.signals.pipeline.enrichment as e  # noqa
    assert float(c) == float(f)
    assert hasattr(e, "ARMED_THRESHOLD")
