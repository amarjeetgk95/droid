'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';

// ---- Types ----

type AccountData = {
  account_id: string;
  mode: 'OFF' | 'PAPER' | 'LIVE';
  consent_ok: boolean;
  disclosure_version: string;
  capital?: { investment_limit: string };
  kill_switch?: { is_killed: boolean; kill_level: string };
};

type Exposure = {
  gross_exposure: number;
  net_exposure: number;
  long_exposure: number;
  short_exposure: number;
  margin_used: number;
  by_underlying: Record<string, number>;
  by_strategy: Record<string, number>;
  greeks: { delta: number; gamma: number; theta: number; vega: number };
  open_positions: number;
};

// ---- Subcomponents ----

function ModeSwitcher({ account, onChange }: { account: AccountData | null; onChange: () => void }) {
  const [loading, setLoading] = useState(false);
  const setMode = async (mode: string) => {
    setLoading(true);
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/account/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      onChange();
    } catch (e: unknown) {
      alert((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  if (!account) return <div className="text-sm text-muted-foreground">Loading account...</div>;
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium">Mode:</span>
      <Badge variant={account.mode === 'LIVE' ? 'destructive' : account.mode === 'PAPER' ? 'secondary' : 'outline'}>{account.mode}</Badge>
      {!account.consent_ok && <Badge variant="outline" className="border-amber-500 text-amber-600">Consent Required for LIVE</Badge>}
      <div className="ml-2 flex gap-1">
        {(['OFF', 'PAPER', 'LIVE'] as const).map((m) => (
          <Button key={m} variant={account.mode === m ? 'default' : 'outline'} size="sm" disabled={loading} onClick={() => setMode(m)}>
            {m}
          </Button>
        ))}
      </div>
    </div>
  );
}

function ConsentCard({ account, onRefresh }: { account: AccountData | null; onRefresh: () => void }) {
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!ack) return alert('You must acknowledge the disclosure (no pre-checked consent per spec §4).');
    setBusy(true);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disclosure_version: account?.disclosure_version || 'v1.0-2026-08-31', acknowledged: true }),
      });
      if (!res.ok) {
        const j = await res.json();
        throw new Error(j.detail || 'Consent failed');
      }
      onRefresh();
    } catch (e: unknown) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Live Risk Disclosure & Consent — §4</CardTitle>
        <CardDescription>Required before first LIVE activation. Never pre-checked. Revoking blocks new entries immediately.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded border bg-muted/30 p-3 text-sm">
          <p className="font-medium">Risk Disclosure {account?.disclosure_version}</p>
          <p className="mt-1 text-muted-foreground">
            Algorithmic trading involves substantial risk. AI signals are advisory only. Capital protection is prioritized but losses can
            exceed expectations. You acknowledge regulatory, AI advisory, and capital-at-risk disclosures.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input id="consent-ack" type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="h-4 w-4" />
          <label htmlFor="consent-ack" className="text-sm font-medium">
            I have read and acknowledge the Risk, Regulatory, and AI Advisory Disclosures.
          </label>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={submit} disabled={busy || account?.consent_ok}>
            {account?.consent_ok ? 'Acknowledged ✓' : busy ? 'Submitting...' : 'Acknowledge & Enable LIVE'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={!account?.consent_ok}
            onClick={async () => {
              await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/consent`, { method: 'DELETE' });
              onRefresh();
            }}
          >
            Revoke Consent (blocks new entries)
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CapitalPanel({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<{ limit: string; available: string; deployed: string; reserved_pending: string; utilization_pct: string; config: Record<string, string | number> } | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [confirmNeeded, setConfirmNeeded] = useState<{ current: string; new: string } | null>(null);

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/capital`)
      .then((r) => r.json())
      .then((j) => setData(j.data))
      .catch(() => {});
  }, [refreshKey]);

  const save = async (withConfirm = false) => {
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(edit)) if (v !== '') payload[k] = isNaN(Number(v)) ? v : Number(v);
    if (Object.keys(payload).length === 0) return;
    if (withConfirm) payload.confirm = true;
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/capital`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.status === 428) {
      const j = await res.json();
      setConfirmNeeded({ current: j.detail.current, new: j.detail.new });
      return;
    }
    if (!res.ok) {
      const j = await res.json().catch(() => ({ detail: 'error' }));
      alert(JSON.stringify(j.detail));
      return;
    }
    setEdit({});
    setConfirmNeeded(null);
    // refresh
    const j2 = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/capital`).then((r) => r.json());
    setData(j2.data);
  };

  if (!data) return <div className="text-sm text-muted-foreground">Loading capital...</div>;

  const fields: [string, string][] = [
    ['investment_limit', 'Investment Limit (₹)'],
    ['max_capital_per_trade', 'Max Capital / Trade (₹)'],
    ['max_daily_loss', 'Max Daily Loss (₹)'],
    ['max_loss_per_trade', 'Max Loss / Trade (₹)'],
    ['max_open_positions', 'Max Open Positions'],
    ['max_trades_per_day', 'Max Trades / Day'],
    ['max_position_quantity', 'Max Position Quantity'],
    ['max_slippage_pct', 'Max Slippage %'],
    ['max_spread_pct', 'Max Spread %'],
    ['portfolio_gross_exposure_limit', 'Portfolio Gross Exposure (₹)'],
    ['portfolio_net_exposure_limit', 'Portfolio Net Exposure (₹)'],
    ['portfolio_margin_limit_pct', 'Portfolio Margin Limit %'],
    ['portfolio_var_limit', 'Portfolio VaR Limit (₹)'],
    ['portfolio_stress_limit', 'Portfolio Stress Limit (₹)'],
    ['portfolio_delta_limit', 'Portfolio Delta Limit'],
    ['portfolio_gamma_limit', 'Portfolio Gamma Limit'],
    ['portfolio_vega_limit', 'Portfolio Vega Limit'],
    ['underlying_concentration_pct', 'Underlying Concentration %'],
    ['strategy_concentration_pct', 'Strategy Concentration %'],
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Limit</div><div className="text-lg font-bold">₹{data.limit}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Deployed</div><div className="text-lg font-bold">₹{data.deployed}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Reserved</div><div className="text-lg font-bold">₹{data.reserved_pending}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Available</div><div className="text-lg font-bold text-emerald-600">₹{data.available}</div><div className="text-xs">{data.utilization_pct}% used</div></CardContent></Card>
      </div>
      {confirmNeeded && (
        <div className="rounded border border-amber-500 bg-amber-50 dark:bg-amber-950 p-3 text-sm">
          <p className="font-semibold">Confirm Live Risk-Setting Change — §76</p>
          <p>Current Algo Limit: ₹{confirmNeeded.current} → New Algo Limit: ₹{confirmNeeded.new}. This increases capital available to live algorithmic trading.</p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setConfirmNeeded(null)}>Cancel</Button>
            <Button size="sm" onClick={() => save(true)}>Confirm Change</Button>
          </div>
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Investment / Capital Limits — §44-45, §75</CardTitle>
          <CardDescription>Hard ceilings. Broker balance ≠ algo limit (§88.4-5). Persisted & audited. Critical changes require confirmation.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {fields.map(([key, label]) => (
            <div key={key} className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">{label}</label>
              <input
                className="h-8 rounded border px-2 text-sm"
                placeholder={String((data.config as Record<string, unknown>)[key] ?? '')}
                value={edit[key] ?? ''}
                onChange={(e) => setEdit((p) => ({ ...p, [key]: e.target.value }))}
              />
            </div>
          ))}
        </CardContent>
        <div className="px-6 pb-4">
          <Button size="sm" onClick={() => save(false)}>Save Changes</Button>
          <span className="ml-2 text-xs text-muted-foreground">Increases to Investment Limit require explicit confirm (§76)</span>
        </div>
      </Card>
      <div className="text-xs text-muted-foreground">
        Capital = Limit − Deployed − Reserved. Example: Limit ₹3000, Deployed ₹1500, Reserved ₹1000 → Available ₹500. A ₹600 trade is rejected (§45).
      </div>
    </div>
  );
}

