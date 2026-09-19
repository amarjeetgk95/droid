'use client';

import React, { useState, useMemo, useEffect } from 'react';

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render?: (row: T, index: number) => React.ReactNode;
  sortable?: boolean;
  /** Derives the sort value when it is not a raw `row[key]` (formatted/derived columns). */
  sortValue?: (row: T) => unknown;
  align?: 'left' | 'center' | 'right';
  className?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  keyExtractor: (row: T, index: number) => string;
  emptyMessage?: string;
  pageSize?: number;
  /** Set false for small operational tables that must show every row. */
  paginate?: boolean;
  onRowClick?: (row: T) => void;
  className?: string;
}

function compareValues(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  const as = String(a);
  const bs = String(b);
  if (as < bs) return -1;
  if (as > bs) return 1;
  return 0;
}

export function DataTable<T>({
  data,
  columns,
  keyExtractor,
  emptyMessage = 'No records found',
  pageSize = 10,
  paginate = true,
  onRowClick,
  className = '',
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);

  const handleHeaderClick = (col: Column<T>) => {
    if (!col.sortable) return;
    if (sortKey === col.key) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(col.key);
      setSortOrder('asc');
    }
  };

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return data;
    return [...data].sort((a, b) => {
      const valA = col.sortValue ? col.sortValue(a) : (a as unknown as Record<string, unknown>)[sortKey];
      const valB = col.sortValue ? col.sortValue(b) : (b as unknown as Record<string, unknown>)[sortKey];
      if (valA == null && valB == null) return 0;
      if (valA == null) return 1;
      if (valB == null) return -1;
      const result = compareValues(valA, valB);
      return sortOrder === 'asc' ? result : -result;
    });
  }, [data, sortKey, sortOrder, columns]);

  const totalPages = paginate ? Math.max(1, Math.ceil(sortedData.length / pageSize)) : 1;
  // Clamp during render so a shrinking dataset never shows an empty page…
  const safePage = Math.min(page, totalPages);
  // …and keep the stored page in sync for subsequent interactions.
  useEffect(() => {
    setPage((p) => Math.min(p, totalPages));
  }, [totalPages]);

  const paginatedData = useMemo(() => {
    if (!paginate) return sortedData;
    const start = (safePage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, safePage, pageSize, paginate]);

  return (
    <div className={`overflow-x-auto w-full ${className}`}>
      <table className="w-full text-left text-xs border-collapse">
        <thead>
          <tr className="border-b border-border bg-surface-subtle text-ink-3 tracking-wide">
            {columns.map((col) => {
              const isSorted = sortKey === col.key;
              const ariaSort = col.sortable
                ? isSorted
                  ? sortOrder === 'asc'
                    ? 'ascending'
                    : 'descending'
                  : 'none'
                : undefined;
              const alignClass =
                col.align === 'right'
                  ? 'text-right'
                  : col.align === 'center'
                    ? 'text-center'
                    : 'text-left';
              return (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={ariaSort}
                  className={`py-2.5 px-3 font-semibold select-none ${alignClass} ${col.className || ''}`}
                >
                  <div
                    className={`inline-flex items-center gap-1 ${
                      col.align === 'right'
                        ? 'justify-end'
                        : col.align === 'center'
                          ? 'justify-center'
                          : ''
                    }`}
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        onClick={() => handleHeaderClick(col)}
                        className={`inline-flex items-center gap-1 font-semibold tracking-wide cursor-pointer hover:text-foreground ${
                          alignClass
                        }`}
                      >
                        {col.header}
                        {isSorted && (
                          <span className="text-primary" aria-hidden="true">
                            {sortOrder === 'asc' ? '▲' : '▼'}
                          </span>
                        )}
                      </button>
                    ) : (
                      col.header
                    )}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle font-sans">
          {paginatedData.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="text-center py-8 text-ink-4 font-mono">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            paginatedData.map((row, index) => (
              <tr
                key={keyExtractor(row, index)}
                onClick={() => onRowClick && onRowClick(row)}
                className={`transition-colors hover:bg-muted ${onRowClick ? 'cursor-pointer' : ''}`}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`py-2 px-3 text-foreground ${
                      col.align === 'right'
                        ? 'text-right font-mono'
                        : col.align === 'center'
                          ? 'text-center'
                          : 'text-left'
                    } ${col.className || ''}`}
                  >
                    {col.render ? col.render(row, index) : String((row as unknown as Record<string, unknown>)[col.key] ?? '-')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>

      {paginate && totalPages > 1 && (
        <nav
          aria-label="Table pagination"
          className="flex items-center justify-between px-3 py-2 border-t border-border bg-surface-subtle text-xs font-mono text-ink-3"
        >
          <div>
            Showing {(safePage - 1) * pageSize + 1} to{' '}
            {Math.min(safePage * pageSize, sortedData.length)} of {sortedData.length}
          </div>
          <div className="flex items-center gap-1">
            <button
              disabled={safePage <= 1}
              onClick={() => setPage(Math.max(1, safePage - 1))}
              className="px-2 py-0.5 rounded-sm border border-border-strong disabled:opacity-30 hover:bg-muted-strong text-ink-2"
            >
              Prev
            </button>
            <span className="px-2">
              {safePage} / {totalPages}
            </span>
            <button
              disabled={safePage >= totalPages}
              onClick={() => setPage(Math.min(totalPages, safePage + 1))}
              className="px-2 py-0.5 rounded-sm border border-border-strong disabled:opacity-30 hover:bg-muted-strong text-ink-2"
            >
              Next
            </button>
          </div>
        </nav>
      )}
    </div>
  );
}
