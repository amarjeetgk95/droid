// Human-readable labels for HPI/Historical Intelligence enums.
// Single source of truth so panels, dialogs, and reports stay consistent.

const CATEGORY_LABELS: Record<string, string> = {
  '1m_market_data': '1-minute market data',
  '5m_market_data': '5-minute market data',
  '15m_market_data': '15-minute market data',
  '1h_market_data': '1-hour market data',
  '1d_market_data': 'Daily market data',
  'futures': 'Futures chain',
  'option_chain': 'Option chain',
  'iv_surface': 'IV surface',
  'pcr_history': 'PCR history',
  'greeks': 'Greeks',
  'funding': 'Funding rates',
  'liquidations': 'Liquidations',
  'open_interest': 'Open interest',
  'volume_profile': 'Volume profile',
};

const CATEGORY_SHORT: Record<string, string> = {
  '1m_market_data': '1m data',
  '5m_market_data': '5m data',
  '15m_market_data': '15m data',
  '1h_market_data': '1h data',
  '1d_market_data': '1D data',
  'futures': 'Futures',
  'option_chain': 'Chain',
  'iv_surface': 'IV',
  'pcr_history': 'PCR',
  'greeks': 'Greeks',
  'funding': 'Funding',
  'liquidations': 'Liqs',
  'open_interest': 'OI',
  'volume_profile': 'Vol prof',
};

const ASSET_CLASS_LABELS: Record<string, string> = {
  INDEX: 'Index',
  CRYPTO: 'Crypto',
  EQUITY: 'Equity',
  COMMODITY: 'Commodity',
};

const STORAGE_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  WITHIN_TARGET: { label: 'Within target', tone: 'ok' },
  WARNING: { label: 'Warning', tone: 'warn' },
  EXCEEDS_HARD: { label: 'Exceeds ceiling', tone: 'danger' },
};

const COVERAGE_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  FULL: { label: 'Full', tone: 'ok' },
  PARTIAL: { label: 'Partial', tone: 'warn' },
  MISSING: { label: 'Missing', tone: 'danger' },
  DISABLED: { label: 'Disabled', tone: 'muted' },
  EMPTY: { label: 'Empty', tone: 'muted' },
};

const AUTO_DELETE_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  ON: { label: 'Auto-delete ON', tone: 'ok' },
  OFF: { label: 'Auto-delete OFF', tone: 'muted' },
  PARTIAL: { label: 'Auto-delete PARTIAL', tone: 'warn' },
};

const BIAS_TONE: Record<string, 'ok' | 'warn' | 'danger'> = {
  BULLISH: 'ok',
  NEUTRAL: 'warn',
  BEARISH: 'danger',
};

export function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] ?? cat.replace(/_/g, ' ');
}

export function categoryShort(cat: string): string {
  return CATEGORY_SHORT[cat] ?? cat.replace(/_/g, ' ');
}

export function assetClassLabel(ac: string): string {
  return ASSET_CLASS_LABELS[ac] ?? ac;
}

export function storageStatus(status: string) {
  return STORAGE_STATUS[status] ?? { label: status.replace(/_/g, ' '), tone: 'muted' as const };
}

export function coverageStatus(status: string) {
  return COVERAGE_STATUS[status] ?? { label: status, tone: 'muted' as const };
}

export function autoDeleteStatus(status: string) {
  return AUTO_DELETE_STATUS[status] ?? { label: status, tone: 'muted' as const };
}

export function biasTone(bias: string): 'ok' | 'warn' | 'danger' {
  return BIAS_TONE[bias] ?? 'warn';
}

export function sortDirectionLabel(dir: 'asc' | 'desc' | null): string {
  return dir === 'asc' ? '↑' : dir === 'desc' ? '↓' : '';
}