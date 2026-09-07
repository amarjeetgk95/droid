/**
 * Lightweight client-side observability — zero dependencies.
 * - Errors caught by ErrorBoundary land in a bounded ring buffer for on-device triage.
 * - Web vitals (via `next/web-vitals`) are buffered the same way; no network calls,
 *   so this never adds 404 noise or blocks rendering. A future backend
 *   `/api/v1/client-logs` endpoint can flush the buffer when it exists.
 */

export interface ErrorReport {
  message: string;
  label?: string;
  stack?: string;
  componentStack?: string;
  url?: string;
  at: number;
}

export interface VitalReport {
  name: string;
  value: number;
  rating?: string;
  at: number;
}

const MAX_BUFFER = 50;

const errorBuffer: ErrorReport[] = [];
const vitalBuffer: VitalReport[] = [];

function safeUrl(): string | undefined {
  try {
    return typeof window !== 'undefined' ? window.location.href : undefined;
  } catch {
    return undefined;
  }
}

export function reportError(err: unknown, context?: { label?: string; componentStack?: string }): ErrorReport {
  const report: ErrorReport = {
    message: err instanceof Error ? err.message : String(err),
    label: context?.label,
    stack: err instanceof Error ? err.stack : undefined,
    componentStack: context?.componentStack,
    url: safeUrl(),
    at: Date.now(),
  };
  errorBuffer.push(report);
  if (errorBuffer.length > MAX_BUFFER) errorBuffer.splice(0, errorBuffer.length - MAX_BUFFER);
  if (process.env.NODE_ENV !== 'production' && process.env.NODE_ENV !== 'test') {
    console.error(`[telemetry]${report.label ? ` (${report.label})` : ''}`, report.message);
  }
  return report;
}

export function reportWebVital(metric: { name: string; value: number; rating?: string }): VitalReport {
  const report: VitalReport = { name: metric.name, value: metric.value, rating: metric.rating, at: Date.now() };
  vitalBuffer.push(report);
  if (vitalBuffer.length > MAX_BUFFER) vitalBuffer.splice(0, vitalBuffer.length - MAX_BUFFER);
  return report;
}

/** Last-N error reports, newest first — for diagnostics UI / support copy-paste. */
export function getRecentErrors(limit = 20): ErrorReport[] {
  return errorBuffer.slice(-limit).reverse();
}

/** Last-N web vital samples, newest first. */
export function getRecentVitals(limit = 20): VitalReport[] {
  return vitalBuffer.slice(-limit).reverse();
}

export function clearTelemetry(): void {
  errorBuffer.length = 0;
  vitalBuffer.length = 0;
}
