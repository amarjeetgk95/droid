'use client';
export function InstrumentHeader({ data }: { data: any }) {
  if (!data) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-4 flex flex-wrap items-center gap-4">
      <div>
        <h2 className="text-xl font-bold">{data.symbol}</h2>
        <p className="text-sm text-muted-foreground">{data.display_name} • {data.exchange} • {data.asset_class}</p>
      </div>
      <div className="ml-auto flex gap-4 text-sm">
        <span className="px-2 py-1 bg-muted rounded">{data.freshness || 'LIVE'}</span>
        <span className="text-muted-foreground">Data: {data.data_timestamp ? new Date(data.data_timestamp).toLocaleTimeString() : '—'}</span>
        <span className={`px-2 py-1 rounded ${data.market_status==='OPEN'?'bg-green-100 text-green-800':'bg-muted'}`}>{data.market_status}</span>
      </div>
    </div>
  );
}
