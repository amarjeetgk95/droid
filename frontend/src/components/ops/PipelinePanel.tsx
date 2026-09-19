'use client';

/* Pipeline tab: on-demand observe tools (state capture, trigger evaluate,
   staleness check, pricing calculate) with minimal forms, the execution
   order list (list-only — transitions are disabled against the shared dev
   backend), and timeseries pipeline stats. */

import { useState } from 'react';
import { useToast } from '@/components/ui/toast';
import type { OpsActionResult, OpsConsole } from '@/hooks/useOpsConsole';
import { getObj, pickStr } from '@/lib/signalsNormalize';
import { TRIGGER_TYPES, fmtCell, parseNumField, toneForStatus } from '@/lib/opsDesk';
import { Field, KvList, OpsCard, ToneBadge, ToolResult } from './OpsBits';

function useTool(run: (...args: never[]) => Promise<OpsActionResult>) {
  const { push } = useToast();
  const [result, setResult] = useState<OpsActionResult | null>(null);
  const [running, setRunning] = useState(false);
  const execute = async (...args: never[]) => {
    setRunning(true);
    try {
      const next = await run(...args);
      setResult(next);
      push(next.ok ? 'success' : 'error', next.message);
    } finally {
      setRunning(false);
    }
  };
  const note = (message: string) => setResult({ ok: false, message });
  return { result, running, execute, note };
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  inputMode,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  inputMode?: 'decimal' | 'text';
}) {
  return (
    <Field label={label}>
      <input
        className="input mono"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        inputMode={inputMode}
      />
    </Field>
  );
}

