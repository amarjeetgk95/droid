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
      <h3 className="font-semibold mb-2">F&O Context</h3>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>PCR: {fno.pcr.toFixed(2)} (Vol {fno.pcr_volume.toFixed(2)})</div>
        <div>ATM IV: {fno.atm_iv?.toFixed(1)}%</div>
        <div>Put Wall: {fno.put_wall}</div>
        <div>Call Wall: {fno.call_wall}</div>
        <div>Basis: {fno.basis>0?'+':''}{fno.basis.toFixed(2)}</div>
        <div>Fut OI Δ: {fno.futures_oi_change.toFixed(1)}%</div>
        <div>Max Pain: {fno.max_pain}</div>
        <div>Positioning: {fno.futures_positioning}</div>
      </div>
    </div>
  );
}
