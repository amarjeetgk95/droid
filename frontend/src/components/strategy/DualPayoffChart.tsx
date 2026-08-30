'use client';

import { PayoffPointModel } from '@/lib/types';
import { TrendingUp, Target } from 'lucide-react';

export function DualPayoffChart({
  payoffCurve,
  spotPrice,
  breakevens,
  maxProfit,
  maxLoss,
}: {
  payoffCurve: PayoffPointModel[];
  spotPrice: number;
  breakevens: number[];
  maxProfit?: number | null;
  maxLoss?: number | null;
}) {
  if (!payoffCurve || payoffCurve.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-8 text-center text-muted-foreground">
        Configure legs above to generate strategy payoff curve.
      </div>
    );
  }

  const allPnls = payoffCurve.flatMap((p) => [p.expiry_pnl, p.t0_pnl]);
  const minPnl = Math.min(...allPnls, -1000);
  const maxPnl = Math.max(...allPnls, 1000);
  const pnlRange = maxPnl - minPnl || 1;

  const minSpot = payoffCurve[0].spot_price;
  const maxSpot = payoffCurve[payoffCurve.length - 1].spot_price;
  const spotRange = maxSpot - minSpot || 1;

  const chartHeight = 240;
  const chartWidth = 720;

  // Zero P&L line Y-coordinate
  const zeroY = chartHeight - ((0 - minPnl) / pnlRange) * chartHeight;

  // Function to convert (spot, pnl) to (x, y)
  const getX = (s: number) => ((s - minSpot) / spotRange) * chartWidth;
  const getY = (pnl: number) => chartHeight - ((pnl - minPnl) / pnlRange) * chartHeight;

  // Generate SVG path for Expiry Payoff
  const expiryPath = payoffCurve.reduce(
    (acc, p, idx) => `${acc} ${idx === 0 ? 'M' : 'L'} ${getX(p.spot_price)} ${getY(p.expiry_pnl)}`,
    ''
  );

  // Generate SVG path for T+0 Payoff
  const t0Path = payoffCurve.reduce(
    (acc, p, idx) => `${acc} ${idx === 0 ? 'M' : 'L'} ${getX(p.spot_price)} ${getY(p.t0_pnl)}`,
    ''
  );

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Dual-Curve Payoff Simulation (Expiry vs T+0)</h3>
        </div>
        <div className="flex items-center gap-4 text-xs font-semibold">
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-2.5 h-0.5 bg-emerald-400" /> At Expiry Payoff
          </span>
          <span className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-2.5 h-0.5 bg-cyan-400" /> T+0 Today Payoff
          </span>
        </div>
      </div>

      {/* SVG Payoff Canvas */}
      <div className="w-full overflow-x-auto bg-secondary/30 rounded-lg p-2 border border-border">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="w-full h-64 overflow-visible select-none"
        >
          {/* Zero Line */}
          <line
            x1="0"
            y1={zeroY}
            x2={chartWidth}
            y2={zeroY}
            stroke="currentColor"
            className="text-muted-foreground/40"
            strokeDasharray="4 4"
            strokeWidth="1.5"
          />

          {/* Current Spot Price Vertical Marker */}
          {spotPrice >= minSpot && spotPrice <= maxSpot && (
            <g>
              <line
                x1={getX(spotPrice)}
                y1={0}
                x2={getX(spotPrice)}
                y2={chartHeight}
                stroke="#6366f1"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
              <text
                x={getX(spotPrice)}
                y={14}
                fill="#6366f1"
                fontSize="10"
                fontWeight="bold"
                textAnchor="middle"
              >
                Spot: ₹{spotPrice}
              </text>
            </g>
          )}

          {/* Breakeven Vertical Markers */}
          {breakevens.map((be) => (
            <g key={be}>
              <line
                x1={getX(be)}
                y1={0}
                x2={getX(be)}
                y2={chartHeight}
                stroke="#f59e0b"
                strokeWidth="1.5"
                strokeDasharray="2 2"
              />
              <text
                x={getX(be)}
                y={chartHeight - 6}
                fill="#f59e0b"
                fontSize="9"
                fontFamily="monospace"
                fontWeight="bold"
                textAnchor="middle"
              >
                BE: ₹{be}
              </text>
            </g>
          ))}

          {/* Expiry Payoff Line */}
          <path
            d={expiryPath}
            fill="none"
            stroke="#10b981"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* T+0 Payoff Line */}
          <path
            d={t0Path}
            fill="none"
            stroke="#06b6d4"
            strokeWidth="2"
            strokeDasharray="5 3"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Footer Info */}
      <div className="flex flex-wrap items-center justify-between text-xs text-muted-foreground px-1">
        <div className="flex items-center gap-4">
          <span>
            Max Profit:{' '}
            <strong className="text-success font-bold font-mono">
              {maxProfit !== null && maxProfit !== undefined ? `₹${maxProfit.toLocaleString('en-IN')}` : 'Unlimited'}
            </strong>
          </span>
          <span>
            Max Loss:{' '}
            <strong className="text-destructive font-bold font-mono">
              {maxLoss !== null && maxLoss !== undefined ? `₹${maxLoss.toLocaleString('en-IN')}` : 'Unlimited'}
            </strong>
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Target className="w-3.5 h-3.5 text-warning" />
          <span>
            Breakevens: {breakevens.length > 0 ? breakevens.map((b) => `₹${b}`).join(', ') : 'None'}
          </span>
        </div>
      </div>
    </div>
  );
}
