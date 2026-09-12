"""Walk-forward validation runner for 1H forecast v2.3 (P1-2).

One-command OOS report with purge/embargo + session-aware settlement:

    python backend/scripts/validate_forecast_1h.py --instrument "NIFTY 50" \\
        --folds 5 --warmup 100 --stride 1 --costs base --out report.md+json

Loads real 1h + 1m candles via MarketService (broker history). NEVER uses
synthetic data: missing MarketService, empty history, or insufficient bars
exits non-zero with a clear remediation message (re-auth FYERS, check
history API). Emits markdown + JSON with per-fold, pooled, and
per-instrument/regime/session/direction tables (n, hit-rate + Wilson95,
naive baselines, excess, Brier, log-loss, ECE10 + reliability, MFE/MAE,
target/stop-hit, turnover).

Stdlib + repo modules only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Walk-forward 1H forecast v2.3 validation (purge/embargo).")
    p.add_argument("--instrument", default="NIFTY 50", help='Instrument, e.g. "NIFTY 50".')
    p.add_argument("--folds", type=int, default=5, help="Chronological folds (>=5).")
    p.add_argument("--warmup", type=int, default=100, help="Warmup 1h bars before first decision.")
    p.add_argument("--stride", type=int, default=1, help="Decision stride in 1h bars.")
    p.add_argument("--purge", type=int, default=1, dest="purge_bars",
                   help="Purge gap in 1h bars between train/test (default 1 = H).")
    p.add_argument("--embargo", type=int, default=1, dest="embargo_days",
                   help="Embargo in trading days between train/test (default 1).")
    p.add_argument("--costs", default="base",
                   help="Reference cost preset label recorded as costs_version (base/1.5x/2x).")
    p.add_argument("--out", default="walkforward_1h_report.md",
                   help='Output path. "report.md+json" writes report.md + report.json. '
                        "A bare .md also writes the sibling .json (and vice versa).")
    return p


def resolve_out_paths(raw: str) -> Tuple[Path, Path]:
    """Map --out to (md_path, json_path), supporting 'report.md+json'."""
    text = (raw or "").strip() or "walkforward_1h_report.md"
    if "+" in text:
        base = text.split("+")[0].strip()
        base = base.replace(".json", "").replace(".md", "").strip() or "walkforward_1h_report"
        return Path(base + ".md"), Path(base + ".json")
    if text.endswith(".md"):
        return Path(text), Path(text[: -len(".md")] + ".json")
    if text.endswith(".json"):
        stem = text[: -len(".json")]
        return Path(stem + ".md"), Path(text)
    return Path(text + ".md"), Path(text + ".json")


def _candle_to_dict(c: Any) -> Dict[str, Any]:
    if isinstance(c, dict):
        return c
    ts = getattr(c, "timestamp", None)
    try:
        ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    except Exception:
        ts_s = str(ts)
    def _f(v: Any, d: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return d
    return {
        "open": _f(getattr(c, "open", d := 0.0)),
        "high": _f(getattr(c, "high", 0.0)),
        "low": _f(getattr(c, "low", 0.0)),
        "close": _f(getattr(c, "close", 0.0)),
        "volume": _f(getattr(c, "volume", 0.0)),
        "timestamp": ts_s,
    }


async def _load_candles(instrument: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        from app.services.market_service import MarketService
    except Exception as e:
        raise RuntimeError(
            "MarketService is unavailable in this environment "
            f"({e}). Refusing to synthesize candles — run inside backend env "
            "with broker history configured."
        )
    try:
        ms = MarketService()
        raw_1h = await ms.get_candles(instrument, timeframe="1h")
        raw_1m = await ms.get_candles(instrument, timeframe="1m")
    except Exception as e:
        raise RuntimeError(
            f"Broker history fetch failed for {instrument!r} ({e}). "
            "Re-auth FYERS if the daily token expired, then retry. "
            "No synthetic data was generated."
        )
    candles_1h = [_candle_to_dict(c) for c in (raw_1h or [])]
    candles_1m = [_candle_to_dict(c) for c in (raw_1m or [])]
    if not candles_1h:
        raise RuntimeError(
            f"Insufficient 1h candle data for {instrument!r}: broker history "
            "returned 0 candles (available: none). Re-auth FYERS if the daily "
            "token expired, then retry. No synthetic data was generated."
        )
    return candles_1h, candles_1m


def _fmt_pct(x: Any) -> str:
    try:
        return f"{float(x):.2f}%"
    except Exception:
        return "n/a"


def _metrics_row(m: Dict[str, Any]) -> List[str]:
    w = m.get("wilson95") or [0.0, 0.0]
    try:
        ci = f"[{float(w[0]):.2f}%, {float(w[1]):.2f}%]"
    except Exception:
        ci = "[n/a]"
    return [
        str(m.get("n", 0)),
        f"{_fmt_pct(m.get('hit_rate', 0.0))} {ci}",
        _fmt_pct(m.get("baseline_naive_accuracy", 0.0)),
        _fmt_pct(m.get("baseline_buyhold_accuracy", 0.0)),
        f"{float(m.get('excess_vs_naive', 0.0)):+.2f}pp",
        f"{float(m.get('brier', 0.0)):.4f}",
        f"{float(m.get('log_loss', 0.0)):.4f}",
        f"{float(m.get('ece10', 0.0)):.4f}",
        f"{float(m.get('mfe_mean', 0.0)):.2f}",
        f"{float(m.get('mae_mean', 0.0)):.2f}",
        _fmt_pct(m.get("target_hit_rate", 0.0)),
        _fmt_pct(m.get("stop_hit_rate", 0.0)),
        f"{float(m.get('turnover', 0.0)):.4f}",
    ]


_METRICS_HEADER = (
    "| scope | n | hit-rate + Wilson95 | naive | buy&hold | excess | Brier | log-loss | "
    "ECE10 | MFE | MAE | tgt-hit | stop-hit | turnover |"
)
_METRICS_SEP = (
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
)


def _metrics_table(title: str, rows: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
    md = [f"### {title}", "", _METRICS_HEADER, _METRICS_SEP]
    for name, m in rows:
        cells = _metrics_row(m)
        md.append(f"| {name} " + "".join(f"| {c} " for c in cells) + "|")
    md.append("")
    return md


def render_markdown(report: Dict[str, Any], args: argparse.Namespace) -> str:
    params = report.get("params", {})
    pooled = report.get("pooled", {})
    folds = report.get("folds", [])
    lines = [
        "# Walk-forward 1H Forecast v2.3 Report (P1-2)",
        "",
        f"- Instrument: `{report.get('instrument')}` | horizon `{report.get('horizon')}` "
        f"({report.get('horizon_minutes')}m x{report.get('horizon_candles')})",
        f"- Target spec: `{report.get('target_spec_version')}` | costs: `{report.get('costs_version')}`",
        f"- Params: warmup={params.get('warmup')} stride={params.get('stride')} "
        f"folds={params.get('folds')} purge={params.get('purge_bars')}bar "
        f"embargo={params.get('embargo_days')}d ({params.get('embargo_bars')}bars, "
        f"gap={params.get('gap_bars')}bars)",
        f"- Candidates: {report.get('total_candidates')} | settleable n={report.get('n_settleable')} "
        f"| unsettleable n={report.get('n_unsettleable')} "
        f"reasons={json.dumps(report.get('unsettleable_reasons', {}))}",
        f"- Generated: `{report.get('generated_at')}`",
        "",
        "PIT: decision at bar t sees only candles[:t+1]; forward H bars quarantined. "
        "Folds are chronological with no shuffle; train ends gap bars before each test block. "
        "Unsettleable windows (cross-close/holiday/special/off-session via classify_window) "
        "are excluded from metrics and counted separately — never bridged.",
        "",
        "## Pooled (settleable only)",
        "",
    ]
    lines.extend(_metrics_table("pooled", [("pooled", pooled)]))
    lines.extend(["## Per-fold (settleable only)", ""])
    fold_rows = [(f"fold-{f.get('fold')} test[{f.get('test_start')}:{f.get('test_end')}] "
                  f"train[{f.get('train_start')}:{f.get('train_end')}]",
                  f.get("metrics", {})) for f in folds]
    lines.extend(_metrics_table("per-fold", fold_rows))
    lines.extend(["## By instrument", ""])
    lines.extend(_metrics_table("per-instrument",
                                [(k, v) for k, v in (report.get("by_instrument", {}) or {}).items()]))
    lines.extend(["## By regime", ""])
    lines.extend(_metrics_table("per-regime",
                                [(k, v) for k, v in (report.get("by_regime", {}) or {}).items()]))
    lines.extend(["## By session", ""])
    lines.extend(_metrics_table("per-session",
                                [(k, v) for k, v in (report.get("by_session", {}) or {}).items()]))
    lines.extend(["## By direction", ""])
    lines.extend(_metrics_table("per-direction",
                                [(k, v) for k, v in (report.get("by_direction", {}) or {}).items()]))
    lines.extend(["## Reliability (pooled ECE10, confidence=max P vs hit)", "",
                  "| bin | range | n | accuracy | avg_conf |",
                  "|---|---|---|---|---|"])
    for row in (pooled.get("reliability_table", []) or []):
        lines.append(
            f"| {row.get('bin')} | [{row.get('lo')}, {row.get('hi')}] "
            f"| {row.get('n')} | {float(row.get('accuracy', 0.0)):.4f} "
            f"| {float(row.get('avg_confidence', 0.0)):.4f} |"
        )
    lines.extend(["", "## Leakage audit", ""])
    audit = report.get("leakage_audit", {})
    for k in ("chronological", "no_shuffle", "purge_respected", "gap_bars",
              "purge_bars", "embargo_days", "embargo_bars"):
        lines.append(f"- {k}: `{json.dumps(audit.get(k))}`")
    lines.extend(["", "## Cost note", "",
                  f"- costs_version `{report.get('costs_version')}` recorded; turnover "
                  f"`{pooled.get('turnover')}` (traded {pooled.get('n_traded')}/{pooled.get('n')}). "
                  "Net P&L under base/1.5x/2x is computed by the P1-5 cost runner when "
                  "returns are available; this harness never invents fills.",
                  ""])
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> Dict[str, Any]:
    if args.folds is not None and args.folds < 5:
        raise SystemExit("--folds must be >= 5")
    if args.warmup is not None and args.warmup < 1:
        raise SystemExit("--warmup must be >= 1")
    candles_1h, candles_1m = await _load_candles(args.instrument)
    if len(candles_1h) < (args.warmup + args.folds + 1):
        raise RuntimeError(
            f"Insufficient 1h candles for {args.instrument!r}: got {len(candles_1h)}, "
            f"need warmup({args.warmup}) + folds({args.folds}) + H(1). "
            "Fetch a longer history window; no synthetic data was generated."
        )
    from app.research.validation.backtest_engine import WalkForwardGate

    report = WalkForwardGate.run_walkforward(
        candles_1h=candles_1h,
        candles_1m=candles_1m,
        instrument=args.instrument,
        warmup=args.warmup,
        stride=args.stride,
        folds=args.folds,
        purge_bars=args.purge_bars,
        embargo_days=args.embargo_days,
        options_ctx=None,
        cost_model=args.costs,
        label_fn=None,
    )
    return report


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = asyncio.run(main_async(args))
    except SystemExit:
        raise
    except RuntimeError as e:
        print(f"validate_forecast_1h failed: {e}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as e:
        print(f"validate_forecast_1h failed: {e}", file=sys.stderr)
        raise SystemExit(1)
    md_path, json_path = resolve_out_paths(args.out)
    md_text = render_markdown(report, args)
    try:
        if md_path.parent and str(md_path.parent) not in ("", "."):
            md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")
        if json_path.parent and str(json_path.parent) not in ("", "."):
            json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        print(f"failed writing reports: {e}", file=sys.stderr)
        raise SystemExit(1)
    pooled = report.get("pooled", {})
    print(f"wrote {md_path} + {json_path} "
          f"(n={pooled.get('n')} hit={pooled.get('hit_rate')}% "
          f"unsettleable={report.get('n_unsettleable')})")


if __name__ == "__main__":
    main()
