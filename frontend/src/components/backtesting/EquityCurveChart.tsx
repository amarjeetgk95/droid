'use client';

import { EquityPointModel } from '@/lib/types';
import { LineChart } from 'lucide-react';

export function EquityCurveChart({
  equityCurve,
  initialCapital,
}: {
  equityCurve: EquityPointModel[];
  initialCapital: number;
}) {
  if (!equityCurve || equityCurve.length === 0) return null;

  const width = 800;
  const height = 240;
  const padding = { top: 20, right: 30, bottom: 30, left: 60 };

  const equities = equityCurve.map((e) => e.equity);
  const minEquity = Math.min(...equities, initialCapital * 0.9);
  const maxEquity = Math.max(...equities, initialCapital * 1.1);

  const xScale = (index: number) =>
    padding.left + (index / (equityCurve.length - 1 || 1)) * (width - padding.left - padding.right);

  const yScale = (val: number) => {
    const range = maxEquity - minEquity || 1;
    return height - padding.bottom - ((val - minEquity) / range) * (height - padding.top - padding.bottom);
  };

  // Generate SVG path for Equity curve
  const points = equityCurve.map((pt, idx) => `${xScale(idx)},${yScale(pt.equity)}`).join(' L ');
  const pathD = `M ${points}`;
  const areaD = `M ${points} L ${xScale(equityCurve.length - 1)},${yScale(minEquity)} L ${padding.left},${yScale(minEquity)} Z`;

  const initialY = yScale(initialCapital);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LineChart className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Cumulative Equity Growth & Drawdown Curve</h3>
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-emerald-400"></div>
            <span className="text-muted-foreground">Portfolio Equity</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-border border-dashed"></div>
            <span className="text-muted-foreground">Initial Capital (₹{initialCapital.toLocaleString('en-IN')})</span>
          </div>
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="w-full overflow-hidden">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
          {/* Baseline Capital */}
          <line
            x1={padding.left}
            y1={initialY}
            x2={width - padding.right}
            y2={initialY}
            stroke="currentColor"
            strokeDasharray="4 4"
            className="text-border"
            strokeWidth="1.5"
          />

          {/* Area gradient */}
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34d399" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#34d399" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Area Fill */}
          <path d={areaD} fill="url(#equityGrad)" />

          {/* Equity Line */}
          <path
            d={pathD}
            fill="none"
            stroke="#34d399"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Axis Labels */}
          <text
            x={padding.left}
            y={height - 8}
            className="text-[10px] fill-muted-foreground font-mono"
          >
            {equityCurve[0].timestamp}
          </text>
          <text
            x={width - padding.right}
            y={height - 8}
            textAnchor="end"
            className="text-[10px] fill-muted-foreground font-mono"
          >
            {equityCurve[equityCurve.length - 1].timestamp}
          </text>

          {/* Y-Axis Value Labels */}
          <text
            x={padding.left - 6}
            y={padding.top + 10}
            textAnchor="end"
            className="text-[9px] fill-muted-foreground font-mono"
          >
            ₹{Math.round(maxEquity).toLocaleString('en-IN')}
          </text>
          <text
            x={padding.left - 6}
            y={height - padding.bottom}
            textAnchor="end"
            className="text-[9px] fill-muted-foreground font-mono"
          >
            ₹{Math.round(minEquity).toLocaleString('en-IN')}
          </text>
        </svg>
      </div>
    </div>
  );
}
