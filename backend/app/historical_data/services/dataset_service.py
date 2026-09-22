"""Dataset Coordinator Service for Serving, Inspecting, and Exporting."""

from __future__ import annotations
import io
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import polars as pl

from app.historical_data.models.dataset import HistoricalDataset, HistoricalDatasetVersion
from app.historical_data.models.gap import DataGap
from app.historical_data.models.quality import HistoricalQualityReport
from app.historical_data.storage.db_repository import db_repo
from app.historical_data.storage.parquet_repository import parquet_repo


class HistoricalDatasetService:
    """Coordinates datasets, candle inspections, version histories, and exports."""

    async def list_datasets(self) -> List[Dict[str, Any]]:
        datasets = await db_repo.list_datasets()
        res = []
        for d in datasets:
            gaps = await db_repo.list_gaps(d.id)
            open_gaps = len([g for g in gaps if g.status == "OPEN"])
            d_dict = d.model_dump()
            d_dict["open_gaps"] = open_gaps
            res.append(d_dict)
        return res

    async def get_dataset_details(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        dataset = await db_repo.get_dataset(dataset_id)
        if not dataset:
            return None

        versions = await db_repo.list_versions(dataset_id)
        gaps = await db_repo.list_gaps(dataset_id)
        quality_report = await db_repo.get_latest_quality_report(dataset_id)

        return {
            "dataset": dataset.model_dump(),
            "versions": [v.model_dump() for v in versions],
            "gaps": [g.model_dump() for g in gaps],
            "latest_quality_report": quality_report.model_dump() if quality_report else None,
        }

    def get_candle_page(
        self,
        symbol: str,
        timeframe: str,
        version_tag: str = "v1",
        page: int = 1,
        page_size: int = 100,
        sort_desc: bool = True,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        rows, total = parquet_repo.get_paginated_candles(
            symbol=symbol,
            timeframe=timeframe,
            version_tag=version_tag,
            page=page,
            page_size=page_size,
            sort_desc=sort_desc,
            start_time=start_time,
            end_time=end_time,
        )
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "version": version_tag,
            "page": page,
            "page_size": page_size,
            "total_records": total,
            "total_pages": total_pages,
            "candles": rows,
        }

    def export_candles(
        self,
        symbol: str,
        timeframe: str,
        version_tag: str = "v1",
        export_format: str = "csv",
    ) -> Tuple[bytes, str, str]:
        """Export full dataset as bytes. Returns (bytes, media_type, filename)."""
        df = parquet_repo.load_candles(symbol, timeframe, version_tag=version_tag)
        clean_sym = symbol.replace(":", "_").replace("-", "_")

        if export_format.lower() == "parquet":
            buf = io.BytesIO()
            df.write_parquet(buf, compression="snappy")
            buf.seek(0)
            filename = f"{clean_sym}_{timeframe}_{version_tag}.parquet"
            return buf.getvalue(), "application/octet-stream", filename
        else:
            # Default CSV
            buf = io.BytesIO()
            df.write_csv(buf)
            buf.seek(0)
            filename = f"{clean_sym}_{timeframe}_{version_tag}.csv"
            return buf.getvalue(), "text/csv", filename


# Global dataset service instance
dataset_service = HistoricalDatasetService()
