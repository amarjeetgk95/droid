export function scalarToString(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function csvEscape(value: unknown): string {
  const s = scalarToString(value);
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function toCsv(
  rows: Array<Record<string, unknown>>,
  columns?: string[],
): string {
  if (rows.length === 0) return '';
  const cols =
    columns && columns.length > 0
      ? columns
      : Array.from(rows.reduce<Set<string>>((set, row) => {
          for (const key of Object.keys(row)) set.add(key);
          return set;
        }, new Set<string>()));
  const lines = [cols.map(csvEscape).join(',')];
  for (const row of rows) {
    lines.push(cols.map((col) => csvEscape(row[col])).join(','));
  }
  return lines.join('\r\n');
}

export function downloadBlob(filename: string, mime: string, data: string): void {
  if (typeof document === 'undefined') return;
  const blob = new Blob([data], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function timestampSlug(date: Date = new Date()): string {
  return date.toISOString().replace(/[:.]/g, '-').slice(0, 19);
}

export function exportRowsAsCsv(filename: string, rows: Array<Record<string, unknown>>): void {
  if (rows.length === 0) return;
  downloadBlob(filename, 'text/csv;charset=utf-8', toCsv(rows));
}

export function exportAsJson(filename: string, payload: unknown): void {
  downloadBlob(filename, 'application/json', JSON.stringify(payload, null, 2));
}
