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

export function MarketCard({ card }: { card: IndexCard }) {
  const isPos = (card.change ?? 0) >= 0;

  return (
    <div className="bg-card rounded-lg border border-border p-4 flex flex-col justify-between hover:border-border/80 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <h3 className="font-bold text-foreground">{card.display_name || card.symbol}</h3>
        <DataStatus status={card.status} />
      </div>
      
      <div className="my-2 flex items-center justify-between">
        <div>
          <div className="text-2xl font-black tabular-nums tracking-tight">
            {safeNum(card.ltp)}
          </div>
          <div className={`text-xs font-semibold flex items-center gap-1 mt-0.5 ${isPos ? 'text-success' : 'text-danger'}`}>
            <span>{isPos ? '▲' : '▼'}</span>
            <span>{safeNum(card.change)}</span>
            <span>({safeNum(card.change_percent)}%)</span>
          </div>
        </div>
        <div className="opacity-90">
          <Sparkline data={card.sparkline} isPositive={isPos} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs text-muted-foreground">
        <div className="flex justify-between"><span>O:</span><span className="text-foreground tabular-nums">{safeNum(card.open)}</span></div>
        <div className="flex justify-between"><span>H:</span><span className="text-foreground tabular-nums">{safeNum(card.high)}</span></div>
        <div className="flex justify-between"><span>L:</span><span className="text-foreground tabular-nums">{safeNum(card.low)}</span></div>
        <div className="flex justify-between"><span>C:</span><span className="text-foreground tabular-nums">{safeNum(card.previous_close)}</span></div>
        <div className="flex justify-between mt-1 pt-1 border-t border-border"><span>Vol:</span><span className="text-foreground tabular-nums">{safeInt(card.volume)}</span></div>
        <div className="flex justify-between mt-1 pt-1 border-t border-border"><span>OI:</span><span className="text-foreground tabular-nums">{card.open_interest !== null && card.open_interest !== undefined ? formatNumber(card.open_interest) : 'N/A'}</span></div>
      </div>
    </div>
  );
}
