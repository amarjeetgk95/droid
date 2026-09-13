"""Fetch third-party cached NSE FII/DII cash history (PIT-safe proxy, NOT NSE-direct).

Source: https://fii-diidata.mrchartist.com/api/history-full
  - Claims NSE-sourced cash (fetch-pipeline) + F&O participant OI.
  - Verified 2026-09-12: 152 cash rows real, but F&O all-zero for ~66 recent
    rows (pipeline broken after ~10-Jun-2026). Zeros are treated as MISSING,
    never as zero positioning.

PIT rules enforced here (fail-loud, no fabrication):
  - event_date parsed from 'd' (e.g. 11-Sep-2026); available_time = T+1 18:00 IST
  - buy-sell~=net validated within +/-2cr, else row rejected
  - F&O zeros -> None (missing), non-zero -> ingested with net+lsr
  - Output: backend/data/fii_dii_history.json {fetched_at, source, rows[]}
    Rows sorted ascending. flow_store loads this file on seed_rows().

Usage:
    .venv/Scripts/python scripts/ingest_fii_dii_history.py [--out data/fii_dii_history.json]

Verify exact numbers on nseindia.com before relying on them.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

URL = "https://fii-diidata.mrchartist.com/api/history-full"


def parse_d(s: str) -> str:
    # '11-Sep-2026' -> '2026-09-11'
    dt = datetime.strptime(s.strip(), "%d-%b-%Y")
    return dt.strftime("%Y-%m-%d")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/fii_dii_history.json")
    args = ap.parse_args()
    out_path = (BACKEND_ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)

    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Droid-ingest)"})
    raw = urllib.request.urlopen(req, timeout=30).read()
    j = json.loads(raw)
    assert isinstance(j, list) and len(j) > 0, "empty history"

    rows, rejected = [], []
    for r in j:
        try:
            evt = parse_d(str(r["d"]))
            fb, fs, fn = float(r["fb"]), float(r["fs"]), float(r["fn"])
            db, ds, dn = float(r["db"]), float(r["ds"]), float(r["dn"])
            if abs((fb - fs) - fn) > 2.0 or abs((db - ds) - dn) > 2.0:
                rejected.append((evt, "buy-sell!=net"))
                continue
            fl = r.get("fii_idx_fut_long", 0) or 0
            fss = r.get("fii_idx_fut_short", 0) or 0
            try:
                fl_i, fs_i = int(fl), int(fss)
            except Exception:
                fl_i, fs_i = 0, 0
            if fl_i == 0 and fs_i == 0:
                fut_net, lsr = None, None  # missing, never zero-fill
            else:
                fut_net = fl_i - fs_i
                lsr = round(fl_i / max(1, fs_i), 4) if fs_i else None
            rows.append(
                {
                    "event_date": evt,
                    "fii_cash_net_crores": round(fn, 2),
                    "dii_cash_net_crores": round(dn, 2),
                    "fii_cash_buy_crores": round(fb, 2),
                    "fii_cash_sell_crores": round(fs, 2),
                    "dii_cash_buy_crores": round(db, 2),
                    "dii_cash_sell_crores": round(ds, 2),
                    "fii_fut_long": fl_i if fut_net is not None else None,
                    "fii_fut_short": fs_i if fut_net is not None else None,
                    "fii_fut_net": fut_net,
                    "fii_lsr": lsr,
                    "pcr": r.get("pcr") if r.get("pcr") not in (0, 0.0, None) else None,
                }
            )
        except Exception as e:
            rejected.append((str(r.get("d")), f"parse:{e}"))
            continue

    rows.sort(key=lambda x: x["event_date"])
    # De-dupe same date (keep last occurrence = newest fetch).
    dedup = {}
    for x in rows:
        dedup[x["event_date"]] = x
    rows = [dedup[k] for k in sorted(dedup)]
    with_fo = sum(1 for x in rows if x["fii_fut_net"] is not None)

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "mrchartist_proxy_fetch-pipeline (third-party cache of NSE; verify on nseindia.com)",
        "url": URL,
        "note": "F&O zeros treated as missing. Cash provisional evening, final next morning; consumers must use available_time=T+1 18:00 IST.",
        "n_rows": len(rows),
        "n_with_fo": with_fo,
        "n_rejected": len(rejected),
        "rejected": rejected[:20],
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out_path} rows={len(rows)} with_fo={with_fo} rejected={len(rejected)} range={rows[0]['event_date']}->{rows[-1]['event_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
