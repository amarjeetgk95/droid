'use client';

import * as React from 'react';
import { Search, ArrowUpDown, ShieldCheck } from 'lucide-react';
import type { HpiAuditEntry } from '@/lib/types';
import { categoryLabel } from '@/lib/historical-intelligence/labels';
import { fmtMb, fmtNumber, fmtDateTime } from '@/lib/historical-intelligence/format';
import { Panel } from './Panel';
import { EmptyState } from './EmptyState';

interface Props {
  audit: HpiAuditEntry[];
}

type SortKey = 'timestamp' | 'derivative' | 'dataset' | 'records_deleted' | 'storage_released_mb';

export function HiAudit({ audit }: Props) {
  const [search, setSearch] = React.useState('');
  const [sortKey, setSortKey] = React.useState<SortKey>('timestamp');
  const [sortDir, setSortDir] = React.useState<'asc' | 'desc'>('desc');

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = audit;
    if (q) {
      list = list.filter((a) =>
        [a.derivative, a.dataset, a.reason, a.user_id].some((v) => v?.toLowerCase().includes(q))
      );
    }
    list = [...list].sort((a, b) => {
      const av = a[sortKey] as string | number;
      const bv = b[sortKey] as string | number;
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [audit, search, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  return (
    <Panel
      title="Deletion audit log"
      description={`${audit.length} total · ${filtered.length} filtered`}
      actions={
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search derivative, dataset, reason, user…"
            className="pl-7 pr-2 py-1.5 rounded-md border border-border bg-background text-xs w-64"
          />
        </div>
      }
      bare
    >
      <div className="px-4 sm:px-5 pb-4 sm:pb-5">
        {filtered.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck className="w-6 h-6" />}
            title={audit.length === 0 ? 'No deletions yet' : 'No matches'}
            description={audit.length === 0 ? 'Deletions will be recorded here for compliance and traceability.' : 'Try a different search term.'}
          />
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-xs">
              <thead className="bg-muted/50">
                <tr>
                  <Th label="When" onClick={() => toggleSort('timestamp')} active={sortKey === 'timestamp'} dir={sortDir} />
                  <Th label="Derivative" onClick={() => toggleSort('derivative')} active={sortKey === 'derivative'} dir={sortDir} />
                  <Th label="Dataset" onClick={() => toggleSort('dataset')} active={sortKey === 'dataset'} dir={sortDir} />
                  <Th label="Range" />
                  <Th label="Records" onClick={() => toggleSort('records_deleted')} active={sortKey === 'records_deleted'} dir={sortDir} align="right" />
                  <Th label="Released" onClick={() => toggleSort('storage_released_mb')} active={sortKey === 'storage_released_mb'} dir={sortDir} align="right" />
                  <Th label="Reason" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.deletion_id} className="border-t border-border/60 hover:bg-background/50">
                    <td className="p-2 text-muted-foreground whitespace-nowrap">{fmtDateTime(a.timestamp)}</td>
                    <td className="p-2 font-semibold">{a.derivative}</td>
                    <td className="p-2">{categoryLabel(a.dataset)}</td>
                    <td className="p-2 text-muted-foreground whitespace-nowrap">{fmtDateTime(a.start_date)} → {fmtDateTime(a.end_date)}</td>
                    <td className="p-2 text-right tabular-nums">{fmtNumber(a.records_deleted)}</td>
                    <td className="p-2 text-right tabular-nums">{fmtMb(a.storage_released_mb)}</td>
                    <td className="p-2 text-muted-foreground max-w-xs truncate" title={a.reason}>{a.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Panel>
  );
}

function Th({ label, onClick, active, dir, align }: { label: string; onClick?: () => void; active?: boolean; dir?: 'asc' | 'desc'; align?: 'left' | 'right' }) {
  const Comp: React.ElementType = onClick ? 'button' : 'span';
  return (
    <th className={`p-2 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <Comp onClick={onClick} className={`inline-flex items-center gap-1 ${onClick ? 'hover:text-foreground' : ''} ${active ? 'text-foreground' : ''}`}>
        {label}
        {onClick && <ArrowUpDown className={`w-3 h-3 ${active ? 'text-primary' : 'text-muted-foreground'} ${dir === 'asc' ? 'rotate-180' : ''}`} />}
      </Comp>
    </th>
  );
}