"""Champion / Challenger Promotion Engine.

Implements Section 30 of the DROID ML Production & Research Specification.
Safely promotes validated challenger artifacts to champion status:
  1. Archives current champion artifacts into app/ml/artifacts/archive/<timestamp>/
  2. Copies challenger artifacts and manifests into app/ml/artifacts/champion/
  3. Writes promotion audit entry to app/ml/artifacts/promotion_audit.jsonl
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).parent.parent / "app" / "ml" / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHAMPION_DIR = ARTIFACTS_DIR / "champion"
ARCHIVE_DIR = ARTIFACTS_DIR / "archive"
AUDIT_LOG_PATH = ARTIFACTS_DIR / "promotion_audit.jsonl"


def promote_challengers(model_prefixes: list[str] | None = None) -> list[str]:
    CHAMPION_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_sub = ARCHIVE_DIR / timestamp_str

    promoted: list[str] = []

    # Find all challenger files to promote
    challenger_files = list(CHALLENGER_DIR.glob("*.*"))
    if not challenger_files:
        print("No challenger artifacts found to promote.")
        return []

    for c_file in challenger_files:
        if model_prefixes:
            if not any(c_file.name.startswith(p) for p in model_prefixes):
                continue

        target_champion = CHAMPION_DIR / c_file.name

        # If champion already exists, archive it
        if target_champion.exists():
            archive_sub.mkdir(parents=True, exist_ok=True)
            archived_dest = archive_sub / c_file.name
            shutil.move(str(target_champion), str(archived_dest))
            print(f"Archived champion {target_champion.name} -> {archived_dest}")

        # Copy challenger to champion
        shutil.copy2(str(c_file), str(target_champion))
        promoted.append(c_file.name)
        print(f"Promoted challenger {c_file.name} -> {target_champion}")

    # Record audit log entry
    audit_entry = {
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive_folder": str(archive_sub) if archive_sub.exists() else None,
        "promoted_files": promoted,
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry) + "\n")

    print(f"\nPromotion complete! Promoted {len(promoted)} artifacts to {CHAMPION_DIR}")
    print(f"Audit record appended to {AUDIT_LOG_PATH}")
    return promoted


if __name__ == "__main__":
    promote_challengers()
