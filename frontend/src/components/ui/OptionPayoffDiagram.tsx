'use client';

import { useId, useMemo, useState } from 'react';

export interface OptionPayoffProps {
  direction: 'LONG_CALL' | 'LONG_PUT' | string;
  strike: number;
  entryPremium: number;
  lotSize?: number;
  currentSpot?: number | null;
  target1Spot?: number | null;
  target2Spot?: number | null;
  stopLossSpot?: number | null;
  className?: string;
}

export function calculatePayoffAtExpiry(
  direction: string,
  spot: number,
  strike: number,
  premium: number,
  lotSize: number,
): number {
  const isCall = direction.toUpperCase().includes('CALL');
  const intrinsic = isCall ? Math.max(0, spot - strike) : Math.max(0, strike - spot);
  const pnlPerShare = intrinsic - premium;
  return pnlPerShare * lotSize;
}

export function OptionPayoffDiagram({
  direction,
  strike,
  entryPremium,
  lotSize = 25,
  currentSpot = null,
  target1Spot = null,
  target2Spot = null,
  stopLossSpot = null,
  className = '',
}: OptionPayoffProps) {
  const clipId = useId();
  const [hoverSpot, setHoverSpot] = useState<number | null>(null);

  const isCall = direction.toUpperCase().includes('CALL');
  const breakeven = isCall ? strike + entryPremium : strike - entryPremium;
  const maxLoss = entryPremium * lotSize;

  // Derive display price range
  const { minSpot, maxSpot, minPnl, maxPnl } = useMemo(() => {
    const rawSpan = Math.max(entryPremium * 4, strike * 0.03, 100);
    const keySpots = [
      strike,
      breakeven,
      currentSpot,
      target1Spot,
      target2Spot,
      stopLossSpot,
    ].filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0);

    const minKey = Math.min(...keySpots);
    const maxKey = Math.max(...keySpots);

    const span = Math.max(rawSpan, (maxKey - minKey) * 0.6);
    const low = Math.floor(Math.min(strike - span, minKey - span * 0.2));
    const high = Math.ceil(Math.max(strike + span, maxKey + span * 0.2));

    const pnlLow = calculatePayoffAtExpiry(direction, low, strike, entryPremium, lotSize);
    const pnlHigh = calculatePayoffAtExpiry(direction, high, strike, entryPremium, lotSize);
    const pnlAtTargets = [target1Spot, target2Spot]
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0)
      .map((s) => calculatePayoffAtExpiry(direction, s, strike, entryPremium, lotSize));

    const bottomPnl = Math.min(-maxLoss * 1.15, pnlLow, pnlHigh, ...pnlAtTargets);
    const topPnl = Math.max(maxLoss * 2.5, pnlLow, pnlHigh, ...pnlAtTargets, 1000);

    return { minSpot: low, maxSpot: high, minPnl: bottomPnl, maxPnl: topPnl };
  }, [direction, strike, entryPremium, lotSize, breakeven, currentSpot, target1Spot, target2Spot, stopLossSpot, maxLoss]);

  // Layout dimensions
  const width = 480;
  const height = 180;
  const padLeft = 50;
  const padRight = 30;
  const padTop = 20;
  const padBottom = 26;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const toX = (spot: number) => {
    const frac = (spot - minSpot) / (maxSpot - minSpot || 1);
    return padLeft + Math.max(0, Math.min(1, frac)) * chartW;
  };

  const toY = (pnl: number) => {
    const frac = (pnl - minPnl) / (maxPnl - minPnl || 1);
    return padTop + chartH - Math.max(0, Math.min(1, frac)) * chartH;
  };

  const fromX = (x: number) => {
    const clampedX = Math.max(padLeft, Math.min(width - padRight, x));
    const frac = (clampedX - padLeft) / chartW;
    return minSpot + frac * (maxSpot - minSpot);
  };

  const zeroY = toY(0);

  // Generate payoff curve points
  const pointsCount = 40;
  const step = (maxSpot - minSpot) / pointsCount;
  const pathPoints: Array<{ x: number; y: number; spot: number; pnl: number }> = [];

  // Ensure key strike & breakeven are exact points
  const spotSampleSet = new Set<number>();
  for (let i = 0; i <= pointsCount; i++) {
    spotSampleSet.add(Math.round(minSpot + i * step));
  }
  spotSampleSet.add(strike);
  spotSampleSet.add(Math.round(breakeven));
  const sortedSpots = Array.from(spotSampleSet).sort((a, b) => a - b);

  for (const s of sortedSpots) {
    const pnl = calculatePayoffAtExpiry(direction, s, strike, entryPremium, lotSize);
    pathPoints.push({ x: toX(s), y: toY(pnl), spot: s, pnl });
  }

  const pathD = pathPoints.reduce(
    (acc, pt, idx) => (idx === 0 ? `M ${pt.x},${pt.y}` : `${acc} L ${pt.x},${pt.y}`),
    '',
  );

  // Active inspected spot
  const activeSpot = hoverSpot ?? currentSpot ?? breakeven;
  const activePnl = calculatePayoffAtExpiry(direction, activeSpot, strike, entryPremium, lotSize);
  const activePnlPct = maxLoss > 0 ? (activePnl / maxLoss) * 100 : 0;
  const activeX = toX(activeSpot);
  const activeY = toY(activePnl);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = width / rect.width;
    const mouseX = (e.clientX - rect.left) * scaleX;
    setHoverSpot(Math.round(fromX(mouseX)));
  };

  return (
    <div className={`ds-card p-3 flex flex-col gap-2 ${className}`}>
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{isCall ? 'CALL' : 'PUT'} Payoff (Expiry)</span>
          <span className="text-muted-foreground font-mono">
            K={strike} | Prem=₹{entryPremium.toFixed(1)}
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono">
          <span>
            BE: <strong className="text-foreground">₹{breakeven.toFixed(0)}</strong>
          </span>
          <span>
            Max Loss: <strong style={{ color: 'var(--ds-bear)' }}>-₹{maxLoss.toFixed(0)}</strong>
          </span>
        </div>
      </div>

      <div className="relative w-full overflow-hidden select-none">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto block"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverSpot(null)}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={padLeft} y={padTop} width={chartW} height={chartH} />
            </clipPath>
          </defs>

          {/* Background Grid & Axis */}
          <line
            x1={padLeft}
            y1={zeroY}
            x2={width - padRight}
            y2={zeroY}
            stroke="var(--ds-border-strong)"
            strokeDasharray="3 3"
            strokeWidth="1"
          />

          {/* Shaded Risk Floor (Capped Loss Region) */}
          <rect
            x={padLeft}
            y={toY(-maxLoss)}
            width={chartW}
            height={Math.max(2, chartH + padTop - toY(-maxLoss))}
            fill="var(--ds-bear-wash)"
            opacity="0.3"
            clipPath={`url(#${clipId})`}
          />

          {/* Payoff Curve */}
          <path
            d={pathD}
            fill="none"
            stroke="var(--ds-accent)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            clipPath={`url(#${clipId})`}
          />

          {/* Strike marker */}
          <line
            x1={toX(strike)}
            y1={padTop}
            x2={toX(strike)}
            y2={height - padBottom}
            stroke="var(--ds-border-strong)"
            strokeDasharray="2 2"
            strokeWidth="1"
          />
          <text
            x={toX(strike)}
            y={height - padBottom + 14}
            textAnchor="middle"
            fontSize="9"
            fill="var(--ds-ink-3)"
            fontFamily="var(--ds-mono)"
          >
            K
          </text>

          {/* Breakeven marker */}
          <line
            x1={toX(breakeven)}
            y1={padTop}
            x2={toX(breakeven)}
            y2={height - padBottom}
            stroke="var(--ds-warn)"
            strokeDasharray="2 2"
            strokeWidth="1.2"
          />
          <text
            x={toX(breakeven)}
            y={padTop - 6}
            textAnchor="middle"
            fontSize="9"
            fill="var(--ds-warn)"
            fontFamily="var(--ds-mono)"
            fontWeight="600"
          >
            BE
          </text>

          {/* Targets */}
          {target1Spot ? (
            <circle
              cx={toX(target1Spot)}
              cy={toY(calculatePayoffAtExpiry(direction, target1Spot, strike, entryPremium, lotSize))}
              r="3.5"
              fill="var(--ds-bull)"
              stroke="var(--ds-surface)"
              strokeWidth="1.5"
            />
          ) : null}

          {/* Active spot vertical cursor */}
          <line
            x1={activeX}
            y1={padTop}
            x2={activeX}
            y2={height - padBottom}
            stroke="var(--ds-ink-2)"
            strokeWidth="1"
          />
          <circle
            cx={activeX}
            cy={activeY}
            r="4.5"
            fill={activePnl >= 0 ? 'var(--ds-bull)' : 'var(--ds-bear)'}
            stroke="var(--ds-surface)"
            strokeWidth="2"
          />

          {/* Axis Labels */}
          <text
            x={padLeft - 6}
            y={zeroY + 3}
            textAnchor="end"
            fontSize="9"
            fill="var(--ds-ink-3)"
            fontFamily="var(--ds-mono)"
          >
            ₹0
          </text>
          <text
            x={padLeft}
            y={height - 6}
            textAnchor="start"
            fontSize="9"
            fill="var(--ds-ink-3)"
            fontFamily="var(--ds-mono)"
          >
            ₹{minSpot}
          </text>
          <text
            x={width - padRight}
            y={height - 6}
            textAnchor="end"
            fontSize="9"
            fill="var(--ds-ink-3)"
            fontFamily="var(--ds-mono)"
          >
            ₹{maxSpot}
          </text>
        </svg>

        {/* Hover / Cursor readout pill */}
        <div className="flex items-center justify-between text-xs px-1 pt-1 border-t border-border mt-1">
          <span className="text-muted-foreground">
            {hoverSpot ? 'Simulated Spot:' : 'Spot:'}{' '}
            <strong className="font-mono text-foreground">₹{activeSpot.toLocaleString('en-IN')}</strong>
          </span>
          <span className="font-mono">
            Estimated PnL:{' '}
            <strong
              style={{
                color: activePnl >= 0 ? 'var(--ds-bull)' : 'var(--ds-bear)',
              }}
            >
              {activePnl >= 0 ? '+' : ''}₹{Math.round(activePnl).toLocaleString('en-IN')} ({activePnlPct >= 0 ? '+' : ''}
              {activePnlPct.toFixed(1)}%)
            </strong>
          </span>
        </div>
      </div>
    </div>
  );
}
