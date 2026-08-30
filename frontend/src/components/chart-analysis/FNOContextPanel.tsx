'use client';
export function FNOContextPanel({ data }: { data: any }) {
  const fno = data?.fno;
  if (!fno) return null;
  if (!fno.available) {
    return (
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="font-semibold mb-2">F&O Context</h3>
        <p className="text-sm text-muted-foreground">F&O context unavailable for this instrument. Technical and market-data analysis remains available.</p>
        <p className="text-xs text-muted-foreground">{fno.reason}</p>
      </div>
    );
  }
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">F&O Context — separate engine</h3>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>Spot: {fno.spot?.toFixed(2) ?? '—'} • Futures {fno.futures_price?.toFixed(2) ?? '—'}</div>
        <div>Basis: {fno.futures_basis?.toFixed(2) ?? fno.basis?.toFixed(2) ?? '—'} {fno.futures_basis_percent && `(${fno.futures_basis_percent.toFixed(3)}%)`}</div>
        <div>Futures OI: {fno.futures_oi?.toLocaleString() ?? '—'} {fno.futures_oi_change != null && `Δ ${fno.futures_oi_change.toFixed(1)}%`}</div>
        <div>Positioning: {fno.futures_positioning} {fno.buildup_strength && `(${fno.buildup_strength})`}</div>
        <div>PCR: {fno.pcr?.toFixed(2) ?? '—'} (Vol {fno.pcr_volume?.toFixed(2) ?? '—'})</div>
        <div>ATM IV: {fno.atm_iv?.toFixed(1)}% {fno.iv_rank_proxy != null && `• IV Rank ~${fno.iv_rank_proxy.toFixed(0)}%`}</div>
        <div>Put Wall: {fno.put_wall ?? '—'} {fno.key_put_strikes?.[0] && `(OI ${fno.key_put_strikes[0].oi.toLocaleString()})`}</div>
        <div>Call Wall: {fno.call_wall ?? '—'} {fno.key_call_strikes?.[0] && `(OI ${fno.key_call_strikes[0].oi.toLocaleString()})`}</div>
        <div>Max Pain: {fno.max_pain ?? '—'} • Distance to expiry {fno.distance_to_expiry_days}d</div>
        <div>Rollover: {fno.rollover_percent?.toFixed(1)}% ({fno.rollover_pace}) • Curve {fno.term_structure_curve}</div>
        <div>ATM premiums: C {fno.atm_call_premium ?? '—'} / P {fno.atm_put_premium ?? '—'}</div>
        <div>Greeks (ATM): Δ {(fno.atm_greeks?.call?.delta ?? fno.atm_greeks?.put?.delta ?? '—')?.toString().slice(0,6)}</div>
      </div>
      {fno.near_expiry_guard_active && <p className="text-xs text-amber-600 mt-2">Near expiry (≤3d) — rollover guard active, no Section 8 hard stop; assessment continues with daily/weekly lens.</p>}
      <p className="text-xs text-muted-foreground mt-2">F&O engine separate from technical analysis. Values unavailable for non-F&O instruments (e.g., BTC).</p>
    </div>
  );
}
