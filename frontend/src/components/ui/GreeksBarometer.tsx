'use client';

export interface GreeksProps {
  delta?: number | null;
  theta?: number | null;
  gamma?: number | null;
  vega?: number | null;
  iv?: number | null;
  lotSize?: number;
  quantity?: number;
  className?: string;
}

export function GreeksBarometer({
  delta = null,
  theta = null,
  gamma = null,
  vega = null,
  iv = null,
  lotSize = 25,
  quantity,
  className = '',
}: GreeksProps) {
  const d = typeof delta === 'number' && Number.isFinite(delta) ? delta : null;
  const th = typeof theta === 'number' && Number.isFinite(theta) ? theta : null;
  const g = typeof gamma === 'number' && Number.isFinite(gamma) ? gamma : null;
  const v = typeof vega === 'number' && Number.isFinite(vega) ? vega : null;
  const ivPct = typeof iv === 'number' && Number.isFinite(iv) ? iv : null;

  const totalQty = quantity ?? lotSize;
  const rupeeThetaHr = th !== null ? Math.abs(th * totalQty) : null;
  const rupeeVega1Pct = v !== null ? Math.abs(v * totalQty) : null;

  // Delta position (-1.0 to +1.0 mapped to 0% - 100%)
  const deltaClamped = d !== null ? Math.max(-1, Math.min(1, d)) : 0;
  const deltaPct = ((deltaClamped + 1) / 2) * 100;

  return (
    <div className={`ds-card p-3 flex flex-col gap-2.5 ${className}`}>
      <div className="flex items-center justify-between text-xs border-b border-border pb-1.5">
        <span className="font-semibold">Option Greeks &amp; Microstructure</span>
        {ivPct !== null ? (
          <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-surface border border-border">
            IV: <strong>{ivPct.toFixed(1)}%</strong>
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        {/* Delta Gauge */}
        <div className="flex flex-col gap-1 p-2 rounded bg-surface-subtle border border-border-subtle">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground font-mono">Delta (Δ)</span>
            <strong
              className="font-mono"
              style={{
                color: (d ?? 0) > 0 ? 'var(--ds-bull)' : (d ?? 0) < 0 ? 'var(--ds-bear)' : 'var(--ds-ink)',
              }}
            >
              {d !== null ? `${d > 0 ? '+' : ''}${d.toFixed(3)}` : '—'}
            </strong>
          </div>
          {/* Visual Delta Track */}
          <div className="relative h-1.5 w-full bg-border rounded-full overflow-hidden mt-0.5">
            <div
              className="absolute top-0 bottom-0 w-1 bg-ink rounded-full"
              style={{ left: '50%', transform: 'translateX(-50%)' }}
            />
            <div
              className="absolute top-0 bottom-0 h-full rounded-full transition-all duration-150"
              style={{
                left: d && d < 0 ? `${deltaPct}%` : '50%',
                width: `${Math.abs(deltaClamped) * 50}%`,
                backgroundColor: (d ?? 0) >= 0 ? 'var(--ds-bull)' : 'var(--ds-bear)',
              }}
            />
          </div>
        </div>

        {/* Theta Decay */}
        <div className="flex flex-col gap-1 p-2 rounded bg-surface-subtle border border-border-subtle">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground font-mono">Theta (Θ)</span>
            <strong className="font-mono" style={{ color: 'var(--ds-bear)' }}>
              {th !== null ? `${th.toFixed(2)} pts` : '—'}
            </strong>
          </div>
          <span className="text-2xs text-muted-foreground font-mono">
            {rupeeThetaHr !== null ? `≈ -₹${Math.round(rupeeThetaHr)}/lot decay` : 'Time erosion'}
          </span>
        </div>

        {/* Gamma Risk */}
        <div className="flex flex-col gap-1 p-2 rounded bg-surface-subtle border border-border-subtle">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground font-mono">Gamma (Γ)</span>
            <strong className="font-mono text-foreground">
              {g !== null ? g.toFixed(4) : '—'}
            </strong>
          </div>
          <span className="text-2xs text-muted-foreground font-mono">
            {g !== null ? `${(g * 100).toFixed(2)} Δ / 100pts` : 'Acceleration'}
          </span>
        </div>

        {/* Vega Exposure */}
        <div className="flex flex-col gap-1 p-2 rounded bg-surface-subtle border border-border-subtle">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground font-mono">Vega (ν)</span>
            <strong className="font-mono text-foreground">
              {v !== null ? `${v.toFixed(2)} pts` : '—'}
            </strong>
          </div>
          <span className="text-2xs text-muted-foreground font-mono">
            {rupeeVega1Pct !== null ? `±₹${Math.round(rupeeVega1Pct)} per 1% IV` : 'Volatility impact'}
          </span>
        </div>
      </div>
    </div>
  );
}
