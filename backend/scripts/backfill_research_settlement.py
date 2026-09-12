"""Backfill settlement for research predictions (P1-1).

Settles ``research_predictions`` rows (default ``trend_forecast_1h``) whose
60m window has elapsed, labeling with ``v2-atr-em-session`` and appending to
``research_prediction_outcomes``. Same-session windows only — overnight gaps
are never bridged (see ``app.research.settlement``).

Usage (from repo root):
    python backend/scripts/backfill_research_settlement.py \
        --indicator trend_forecast_1h --since 90d --limit 500 --dry-run
    python backend/scripts/backfill_research_settlement.py \
        --indicator trend_forecast_1h --since 90d --limit 500 --commit

``--commit`` writes outcomes; without it (or with ``--dry-run``) nothing is
written. Stdlib only — no new dependencies.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass


def parse_since(raw: str | None) -> datetime | None:
    """Parse --since: '<N>d' (days back), YYYY-MM-DD, or full ISO datetime."""
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.lower().endswith("d"):
        try:
            days = int(text[:-1])
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid --since {raw!r}: use '<N>d', YYYY-MM-DD, or ISO datetime"
            )
        if days < 0:
            raise argparse.ArgumentTypeError("--since days must be >= 0")
        return datetime.now(timezone.utc) - timedelta(days=days)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid --since {raw!r}: use '<N>d', YYYY-MM-DD, or ISO datetime"
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Backfill research prediction settlement (v2 spec).")
    p.add_argument("--indicator", default="trend_forecast_1h",
                   help="Exact research indicator_id to settle (default: trend_forecast_1h).")
    p.add_argument("--indicator-prefix", default=None,
                   help="Prefix match instead of --indicator (e.g. trend_forecast_).")
    p.add_argument("--since", default="90d",
                   help="Only rows with timestamp >= this ('<N>d', YYYY-MM-DD, ISO). Default 90d.")
    p.add_argument("--limit", type=int, default=500, help="Max rows to process (default 500).")
    p.add_argument("--dry-run", action="store_true", default=False,
                   help="Plan only; write nothing (default unless --commit).")
    p.add_argument("--commit", action="store_true", default=False,
                   help="Append outcomes for settleable rows.")
    return p


async def main_async(args: argparse.Namespace) -> dict:
    from app.core.database import get_async_session_factory
    from app.research.settlement import settle_due_research

    dry_run = True if args.dry_run or not args.commit else False
    since_utc = parse_since(args.since)
    factory = get_async_session_factory()
    if factory is None:
        raise RuntimeError("Database is not configured (DATABASE_URL missing) — aborting backfill.")

    indicator = None if args.indicator_prefix else args.indicator
    prefix = args.indicator_prefix or "trend_forecast_"
    async with factory() as session:
        summary = await settle_due_research(
            session,
            indicator_prefix=prefix,
            limit=args.limit,
            indicator=indicator,
            since_utc=since_utc,
            dry_run=dry_run,
        )
    scope = {"indicator": indicator, "indicator_prefix": None if indicator else prefix,
             "since": since_utc.isoformat() if since_utc else None,
             "limit": args.limit, "dry_run": dry_run}
    return {"scope": scope, "summary": summary}


def main() -> None:
    args = build_parser().parse_args()
    if args.limit is not None and args.limit <= 0:
        print("--limit must be > 0", file=sys.stderr)
        raise SystemExit(2)
    try:
        result = asyncio.run(main_async(args))
    except Exception as e:
        print(f"backfill failed: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, indent=2, default=str))
    if result["summary"].get("errors"):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
