import { DataStatus as DataStatusType } from '@/lib/types';

export function DataStatus({ status }: { status: DataStatusType }) {
  let badgeClass = '';
  switch (status) {
    case 'DEMO': badgeClass = 'bg-warning/20 text-warning border-warning/50'; break;
    case 'LIVE': badgeClass = 'bg-success/20 text-success border-success/50 animate-pulse'; break;
    case 'STALE': badgeClass = 'bg-yellow-500/20 text-yellow-500 border-yellow-500/50'; break;
    case 'DISCONNECTED':
    case 'ERROR': badgeClass = 'bg-destructive/20 text-destructive border-destructive/50'; break;
    default: badgeClass = 'bg-muted text-muted-foreground border-border';
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${badgeClass}`}>
      {status === 'DEMO' ? 'DEMO DATA' : status}
    </span>
  );
}
