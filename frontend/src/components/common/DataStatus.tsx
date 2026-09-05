import { DataStatus as DataStatusType } from '@/lib/types';

export function DataStatus({ status }: { status: DataStatusType }) {
  let badgeClass = '';
  let icon = '●';
  let label = status as string;

  switch (status) {
    case 'LIVE':
      badgeClass = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
      icon = '●';
      label = 'LIVE';
      break;
    case 'STALE':
      badgeClass = 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30';
      icon = '▲';
      label = 'STALE';
      break;
    case 'OFFLINE':
      badgeClass = 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30';
      icon = '■';
      label = 'OFFLINE';
      break;
    case 'CLOSED':
      badgeClass = 'bg-secondary text-muted-foreground border-border';
      icon = '○';
      label = 'CLOSED';
      break;
    case 'DISCONNECTED':
    case 'ERROR':
      badgeClass = 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30';
      icon = '■';
      label = 'FEED DOWN';
      break;
    default:
      badgeClass = 'bg-muted text-muted-foreground border-border';
      icon = '○';
      label = status || 'UNKNOWN';
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-tight border select-none ${badgeClass}`}
    >
      <span className={`text-[8px] leading-none ${status === 'LIVE' ? 'animate-pulse' : ''}`}>{icon}</span>
      <span>{label}</span>
    </span>
  );
}

