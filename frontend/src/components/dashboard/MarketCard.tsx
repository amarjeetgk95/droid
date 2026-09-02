import { IndexCard } from '@/lib/types';
import { DataStatus } from '../common/DataStatus';
import { safeNum, safeInt } from '@/lib/utils';

function formatNumber(num: number) {
  if (!Number.isFinite(num)) return '—';
  if (num >= 10000000) return (num / 10000000).toFixed(2) + 'Cr';
  if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
  if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
  return num.toString();
}

function Sparkline({ data, isPositive }: { data: number[]; isPositive: boolean }) {
  if (!data || data.length < 2) return null;
  const clean = data.filter((v) => Number.isFinite(v));
  if (clean.length < 2) return null;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1;
  const width = 72;
  const height = 24;
  const points = clean
    .map((val, idx) => {
      const x = (idx / (clean.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');
  const strokeColor = isPositive ? '#22c55e' : '#ef4444';
  return (
    <svg width={width} height={height} className="overflow-visible shrink-0">
      <polyline fill="none" stroke={strokeColor} strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" points={points} />
    </svg>
  );
}

interface MarketCardProps {
  card: IndexCard;
  isSelected?: boolean;
  onSelect?: () => void;
}

export function MarketCard({ card, isSelected = false, onSelect }: MarketCardProps) {
  const isPos = (card.change ?? 0) >= 0;
  const low = Number(card.low) || 0;
  const high = Number(card.high) || 0;
  const ltp = Number(card.ltp) || 0;
  const rangeSpan = high - low;
  const rangePct = rangeSpan > 0 ? Math.min(100, Math.max(0, ((ltp - low) / rangeSpan) * 100)) : 50;

  return (
    <div
      onClick={onSelect}
      className={`rounded-lg border p-3 flex flex-col justify-between transition-colors cursor-pointer select-none [contain:paint] cv-auto ${
        isSelected
          ? 'bg-blue-500/10 border-blue-500/30 ring-1 ring-blue-500/20'
          : 'bg-card border-border hover:border-border hover:bg-card/40'
      }`}
      style={{ contentVisibility: 'auto', containIntrinsicSize: '0 180px' } as React.CSSProperties}
    >
      <div className="flex justify-between items-start gap-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <h3 className="font-semibold text-[13px] tracking-tight text-foreground truncate">
            {card.display_name || card.symbol}
          </h3>
          {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />}
        </div>
        <DataStatus status={card.status} />
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[20px] font-bold tabular-nums tracking-tight leading-none text-foreground font-mono">
            {safeNum(card.ltp)}
          </div>
          <div className={`text-[11px] font-medium flex items-center gap-1 mt-1 tabular-nums ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
            <span className="text-[10px] leading-none">{isPos ? '▲' : '▼'}</span>
            <span>{safeNum(card.change)}</span>
            <span className="opacity-80">({safeNum(card.change_percent)}%)</span>
          </div>
        </div>
        <Sparkline data={card.sparkline} isPositive={isPos} />
      </div>

      {rangeSpan > 0 && (
        <div className="mt-2.5 space-y-1">
          <div className="w-full bg-secondary h-1 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${isPos ? 'bg-emerald-500' : 'bg-red-500'}`} style={{ width: `${rangePct}%` }} />
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground tabular-nums font-mono leading-none">
            <span>L {safeNum(card.low)}</span>
            <span>H {safeNum(card.high)}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2.5 text-[11px] border-t border-border pt-2.5">
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground text-[10px]">Open</span>
          <span className="text-foreground tabular-nums font-mono font-medium">{safeNum(card.open)}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground text-[10px]">Prev</span>
          <span className="text-foreground tabular-nums font-mono font-medium">{safeNum(card.previous_close)}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground text-[10px]">Vol</span>
          <span className="text-foreground tabular-nums font-mono font-medium">{safeInt(card.volume)}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground text-[10px]">OI</span>
          <span className="text-foreground tabular-nums font-mono font-medium">
            {card.open_interest != null ? formatNumber(card.open_interest) : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}
