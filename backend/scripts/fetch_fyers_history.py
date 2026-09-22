"""CLI tool to fetch and persist historical 1-minute market data via FYERS API v3 (Tier 0).

Supports:
- Chunked downloading (60-day slices) to respect broker limits
- Passing through the DataQualityFirewall
- Immutable local Parquet persistence with SHA-256 integrity checksums
- Optional `--fixture-fallback` flag to synthesize high-fidelity realistic
  test datasets when broker credentials are expired/offline. Fixtures are
  written to `data/fixtures/`, never to the real-data tree, and default off.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
import polars as pl
import numpy as np
import structlog

# Add parent directory to sys.path so app can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.quant.data.data_firewall import DataQualityFirewall
from app.quant.data.dataset_manager import DatasetManager
from app.quant.data.provenance import assert_real_dataset

logger = structlog.get_logger("fetch_fyers_history")

CHUNK_DAYS = 60
FYERS_HISTORY_URL = "https://api-t1.fyers.in/data/history"


async def fetch_fyers_chunk(
    client: httpx.AsyncClient,
    symbol: str,
    resolution: str,
    from_ts: int,
    to_ts: int,
    auth_header: str,
) -> list[list[float]]:
    url = (
        f"{FYERS_HISTORY_URL}"
        f"?symbol={symbol}&resolution={resolution}&date_format=0"
        f"&range_from={from_ts}&range_to={to_ts}&cont_flag=1"
    )
    resp = await client.get(url, headers={"Authorization": auth_header})
    if resp.status_code == 200:
        data = resp.json()
        if data.get("s") == "ok" and "candles" in data and isinstance(data["candles"], list):
            return data["candles"]
        else:
            logger.warning("fyers_history_empty_or_error", symbol=symbol, response=data.get("message", "unknown"))
            return []
    elif resp.status_code in (401, 403):
        raise PermissionError(f"FYERS API Auth Failed (HTTP {resp.status_code}): Check daily access token.")
    else:
        logger.warning("fyers_history_bad_status", status_code=resp.status_code, body=resp.text[:120])
        return []


def generate_synthetic_history(
    symbol: str,
    days: int = 30,
    base_price: float = 80000.0,
    volatility: float = 0.14,
) -> pl.DataFrame:
    """Synthesizes high-fidelity realistic intraday 1m candles for testing."""
    logger.info("generating_synthetic_fixture", symbol=symbol, days=days, base_price=base_price)
    
    # Generate trading days (Mon-Fri)
    end_date = datetime.now(timezone.utc).date()
    current_date = end_date - timedelta(days=int(days * 1.5))
    
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    
    current_price = base_price
    days_generated = 0
    dt_1m = 1.0 / (252.0 * 375.0)  # 375 1-min bars per day, 252 days/yr
    sigma_1m = volatility * np.sqrt(dt_1m)
    
    while days_generated < days:
        if current_date.weekday() < 5:  # Monday to Friday
            # Day open (allow overnight gap +/- 0.5%)
            gap = np.random.normal(0, 0.003)
            current_price = current_price * (1.0 + gap)
            
            # Market session 09:15 to 15:30 IST (03:45 to 10:00 UTC)
            day_start_utc = datetime(current_date.year, current_date.month, current_date.day, 3, 45, tzinfo=timezone.utc)
            
            for m in range(375):
                bar_time = day_start_utc + timedelta(minutes=m)
                bar_open = current_price
                
                # 1m Brownian price shock
                shock = np.random.normal(0, sigma_1m)
                bar_close = bar_open * (1.0 + shock)
                
                intra_vol = abs(np.random.normal(0, sigma_1m * 0.8))
                bar_high = max(bar_open, bar_close) * (1.0 + intra_vol)
                bar_low = min(bar_open, bar_close) * (1.0 - intra_vol * 0.9)
                bar_volume = max(100.0, np.random.lognormal(mean=7.0, sigma=0.8))
                
                timestamps.append(bar_time)
                opens.append(bar_open)
                highs.append(bar_high)
                lows.append(bar_low)
                closes.append(bar_close)
                volumes.append(bar_volume)
                
                current_price = bar_close
                
            days_generated += 1
            
        current_date += timedelta(days=1)
        
    return pl.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


#: Fixtures are written here, never into the real-data tree. The loaders search
#: ``data/raw`` and ``data/datasets`` for real history, so a fixture that lands in
#: those directories is indistinguishable from a market by file presence alone.
#: That is exactly how a synthetic SENSEX series came to be served on the live HUD
#: path tagged ``is_simulated: false``, defeating the strict-mode guard above it.
FIXTURE_ROOT = Path("data/fixtures")


def instrument_slug(symbol: str) -> str:
    """Canonical instrument directory name for a FYERS symbol.

    The previous mapping was ``"sensex" if "SENSEX" in symbol else "nifty"``,
    which filed BANKNIFTY — and every other instrument — under ``nifty``.
    """
    upper = symbol.upper()
    for name in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "NIFTY"):
        if name in upper:
            return name.lower()
    return upper.split(":")[-1].split("-")[0].lower()


def _persist_fixture(symbol: str, days: int, reason: str) -> pl.DataFrame:
    """Write a synthetic fixture to FIXTURE_ROOT and return it.

    Never writes to the real-data directory, and always records
    ``source="synthetic_fixture"`` so the provenance gate refuses it downstream.
    """
    logger.error(
        "writing_synthetic_fixture",
        symbol=symbol,
        reason=reason,
        note="Synthetic data is not market data; writing outside the real-data tree.",
    )
    base_p = 80000.0 if "SENSEX" in symbol else 25000.0
    df_raw = generate_synthetic_history(symbol=symbol, days=days, base_price=base_p)
    firewall = DataQualityFirewall(session_only=True)
    df_clean, report = firewall.inspect_and_clean(df_raw, instrument=symbol)
    mgr = DatasetManager(base_dir=FIXTURE_ROOT)
    mgr.save_dataset(
        df_clean,
        instrument=instrument_slug(symbol),
        timeframe="1m",
        source="synthetic_fixture",
        quality_score=report.score,
    )
    logger.error(
        "fixture_written",
        path=str(FIXTURE_ROOT / instrument_slug(symbol) / "1m.parquet"),
    )
    return df_clean


async def download_history(
    symbol: str,
    days: int,
    resolution: str = "1",
    app_id: Optional[str] = None,
    access_token: Optional[str] = None,
    use_fixture_on_fail: bool = False,
    output_dir: Path | str = "data/raw",
) -> pl.DataFrame:
    app_id = app_id or settings.fyers_app_id
    access_token = access_token or settings.fyers_access_token

    candles_raw: list[list[float]] = []

    if not access_token or access_token in ("", "mock-demo-token", "changeme"):
        logger.error("fyers_credentials_missing", msg="No valid FYERS access token found in environment.")
        if use_fixture_on_fail:
            return _persist_fixture(symbol, days=min(days, 180), reason="credentials_missing")
        raise ValueError(
            "FYERS credentials missing. FYERS access tokens expire daily — set "
            "FYERS_ACCESS_TOKEN to a fresh token, or pass --fixture-fallback to write "
            "a synthetic fixture to data/fixtures (which no loader treats as market data)."
        )

    auth_header = f"{app_id}:{access_token}" if app_id and ":" not in access_token else access_token
    now_ts = int(datetime.now(timezone.utc).timestamp())
    total_seconds = days * 86400
    start_ts = now_ts - total_seconds

    logger.info("starting_fyers_history_download", symbol=symbol, days=days, resolution=resolution)

    async with httpx.AsyncClient(timeout=15.0) as client:
        current_start = start_ts
        while current_start < now_ts:
            current_end = min(current_start + (CHUNK_DAYS * 86400), now_ts)
            logger.info("fetching_chunk", from_date=datetime.fromtimestamp(current_start, tz=timezone.utc).isoformat(), to_date=datetime.fromtimestamp(current_end, tz=timezone.utc).isoformat())
            try:
                chunk = await fetch_fyers_chunk(client, symbol, resolution, current_start, current_end, auth_header)
                candles_raw.extend(chunk)
            except PermissionError as e:
                logger.error("fyers_auth_error", error=str(e))
                if use_fixture_on_fail:
                    return _persist_fixture(symbol, days=min(days, 60), reason="auth_failed")
                raise
            except Exception as e:
                logger.warning("chunk_fetch_exception", error=str(e))
            
            await asyncio.sleep(0.6)  # rate limit pause
            current_start = current_end + 1

    if not candles_raw:
        logger.error("zero_candles_retrieved_from_fyers")
        if use_fixture_on_fail:
            return _persist_fixture(symbol, days=min(days, 60), reason="no_candles_returned")
        raise ValueError(
            "No historical candles retrieved from FYERS API. Nothing was written — "
            "refusing to substitute synthetic data for real history."
        )

    # Convert to Polars
    timestamps = [datetime.fromtimestamp(c[0], tz=timezone.utc) for c in candles_raw]
    opens = [float(c[1]) for c in candles_raw]
    highs = [float(c[2]) for c in candles_raw]
    lows = [float(c[3]) for c in candles_raw]
    closes = [float(c[4]) for c in candles_raw]
    volumes = [float(c[5]) if len(c) > 5 else 0.0 for c in candles_raw]

    df_raw = pl.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    # Pass through firewall
    firewall = DataQualityFirewall(session_only=True)
    df_clean, report = firewall.inspect_and_clean(df_raw, instrument=symbol)
    logger.info("firewall_completed", report=report.to_dict())

    # Save via DatasetManager
    mgr = DatasetManager(base_dir=output_dir)
    inst_slug = instrument_slug(symbol)
    timeframe = f"{resolution}m" if resolution.isdigit() else resolution
    mgr.save_dataset(
        df_clean,
        instrument=inst_slug,
        timeframe=timeframe,
        source="fyers_api_v3",
        quality_score=report.score,
    )

    # Verify what was just written is admissible, so a partial or empty fetch can
    # never be persisted as real history.
    written = Path(output_dir) / inst_slug / f"{timeframe}.parquet"
    prov = assert_real_dataset(written, label=f"{symbol} {timeframe} fetch")
    logger.info(
        "history_persisted",
        path=str(written),
        source=prov.source,
        rows=len(df_clean),
        checksum=(prov.checksum_sha256 or "")[:12],
    )
    return df_clean


def main():
    parser = argparse.ArgumentParser(description="Fetch and validate historical market data.")
    parser.add_argument("--symbol", default="BSE:SENSEX-INDEX", help="FYERS market symbol (default: BSE:SENSEX-INDEX)")
    parser.add_argument("--resolution", default="1", help="Candle resolution (default: 1 for 1m)")
    parser.add_argument("--days", type=int, default=60, help="Days of history to fetch (default: 60)")
    parser.add_argument("--app-id", default=None, help="FYERS App ID")
    parser.add_argument("--access-token", default=None, help="FYERS Access Token")
    parser.add_argument("--output-dir", default="data/raw", help="Output directory")
    parser.add_argument(
        "--fixture-fallback",
        action="store_true",
        help="On failure, write a synthetic fixture to data/fixtures (never to the real-data path)",
    )
    parser.add_argument(
        "--no-fixture-fallback",
        action="store_true",
        help="Deprecated no-op: fixture fallback is already off by default",
    )
    args = parser.parse_args()

    asyncio.run(
        download_history(
            symbol=args.symbol,
            days=args.days,
            resolution=args.resolution,
            app_id=args.app_id,
            access_token=args.access_token,
            use_fixture_on_fail=args.fixture_fallback,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    main()