function PortfolioRiskView({ refreshKey }: { refreshKey: number }) {
  const [exp, setExp] = useState<Exposure | null>(null);
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/portfolio/exposure`)
      .then((r) => r.json())
      .then((j) => setExp(j.data))
      .catch(() => {});
  }, [refreshKey]);
  if (!exp) return <div className="text-sm text-muted-foreground">Loading exposure...</div>;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Gross Exposure</div><div className="font-bold">₹{exp.gross_exposure.toLocaleString()}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Net Exposure</div><div className="font-bold">₹{exp.net_exposure.toLocaleString()}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Long / Short</div><div className="text-sm">L ₹{exp.long_exposure.toLocaleString()} / S ₹{exp.short_exposure.toLocaleString()}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Margin Used</div><div className="font-bold">₹{exp.margin_used.toLocaleString()}</div></CardContent></Card>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="pt-4"><div className="text-xs">Δ {exp.greeks.delta.toFixed(2)}</div><div className="text-xs">Γ {exp.greeks.gamma.toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs">Θ {exp.greeks.theta.toFixed(2)}</div><div className="text-xs">Vega {exp.greeks.vega.toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Open Positions</div><div className="font-bold">{exp.open_positions}</div></CardContent></Card>
        <Card><CardContent className="pt-4"><div className="text-xs text-muted-foreground">Concentration</div><div className="text-xs max-h-20 overflow-auto">{Object.entries(exp.by_underlying).map(([k, v]) => <div key={k}>{k}: ₹{v.toLocaleString()}</div>)}</div></CardContent></Card>
      </div>
      <div className="text-xs text-muted-foreground">Greeks & concentration are portfolio-aware across strategies/instruments/expiries (§38-39). Do not assume delta hedged = risk-free (gamma/vega still checked).</div>
    </div>
  );
}

function OrdersPanel({ refreshKey }: { refreshKey: number }) {
  const [orders, setOrders] = useState<Record<string, unknown>[]>([]);
  const [form, setForm] = useState({ symbol: 'NIFTY', side: 'BUY', quantity: '75', price: '180', strategy_id: 'strat-1' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/orders?limit=20`)
      .then((r) => r.json())
      .then((j) => setOrders(j.data || []))
      .catch(() => {});
  };
  useEffect(load, [refreshKey]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: form.symbol,
          side: form.side,
          quantity: Number(form.quantity),
          price: Number(form.price),
          strategy_id: form.strategy_id,
          instrument_id: form.symbol,
        }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail));
      load();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader><CardTitle className="text-base">Execution — Place Order (Trade → Portfolio → Safety → Idempotent)</CardTitle><CardDescription>Every logical order uses UUID client_order_id — unchanged across retries. Blind resend on timeout is prohibited (§49-51).</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <input className="h-8 rounded border px-2 text-sm" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} placeholder="Symbol" />
            <select className="h-8 rounded border px-2 text-sm" value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
              <option>BUY</option><option>SELL</option>
            </select>
            <input className="h-8 rounded border px-2 text-sm" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} placeholder="Qty" />
            <input className="h-8 rounded border px-2 text-sm" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price" />
            <input className="h-8 rounded border px-2 text-sm" value={form.strategy_id} onChange={(e) => setForm({ ...form, strategy_id: e.target.value })} placeholder="Strategy ID" />
          </div>
          <Button size="sm" onClick={submit} disabled={busy}>{busy ? 'Submitting…' : 'Submit (Paper)'}</Button>
          {error && <div className="rounded bg-destructive/10 p-2 text-xs text-destructive">{error}</div>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Recent Orders (account-isolated)</CardTitle></CardHeader>
        <CardContent>
          <div className="max-h-64 overflow-auto rounded border">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted"><tr><th className="p-2 text-left">Client ID</th><th className="p-2">Symbol</th><th className="p-2">Side</th><th className="p-2">Qty</th><th className="p-2">Status</th><th className="p-2">Fill</th></tr></thead>
              <tbody>
                {orders.length === 0 ? <tr><td colSpan={6} className="p-4 text-center text-muted-foreground">No orders yet</td></tr> :
                  orders.map((o: Record<string, unknown>) => (
                    <tr key={String(o.client_order_id)} className="border-t">
                      <td className="p-2 font-mono text-[11px]">{String(o.client_order_id).slice(0, 8)}…</td>
                      <td className="p-2 text-center">{String(o.symbol)}</td>
                      <td className="p-2 text-center">{String(o.side)}</td>
                      <td className="p-2 text-center">{String(o.quantity)}</td>
                      <td className="p-2 text-center"><Badge variant={o.status === 'FILLED' ? 'default' : o.status === 'REJECTED' ? 'destructive' : 'secondary'}>{String(o.status)}</Badge></td>
                      <td className="p-2 text-center">{String(o.fill_price ?? '-')}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PositionsPanel({ refreshKey }: { refreshKey: number }) {
  const [positions, setPositions] = useState<Record<string, unknown>[]>([]);
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/positions?is_open=true`)
      .then((r) => r.json())
      .then((j) => setPositions(j.data || []))
      .catch(() => {});
  }, [refreshKey]);
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Positions — Actual Filled Composition (§18, §62)</CardTitle><CardDescription>Multi-leg spreads shown by actual current composition, not intended.</CardDescription></CardHeader>
      <CardContent>
        {positions.length === 0 ? <div className="text-sm text-muted-foreground">No open positions. Place an order to create one.</div> : (
          <div className="overflow-auto rounded border">
            <table className="w-full text-xs">
              <thead className="bg-muted"><tr><th className="p-2 text-left">ID</th><th className="p-2">Symbol</th><th className="p-2">Side</th><th className="p-2">Qty</th><th className="p-2">Avg</th><th className="p-2">LTP</th><th className="p-2">uPnL</th><th className="p-2">Exit State</th></tr></thead>
              <tbody>
                {positions.map((p: Record<string, unknown>) => (
                  <tr key={String(p.position_id)} className="border-t">
                    <td className="p-2 font-mono">{String(p.position_id)}</td>
                    <td className="p-2 text-center">{String(p.symbol)}</td>
                    <td className="p-2 text-center">{String(p.side)}</td>
                    <td className="p-2 text-center">{String(p.quantity)}</td>
                    <td className="p-2 text-center">{String(p.average_entry ?? '-')}</td>
                    <td className="p-2 text-center">{String(p.current_price ?? '-')}</td>
                    <td className="p-2 text-center">{String(p.unrealized_pnl ?? '-')}</td>
                    <td className="p-2 text-center"><Badge variant={String(p.exit_state) === 'ORPHANED_ALERT' ? 'destructive' : 'outline'}>{String(p.exit_state)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StrategyPanel() {
  const [list, setList] = useState<Record<string, unknown>[]>([]);
  const [form, setForm] = useState({ strategy_id: 'momentum-breakout', name: 'Momentum Breakout', ai_mode: 'AI_OPTIONAL', target_delta: '0.6' });
  const load = () => { fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/strategies`).then((r) => r.json()).then((j) => setList(j.data || [])).catch(() => {}); };
  useEffect(() => { load(); }, []);
  const create = async () => {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/strategies`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy_id: form.strategy_id, name: form.name, ai_mode: form.ai_mode, target_delta: Number(form.target_delta), weights: { technical: 40, mtf: 20, fno: 15, regime: 10, ai: 10, event_risk: 5 } }),
    });
    if (!res.ok) alert(await res.text());
    else load();
  };
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader><CardTitle className="text-base">Strategy Configuration — Versioned & Rollback-Capable (§29-30)</CardTitle><CardDescription>Never mutate in place. Promotion: New Config → Walk-Forward Backtest → Paper → Canary → Live. Material changes retain last-known-good.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <input className="h-8 rounded border px-2 text-sm" value={form.strategy_id} onChange={(e) => setForm({ ...form, strategy_id: e.target.value })} placeholder="strategy_id" />
            <input className="h-8 rounded border px-2 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" />
            <select className="h-8 rounded border px-2 text-sm" value={form.ai_mode} onChange={(e) => setForm({ ...form, ai_mode: e.target.value })}><option>AI_REQUIRED</option><option>AI_OPTIONAL</option><option>AI_DISABLED</option></select>
            <input className="h-8 rounded border px-2 text-sm" value={form.target_delta} onChange={(e) => setForm({ ...form, target_delta: e.target.value })} placeholder="Target Δ e.g. 0.60" />
          </div>
          <Button size="sm" onClick={create}>Create Versioned Config</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Strategies (account-isolated)</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2 max-h-64 overflow-auto">
            {list.length === 0 ? <div className="text-sm text-muted-foreground">No strategies — create one above.</div> :
              list.map((s: Record<string, unknown>) => (
                <div key={String(s.strategy_id) + String(s.config_version)} className="flex items-center justify-between rounded border p-2 text-sm">
                  <div><span className="font-mono font-medium">{String(s.strategy_id)}</span> v{String(s.config_version)} — {String(s.name)} <Badge variant="outline">{String(s.ai_mode)}</Badge> <Badge>{String(s.status)}</Badge></div>
                </div>
              ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function AIGovernancePanel() {
  const [drift, setDrift] = useState<Record<string, unknown> | null>(null);
  const [models, setModels] = useState<Record<string, unknown>[]>([]);
  const load = () => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/ai/drift`).then((r) => r.json()).then((j) => setDrift(j.data)).catch(() => {});
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/ai/models`).then((r) => r.json()).then((j) => setModels(j.data || [])).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader><CardTitle className="text-base">AI Governance — Model Versioning, Shadow/Canary, Drift, Rollback (§21-24)</CardTitle><CardDescription>Every AI decision records provider/model/prompt/config/timestamp/snapshot (§21). AI never calls OrderManager/BrokerAdapter (§20).</CardDescription></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="rounded border bg-muted/30 p-2">
            <div className="font-medium">Drift State: {String(drift?.drift_state ?? '—')}</div>
            <div className="text-xs text-muted-foreground">{drift ? JSON.stringify(drift, null, 2).slice(0, 400) : 'Loading...'}</div>
          </div>
          <div className="text-xs">Models: {models.length === 0 ? 'none registered (shadow before live §22)' : models.map((m: Record<string, unknown>) => `${String(m.key)} [${String(m.status)}]`).join(', ')}</div>
        </CardContent>
      </Card>
    </div>
  );
}

function MonitoringPanel({ refreshKey }: { refreshKey: number }) {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [audit, setAudit] = useState<Record<string, unknown>[]>([]);
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/health`).then((r) => r.json()).then((j) => setHealth(j.data)).catch(() => {});
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/audit?limit=10`).then((r) => r.json()).then((j) => setAudit(j.data || [])).catch(() => {});
  }, [refreshKey]);
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader><CardTitle className="text-base">Observability & SLOs — §68-69</CardTitle><CardDescription>Data freshness, clock drift, latencies, reject/timeout rates, reconciliation, orphaned alerts — each with WARNING/CRITICAL/RECOVERY thresholds. Critical fails closed.</CardDescription></CardHeader>
        <CardContent className="text-sm">
          <div className="rounded bg-muted p-2 font-mono text-xs overflow-auto max-h-40">{health ? JSON.stringify(health, null, 2) : 'Loading health…'}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Audit Tail (append-only, tamper-evident — §70)</CardTitle><CardDescription>Why entered/rejected/exit, portfolio exposure, model identity — for every material decision.</CardDescription></CardHeader>
        <CardContent>
          <div className="max-h-64 overflow-auto rounded border">
            <table className="w-full text-xs"><thead className="bg-muted"><tr><th className="p-2 text-left">Time</th><th className="p-2">Event</th><th className="p-2">Symbol</th><th className="p-2">Trade Risk</th><th className="p-2">Portfolio Risk</th></tr></thead>
              <tbody>
                {audit.length === 0 ? <tr><td colSpan={5} className="p-4 text-center text-muted-foreground">No audit events yet — place an order to generate one.</td></tr> :
                  audit.map((a: Record<string, unknown>, i: number) => (
                    <tr key={i} className="border-t"><td className="p-2 font-mono text-[11px]">{String(a.timestamp ?? '').slice(11, 19)}</td><td className="p-2">{String(a.event_type)}</td><td className="p-2">{String(a.symbol ?? '-')}</td><td className="p-2">{String(a.trade_risk_result ?? '-')}</td><td className="p-2">{String(a.portfolio_risk_result ?? '-')}</td></tr>
                  ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ControlsPanel({ onRefresh }: { onRefresh: () => void }) {
  const [busy, setBusy] = useState(false);
  const act = async (url: string, body?: Record<string, unknown>) => {
    setBusy(true);
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
      const j = await res.json().catch(() => ({}));
      alert(JSON.stringify(j.data ?? j, null, 2).slice(0, 800));
      onRefresh();
    } catch (e: unknown) { alert((e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <Card className="border-destructive/30">
        <CardHeader><CardTitle className="text-base text-destructive">Kill Switch & Emergency Controls — §79-80</CardTitle><CardDescription>STOP NEW ENTRIES / CANCEL ENTRY ORDERS / EXIT ALL POSITIONS / FULL EXECUTION STOP — distinct internal states.</CardDescription></CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button variant="destructive" size="sm" disabled={busy} onClick={() => act(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/kill-switch`, { kill_level: 'STOP_NEW_ENTRIES', reason: 'manual' })}>Stop New Entries</Button>
          <Button variant="destructive" size="sm" disabled={busy} onClick={() => act(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/kill-switch`, { kill_level: 'FULL_EXECUTION_STOP', reason: 'emergency' })}>Full Execution Stop</Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => act(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/kill-switch`, { kill_level: 'NONE' })}>Clear Kill Switch</Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => act(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/positions/exit-all`)}>Exit All (Emergency)</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Reconciliation & Recovery</CardTitle><CardDescription>§71-72: Load → Query broker → Reconcile → Rebuild → Validate → Resume. Never resume LIVE from memory alone.</CardDescription></CardHeader>
        <CardContent className="flex gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => act(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/reconciliation/run`)}>Run Reconciliation</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => act(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/recovery/restart`)}>Restart Recovery Check</Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ---- Main Page ----

export default function AlgoTradingPage() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const bump = () => setRefreshKey((k) => k + 1);

  const loadAccount = () => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com'}/api/v1/algo/account`)
      .then((r) => {
        if (!r.ok) throw new Error('auth required');
        return r.json();
      })
      .then((j) => setAccount(j.data))
      .catch(() => setAccount({ account_id: 'local', mode: 'OFF', consent_ok: false, disclosure_version: 'v1.0-2026-08-31' }));
  };
  useEffect(loadAccount, []);

  return (
    <div className="space-y-4">
      {/* Header — Operating Philosophy */}
      <Card className="border-primary/30 bg-primary/[0.03]">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg">Algo Trading — Event-Driven, Portfolio-Aware</CardTitle>
              <CardDescription>Capital Protection → Position → Portfolio → Data Integrity → Broker Compliance → Idempotent Execution → Execution Quality → Strategy → AI Preference (§1). Default under uncertainty: NO_NEW_ENTRY.</CardDescription>
            </div>
            <Badge variant="outline" className="hidden md:inline-flex">§1-§88 Spec V6 Final</Badge>
          </div>
          <div className="pt-2">
            <ModeSwitcher account={account} onChange={() => { loadAccount(); bump(); }} />
          </div>
        </CardHeader>
      </Card>

      <Tabs defaultValue="capital" className="w-full">
        <div className="overflow-x-auto">
          <TabsList className="w-full justify-start flex-wrap h-auto">
            <TabsTrigger value="capital">Investment / Capital</TabsTrigger>
            <TabsTrigger value="portfolio">Portfolio Risk</TabsTrigger>
            <TabsTrigger value="execution">Execution</TabsTrigger>
            <TabsTrigger value="positions">Positions</TabsTrigger>
            <TabsTrigger value="strategy">Strategy</TabsTrigger>
            <TabsTrigger value="ai">AI / Research</TabsTrigger>
            <TabsTrigger value="monitoring">Monitoring</TabsTrigger>
            <TabsTrigger value="controls">Controls</TabsTrigger>
            <TabsTrigger value="consent">Consent</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="capital" className="space-y-4 pt-2">
          <CapitalPanel refreshKey={refreshKey} />
        </TabsContent>

        <TabsContent value="portfolio" className="space-y-4 pt-2">
          <PortfolioRiskView refreshKey={refreshKey} />
          <Card>
            <CardHeader><CardTitle className="text-sm">Hardening Notes — §35-43</CardTitle></CardHeader>
            <CardContent className="text-xs space-y-1 text-muted-foreground">
              <p>• Correlation confidence LOW → conservative fallback; missing data never = zero risk (§36, §88.33).</p>
              <p>• VaR/stress applied where model/data quality permits; approval requires projected portfolio risk within limits (§41).</p>
              <p>• Concentration, margin, Greeks checked continuously; breach → REJECT (§39-40).</p>
              <p>• Cross-strategy NIFTY exposure evaluated even when each trade passes individually (§37).</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="execution" className="pt-2">
          <OrdersPanel refreshKey={refreshKey} />
          <div className="mt-3 text-xs text-muted-foreground">PAPER and LIVE share strategy/risk/position/exit/reconciliation/audit — only destination changes: PAPER→Simulator, LIVE→Broker (§73). Simulator models slippage/partial fills/latency/rejections/fees.</div>
        </TabsContent>

        <TabsContent value="positions" className="pt-2">
          <PositionsPanel refreshKey={refreshKey} />
        </TabsContent>

        <TabsContent value="strategy" className="pt-2">
          <StrategyPanel />
        </TabsContent>

        <TabsContent value="ai" className="pt-2">
          <AIGovernancePanel />
          <Card className="mt-3">
            <CardHeader><CardTitle className="text-sm">Authority Hierarchy — §87</CardTitle></CardHeader>
            <CardContent className="text-xs font-mono leading-relaxed text-muted-foreground">
              Market Data → Data Health → Technical/F&O/Regime → AI Research → Signal Fusion → Trigger → Position Sizing → Trade Risk → Portfolio Risk → Execution Safety → Idempotency → Order Manager → Broker
              <br /><span className="text-foreground font-medium">AI = Research; Strategy = Signal; Portfolio Risk = Aggregate Exposure Permission; Broker = Confirmation.</span>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="monitoring" className="pt-2">
          <MonitoringPanel refreshKey={refreshKey} />
        </TabsContent>

        <TabsContent value="controls" className="pt-2">
          <ControlsPanel onRefresh={bump} />
          <Card>
            <CardHeader><CardTitle className="text-sm">Final Non-Bypassable Rules — §88 (excerpt)</CardTitle></CardHeader>
            <CardContent className="text-xs leading-relaxed text-muted-foreground">
              AI cannot place orders · Strategy cannot bypass Trade Risk · Trade Risk cannot bypass Portfolio Risk · Broker balance ≠ algo limit · Frontend never authoritative ·
              Decimal for money · DB is financial authority · UUID per logical order, immutable across retries · Timeouts require reconciliation · Stale data blocks entries · Emergency exits prioritize risk reduction → ORPHANED_ALERT on failure · Missing data ≠ zero risk · Risk engine fails closed · Every decision auditable.
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="consent" className="pt-2">
          <ConsentCard account={account} onRefresh={loadAccount} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
