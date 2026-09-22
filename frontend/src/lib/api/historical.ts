import type { ApiCore } from './client';

export type HistoricalDataset = {
  id: string;
  symbol: string;
  exchange: string;
  asset_type: string;
  timeframe: string;
  provider: string;
  status: 'INITIALIZED' | 'DOWNLOADING' | 'READY' | 'DEGRADED' | 'ERROR';
  current_version_id?: string | null;
  earliest_available_ts?: string | null;
  latest_available_ts?: string | null;
  total_candles: number;
  latest_quality_score: number;
  storage_bytes: number;
  parquet_relative_path?: string | null;
  open_gaps?: number;
  updated_at: string;
};

export type HistoricalDatasetVersion = {
  version_id: string;
  dataset_id: string;
  version_tag: string;
  start_time: string;
  end_time: string;
  row_count: number;
  checksum_sha256: string;
  quality_score: number;
  quality_status: string;
  parquet_path: string;
  created_at: string;
};

export type HistoricalDownloadJob = {
  job_id: string;
  dataset_id: string;
  symbol: string;
  timeframe: string;
  provider: string;
  range_from: string;
  range_to: string;
  status: 'QUEUED' | 'RUNNING' | 'PARTIAL' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  progress_pct: number;
  total_chunks: number;
  completed_chunks: number;
  rows_downloaded: number;
  rows_valid: number;
  rows_rejected: number;
  retry_count: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
};

export type HistoricalDataGap = {
  gap_id: string;
  dataset_id: string;
  trading_date: string;
  expected_candles: number;
  actual_candles: number;
  missing_candles: number;
  first_missing_ts?: string | null;
  last_missing_ts?: string | null;
  status: 'OPEN' | 'REPAIRING' | 'RESOLVED' | 'UNREPAIRABLE_UPSTREAM_OMISSION' | 'EXCHANGE_HALT_VERIFIED';
  repair_attempts: number;
  notes?: string | null;
};

export type CandleRecord = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  symbol: string;
  timeframe: string;
};

export type CandlePageResponse = {
  symbol: string;
  timeframe: string;
  version: string;
  page: number;
  page_size: number;
  total_records: number;
  total_pages: number;
  candles: CandleRecord[];
};

export type AutoSyncStatus = {
  enabled: boolean;
  is_running: boolean;
  next_run_ist: string;
  last_sync_at?: string | null;
  last_sync_status: string;
  last_summary?: Record<string, any>;
  tracked_symbols: string[];
};

export interface HistoricalApi {
  getHistoricalDatasets(): Promise<{ datasets: HistoricalDataset[] }>;
  getHistoricalDatasetDetails(id: string): Promise<{
    dataset: HistoricalDataset;
    versions: HistoricalDatasetVersion[];
    gaps: HistoricalDataGap[];
    latest_quality_report: any;
  }>;
  getHistoricalCandles(params: {
    symbol?: string;
    timeframe?: string;
    version?: string;
    page?: number;
    page_size?: number;
    sort_desc?: boolean;
    start_time?: string;
    end_time?: string;
  }): Promise<CandlePageResponse>;
  triggerHistoricalDownload(payload: {
    symbol: string;
    timeframe: string;
    range_from: string;
    range_to: string;
    force_refresh?: boolean;
  }): Promise<{ status: string; job: HistoricalDownloadJob }>;
  getHistoricalJobs(limit?: number): Promise<{ jobs: HistoricalDownloadJob[] }>;
  getHistoricalJob(jobId: string): Promise<{ job: HistoricalDownloadJob }>;
  cancelHistoricalJob(jobId: string): Promise<{ status: string; job: HistoricalDownloadJob }>;
  deleteHistoricalJob(jobId: string): Promise<{ status: string; job_id: string }>;
  cleanupHistoricalJobs(): Promise<{ status: string; reconciled_count: number }>;
  getHistoricalGaps(datasetId?: string): Promise<{ gaps: HistoricalDataGap[] }>;
  repairHistoricalGap(gapId: string): Promise<{ status: string; gap: HistoricalDataGap }>;
  deriveHistoricalTimeframes(payload: {
    symbol: string;
    source_timeframe?: string;
    target_timeframes?: string[];
  }): Promise<{ status: string; derived_count: number; datasets: HistoricalDataset[] }>;
  syncHistoricalDatasets(): Promise<{ status: string; count: number; datasets: HistoricalDataset[] }>;
  getHistoricalAutoSyncStatus(): Promise<AutoSyncStatus>;
  toggleHistoricalAutoSync(enabled?: boolean): Promise<AutoSyncStatus>;
  triggerHistoricalAutoSync(): Promise<{ status: string; message?: string; synced?: any[]; errors?: any[] }>;
  getHistoricalExportUrl(symbol: string, timeframe: string, version: string, format: string): string;
}

