import { ApiCore, API_BASE, type RequestOptions } from './client';

const defaultCore = new ApiCore(API_BASE);

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  return defaultCore.request<T>(path, options);
}

export interface PapGate {
  name: string;
  passed: boolean;
  detail: string;
}

export interface PapInstrumentData {
  instrument: string;
  slug: string;
  path: string;
  present: boolean;
  admissible: boolean;
  source: string | null;
  row_count: number | null;
  checksum_sha256: string | null;
  reasons: string[];
  screen: Record<string, unknown> | null;
}

export interface PapReportSummary {
  file: string;
  verdict: string | null;
  created: string | null;
  criteria_version: string | null;
  experiment_id: string | null;
  unreadable?: boolean;
}

export type PapVerdict = 'PASS' | 'FAIL' | 'INCONCLUSIVE' | 'NOT_RUN';

export interface PapStatus {
  phase: string;
  verdict: PapVerdict;
  criteria_version: string;
  pre_registered: Record<string, string>;
  gates: PapGate[];
  instruments: PapInstrumentData[];
  token_present: boolean;
  horizons: string[];
  reports: PapReportSummary[];
}

export function createPapApi(core: ApiCore) {
  return {
    async getStatus(): Promise<PapStatus> {
      const res = await core.request<{ data: PapStatus }>('/api/v1/pap/status');
      return res.data;
    },
  };
}

export type PapApi = ReturnType<typeof createPapApi>;

export const papApi: PapApi = createPapApi(defaultCore);
