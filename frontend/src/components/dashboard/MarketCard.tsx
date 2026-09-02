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
  // Reject non-finite values instead of producing NaN path points.
  const clean = data.filter((v) => Number.isFinite(v));
  if (clean.length < 2) return null;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1; // min !== max here (filtered finite, len>=2) but keep safe
  const width = 80;
  const height = 28;

  const points = clean
    .map((val, idx) => {
      const x = (idx / (clean.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');

  const strokeColor = isPositive ? '#22c55e' : '#ef4444';

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
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
      className={`rounded-xl border p-4 flex flex-col justify-between transition-all cursor-pointer select-none ${
        isSelected
          ? 'bg-primary/10 border-primary shadow-sm ring-1 ring-primary/30'
          : 'bg-card border-border hover:border-primary/50 hover:bg-secondary/30'
      }`}
    >
      <div className="flex justify-between items-start mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <h3 className="font-bold text-sm text-foreground truncate">
            {card.display_name || card.symbol}
          </h3>
          {isSelected && (
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          )}
        </div>
        <DataStatus status={card.status} />
      </div>

      <div className="my-1.5 flex items-center justify-between">
        <div>
          <div className="text-xl sm:text-2xl font-black tabular-nums tracking-tight text-foreground">
            {safeNum(card.ltp)}
          </div>
          <div
            className={`text-xs font-semibold flex items-center gap-1 mt-0.5 ${
              isPos ? 'text-emerald-500' : 'text-rose-500'
            }`}
          >
            <span>{isPos ? '▲' : '▼'}</span>
            <span>{safeNum(card.change)}</span>
            <span>({safeNum(card.change_percent)}%)</span>
          </div>
        </div>
        <div className="opacity-90 shrink-0">
          <Sparkline data={card.sparkline} isPositive={isPos} />
        </div>
      </div>

      {/* Day Range Bar */}
      {rangeSpan > 0 && (
        <div className="my-2 space-y-1">
          <div className="w-full bg-secondary/80 h-1.5 rounded-full overflow-hidden relative">
            <div
              className={`h-full rounded-full ${isPos ? 'bg-emerald-500' : 'bg-rose-500'}`}
              style={{ width: `${rangePct}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground tabular-nums">
            <span>L: {safeNum(card.low)}</span>
            <span>H: {safeNum(card.high)}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-1 text-[11px] text-muted-foreground border-t border-border/60 pt-2">
        <div className="flex justify-between">
          <span>Open:</span>
          <span className="text-foreground tabular-nums font-mono">{safeNum(card.open)}</span>
        </div>
        <div className="flex justify-between">
          <span>Prev:</span>
          <span className="text-foreground tabular-nums font-mono">{safeNum(card.previous_close)}</span>
        </div>
        <div className="flex justify-between">
          <span>Vol:</span>
          <span className="text-foreground tabular-nums font-mono">{safeInt(card.volume)}</span>
        </div>
        <div className="flex justify-between">
          <span>OI:</span>
          <span className="text-foreground tabular-nums font-mono">
            {card.open_interest !== null && card.open_interest !== undefined
              ? formatNumber(card.open_interest)
              : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}