export function createHistoricalApi(core: ApiCore): HistoricalApi {
  return {
    async getHistoricalDatasets() {
      return core.request<{ datasets: HistoricalDataset[] }>('/api/v1/historical-data/datasets');
    },

    async getHistoricalDatasetDetails(id: string) {
      return core.request(`/api/v1/historical-data/datasets/${encodeURIComponent(id)}`);
    },

    async getHistoricalCandles(params) {
      const q = new URLSearchParams();
      if (params.symbol) q.set('symbol', params.symbol);
      if (params.timeframe) q.set('timeframe', params.timeframe);
      if (params.version) q.set('version', params.version);
      if (params.page) q.set('page', String(params.page));
      if (params.page_size) q.set('page_size', String(params.page_size));
      if (params.sort_desc !== undefined) q.set('sort_desc', String(params.sort_desc));
      if (params.start_time) q.set('start_time', params.start_time);
      if (params.end_time) q.set('end_time', params.end_time);
      return core.request<CandlePageResponse>(`/api/v1/historical-data/candles?${q.toString()}`);
    },

    async triggerHistoricalDownload(payload) {
      return core.request('/api/v1/historical-data/download', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getHistoricalJobs(limit = 20) {
      return core.request<{ jobs: HistoricalDownloadJob[] }>(`/api/v1/historical-data/jobs?limit=${limit}`);
    },

    async getHistoricalJob(jobId: string) {
      return core.request<{ job: HistoricalDownloadJob }>(`/api/v1/historical-data/jobs/${encodeURIComponent(jobId)}`);
    },

    async cancelHistoricalJob(jobId: string) {
      return core.request<{ status: string; job: HistoricalDownloadJob }>(
        `/api/v1/historical-data/jobs/${encodeURIComponent(jobId)}/cancel`,
        { method: 'POST' }
      );
    },

    async deleteHistoricalJob(jobId: string) {
      return core.request<{ status: string; job_id: string }>(
        `/api/v1/historical-data/jobs/${encodeURIComponent(jobId)}`,
        { method: 'DELETE' }
      );
    },

    async cleanupHistoricalJobs() {
      return core.request<{ status: string; reconciled_count: number }>(
        '/api/v1/historical-data/jobs/cleanup',
        { method: 'POST' }
      );
    },

    async getHistoricalGaps(datasetId = 'SENSEX_1M') {
      return core.request<{ gaps: HistoricalDataGap[] }>(`/api/v1/historical-data/gaps?dataset_id=${encodeURIComponent(datasetId)}`);
    },

    async repairHistoricalGap(gapId: string) {
      return core.request('/api/v1/historical-data/repair', {
        method: 'POST',
        body: JSON.stringify({ gap_id: gapId }),
      });
    },

    async deriveHistoricalTimeframes(payload) {
      return core.request('/api/v1/historical-data/derive', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async syncHistoricalDatasets() {
      return core.request<{ status: string; count: number; datasets: HistoricalDataset[] }>('/api/v1/historical-data/sync', {
        method: 'POST',
      });
    },

    async getHistoricalAutoSyncStatus() {
      return core.request<AutoSyncStatus>('/api/v1/historical-data/auto-sync/status');
    },

    async toggleHistoricalAutoSync(enabled?: boolean) {
      const query = enabled !== undefined ? `?enabled=${enabled}` : '';
      return core.request<AutoSyncStatus>(`/api/v1/historical-data/auto-sync/toggle${query}`, { method: 'POST' });
    },

    async triggerHistoricalAutoSync() {
      return core.request<{ status: string; message?: string; synced?: any[]; errors?: any[] }>('/api/v1/historical-data/auto-sync/trigger', {
        method: 'POST',
      });
    },

    getHistoricalExportUrl(symbol: string, timeframe: string, version: string, format: string) {
      return `${core.getBaseUrl()}/api/v1/historical-data/export?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&version=${encodeURIComponent(version)}&format=${encodeURIComponent(format)}`;
    },
  };
}