export function PipelinePanel({ ops }: { ops: OpsConsole }) {
  const capture = useTool(ops.captureState as (...args: never[]) => Promise<OpsActionResult>);
  const trigger = useTool(ops.evaluateTrigger as (...args: never[]) => Promise<OpsActionResult>);
  const stale = useTool(ops.checkStaleness as (...args: never[]) => Promise<OpsActionResult>);
  const pricing = useTool(ops.calculatePricing as (...args: never[]) => Promise<OpsActionResult>);

  const [capSymbol, setCapSymbol] = useState('NIFTY');
  const [capPrice, setCapPrice] = useState('');
  const [capAtr, setCapAtr] = useState('');
  const [capRegime, setCapRegime] = useState('UNKNOWN');

  const [trigSymbol, setTrigSymbol] = useState('NIFTY');
  const [trigType, setTrigType] = useState<string>(TRIGGER_TYPES[0]);
  const [trigPrice, setTrigPrice] = useState('');
  const [trigSig, setTrigSig] = useState('');

  const [stalePrice, setStalePrice] = useState('');
  const [staleAtr, setStaleAtr] = useState('');
  const [staleVersion, setStaleVersion] = useState('1');
  const [staleCurrent, setStaleCurrent] = useState('');

  const [pxBias, setPxBias] = useState('BUY');
  const [pxCurrent, setPxCurrent] = useState('');
  const [pxP10, setPxP10] = useState('');
  const [pxP50, setPxP50] = useState('');
  const [pxP90, setPxP90] = useState('');

  const store = getObj(ops.pipelineStats?.timeseries_store);
  const writer = getObj(ops.pipelineStats?.write_pipeline);

  return (
    <div className="flex flex-col gap-3">
      {ops.infraErrors.orders ? <p className="sg-err">{ops.infraErrors.orders}</p> : null}
      {ops.infraErrors.pipeline ? <p className="sg-err">{ops.infraErrors.pipeline}</p> : null}

      <OpsCard title="State capture" meta="POST /api/v1/pipeline/state/capture">
        <div className="grid gap-2 sm:grid-cols-2">
          <TextField label="Symbol" value={capSymbol} onChange={(v) => setCapSymbol(v.toUpperCase())} placeholder="NIFTY" />
          <TextField label="Regime" value={capRegime} onChange={(v) => setCapRegime(v.toUpperCase())} placeholder="UNKNOWN" />
          <TextField label="Current price (live)" value={capPrice} onChange={setCapPrice} placeholder="e.g. 23346.4" inputMode="decimal" />
          <TextField label="ATR (live)" value={capAtr} onChange={setCapAtr} placeholder="e.g. 42.5" inputMode="decimal" />
        </div>
        <p className="sg-note">Price and ATR are required live values — the backend rejects placeholders.</p>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={capture.running || ops.mutating}
            onClick={() => {
              const price = parseNumField(capPrice);
              const atr = parseNumField(capAtr);
              if (price === null || atr === null) {
                capture.note('Enter live numeric values for current price and ATR.');
                return;
              }
              if (!capSymbol.trim()) {
                capture.note('Enter a symbol first.');
                return;
              }
              void capture.execute(capSymbol.trim().toUpperCase() as never, price as never, atr as never, (capRegime.trim() || 'UNKNOWN') as never);
            }}
          >
            {capture.running ? 'Capturing…' : 'Capture state'}
          </button>
        </div>
        <ToolResult result={capture.result} />
      </OpsCard>

      <OpsCard title="Trigger evaluate" meta="POST /api/v1/pipeline/trigger/evaluate">
        <div className="grid gap-2 sm:grid-cols-2">
          <TextField label="Symbol" value={trigSymbol} onChange={(v) => setTrigSymbol(v.toUpperCase())} placeholder="NIFTY" />
          <Field label="Trigger type">
            <select className="input mono" value={trigType} onChange={(event) => setTrigType(event.target.value)}>
              {TRIGGER_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </Field>
          <TextField label="Current price (live)" value={trigPrice} onChange={setTrigPrice} placeholder="e.g. 23346.4" inputMode="decimal" />
          <TextField label="Significance (optional)" value={trigSig} onChange={setTrigSig} placeholder="e.g. 0.8" inputMode="decimal" />
        </div>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={trigger.running || ops.mutating}
            onClick={() => {
              const price = parseNumField(trigPrice);
              if (price === null || !trigSymbol.trim()) {
                trigger.note('Enter a symbol and a live numeric current price.');
                return;
              }
              void trigger.execute(trigSymbol.trim().toUpperCase() as never, trigType as never, price as never, (parseNumField(trigSig) ?? undefined) as never);
            }}
          >
            {trigger.running ? 'Evaluating…' : 'Evaluate trigger'}
          </button>
        </div>
        <ToolResult result={trigger.result} />
      </OpsCard>

      <OpsCard title="Staleness check" meta="POST /api/v1/pipeline/staleness/check">
        <div className="grid gap-2 sm:grid-cols-2">
          <TextField label="Trigger price" value={stalePrice} onChange={setStalePrice} placeholder="e.g. 23300" inputMode="decimal" />
          <TextField label="Trigger ATR" value={staleAtr} onChange={setStaleAtr} placeholder="e.g. 42.5" inputMode="decimal" />
          <TextField label="State version" value={staleVersion} onChange={setStaleVersion} placeholder="1" inputMode="decimal" />
          <TextField label="Current price" value={staleCurrent} onChange={setStaleCurrent} placeholder="e.g. 23346.4" inputMode="decimal" />
        </div>
        <p className="sg-note">Checked against the live trigger timestamp (now) at versioned state.</p>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={stale.running || ops.mutating}
            onClick={() => {
              const payload = {
                trigger_price: parseNumField(stalePrice),
                trigger_atr: parseNumField(staleAtr),
                trigger_timestamp: new Date().toISOString(),
                trigger_state_version: parseNumField(staleVersion),
                current_price: parseNumField(staleCurrent),
              };
              if (Object.values(payload).some((v) => v === null)) {
                stale.note('All four staleness fields require numeric values.');
                return;
              }
              void stale.execute(payload as never);
            }}
          >
            {stale.running ? 'Checking…' : 'Check staleness'}
          </button>
        </div>
        <ToolResult result={stale.result} />
      </OpsCard>

      <OpsCard title="Pricing calculate" meta="POST /api/v1/pipeline/pricing/calculate">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Bias">
            <select className="input mono" value={pxBias} onChange={(event) => setPxBias(event.target.value)}>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </Field>
          <TextField label="Current price" value={pxCurrent} onChange={setPxCurrent} placeholder="e.g. 23346.4" inputMode="decimal" />
          <TextField label="P10" value={pxP10} onChange={setPxP10} placeholder="lower quantile" inputMode="decimal" />
          <TextField label="P50" value={pxP50} onChange={setPxP50} placeholder="median" inputMode="decimal" />
          <TextField label="P90" value={pxP90} onChange={setPxP90} placeholder="upper quantile" inputMode="decimal" />
        </div>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={pricing.running || ops.mutating}
            onClick={() => {
              const payload = {
                bias: pxBias,
                current_price: parseNumField(pxCurrent),
                p10: parseNumField(pxP10),
                p50: parseNumField(pxP50),
                p90: parseNumField(pxP90),
              };
              if (Object.values(payload).some((v) => v === null)) {
                pricing.note('Bias plus numeric current price, P10, P50 and P90 are required.');
                return;
              }
              void pricing.execute(payload as never);
            }}
          >
            {pricing.running ? 'Calculating…' : 'Calculate pricing'}
          </button>
        </div>
        <ToolResult result={pricing.result} />
      </OpsCard>

      <OpsCard
        title="Execution orders"
        meta={`GET /api/v1/pipeline/execution/orders · ${ops.orders.length} open`}
        action={
          <button type="button" className="btn btn-ic" disabled={ops.infraRefreshing} onClick={() => void ops.refreshInfra()}>
            {ops.infraRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        }
      >
        <p className="sg-note">
          List-only: order transitions mutate the shared execution state machine, so they are disabled
          against the shared dev backend.
        </p>
        {ops.infraLoading ? (
          <p className="sg-empty">Loading execution orders…</p>
        ) : ops.orders.length === 0 ? (
          <p className="sg-empty">No execution orders recorded.</p>
        ) : (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {ops.orders.map((raw, index) => {
                  const o = getObj(raw) ?? {};
                  const id = pickStr(o, 'order_id', 'id') ?? `order-${index}`;
                  const state = pickStr(o, 'state', 'status') ?? '—';
                  return (
                    <tr key={id}>
                      <td>
                        <span className="sg-sym">{id}</span>
                      </td>
                      <td>{pickStr(o, 'symbol') ?? '—'}</td>
                      <td>{pickStr(o, 'side') ?? '—'}</td>
                      <td className="num">{fmtCell(o.quantity ?? o.qty)}</td>
                      <td>
                        <ToneBadge tone={toneForStatus(state)} label={state} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </OpsCard>

      <OpsCard title="Timeseries pipeline" meta="GET /api/v1/timeseries/pipeline-stats">
        {ops.pipelineStats ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="card-meta">timeseries store</p>
              <KvList obj={store} limit={10} />
            </div>
            <div>
              <p className="card-meta">write pipeline</p>
              <KvList obj={writer} limit={10} />
            </div>
          </div>
        ) : (
          <p className="sg-empty">No pipeline stats reported.</p>
        )}
      </OpsCard>
    </div>
  );
}
