'use client';

/* On-demand institutional evaluators: MI, breakout, portfolio risk, contract
   validation. POSTs compute readouts only — no backend state changes, so they
   submit directly; results render as read-only sg-kv lists via useToast. */

import { useCallback, useState, type ReactNode } from 'react';
import { useToast } from '@/components/ui/toast';
import { getObj } from '@/lib/signalsNormalize';
import { badgeClass, healthTone } from '@/lib/intelDesk';
import type { InstitutionalDeskState } from '@/hooks/useIntelDesk';

type EvalState = {
  busy: boolean;
  message: string | null;
  ok: boolean | null;
  data: Record<string, unknown> | null;
};

const IDLE_EVAL: EvalState = { busy: false, message: null, ok: null, data: null };

function ResultKv({ data }: { data: Record<string, unknown> }) {
  const rows: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(data)) {
    if (value === null || value === undefined) rows.push([key, '—']);
    else if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      rows.push([key, String(value)]);
    } else if (Array.isArray(value)) rows.push([key, `${value.length} item(s)`]);
    else if (getObj(value)) rows.push([key, `${Object.keys(value as object).length} field(s)`]);
  }
  if (rows.length === 0) return <p className="sg-note">Empty result object.</p>;
  return (
    <div className="sg-kvlist">
      {rows.slice(0, 24).map(([k, v]) => (
        <div className="sg-kv" key={k}>
          <span className="l">{k.replace(/_/g, ' ')}</span>
          <span className="v">{v}</span>
        </div>
      ))}
    </div>
  );
}

function EvalShell({
  title,
  meta,
  state,
  onSubmit,
  children,
}: {
  title: string;
  meta?: string;
  state: EvalState;
  onSubmit: () => void;
  children: ReactNode;
}) {
  return (
    <section className="card" aria-label={title}>
      <div className="card-hd">
        <h2 className="card-title">{title}</h2>
        {meta ? <span className="card-meta">{meta}</span> : null}
      </div>
      <div className="card-bd flex flex-col gap-2">
        <div className="ds-filters" style={{ marginLeft: 0 }}>
          {children}
          <button type="button" className="btn btn-primary" disabled={state.busy} onClick={onSubmit}>
            {state.busy ? 'Evaluating…' : 'Evaluate'}
          </button>
        </div>
        {state.message ? (
          <p className={state.ok ? 'sg-note' : 'sg-err'}>{state.message}</p>
        ) : null}
        {state.data ? <ResultKv data={state.data} /> : null}
      </div>
    </section>
  );
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
  onChange: (v: string) => void;
  placeholder?: string;
  inputMode?: 'decimal' | 'text';
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="card-meta">{label}</span>
      <input
        className="input num"
        value={value}
        placeholder={placeholder}
        inputMode={inputMode}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export function EvaluateForms({ desk, instrument }: { desk: InstitutionalDeskState; instrument: string }) {
  const { push } = useToast();
  const [mi, setMi] = useState<EvalState>(IDLE_EVAL);
  const [brk, setBrk] = useState<EvalState>(IDLE_EVAL);
  const [risk, setRisk] = useState<EvalState>(IDLE_EVAL);
  const [contract, setContract] = useState<EvalState>(IDLE_EVAL);

  const [miSpot, setMiSpot] = useState('');
  const [miVwap, setMiVwap] = useState('');
  const [brkLevel, setBrkLevel] = useState('');
  const [brkPrice, setBrkPrice] = useState('');
  const [brkAtr, setBrkAtr] = useState('');
  const [brkClose, setBrkClose] = useState(false);
  const [brkVol, setBrkVol] = useState(false);
  const [brkMom, setBrkMom] = useState(false);
  const [riskNotional, setRiskNotional] = useState('');
  const [riskMargin, setRiskMargin] = useState('');
  const [riskSide, setRiskSide] = useState<'BUY' | 'SELL'>('BUY');
  const [ctPrice, setCtPrice] = useState('');
  const [ctQty, setCtQty] = useState('');

  const numOrUndef = (v: string): number | undefined => {
    const t = v.trim();
    if (!t) return undefined;
    const n = Number(t);
    return Number.isFinite(n) ? n : undefined;
  };

  const submitMI = useCallback(async () => {
    setMi((s) => ({ ...s, busy: true, message: null }));
    const spot = numOrUndef(miSpot);
    const vwap = numOrUndef(miVwap);
    const result = await desk.evaluateMI({
      instrument_id: instrument,
      ...(spot !== undefined ? { spot_price: spot } : {}),
      ...(vwap !== undefined ? { vwap } : {}),
      data_health: 'LIVE',
      feed_health: 'HEALTHY',
    });
    setMi({ busy: false, message: result.message, ok: result.ok, data: result.data });
    push(result.ok ? 'success' : 'error', result.message);
  }, [desk, instrument, miSpot, miVwap, push]);

  const submitBreakout = useCallback(async () => {
    const level = brkLevel.trim();
    const price = brkPrice.trim();
    if (!level || !price) {
      push('error', 'Breakout level and current price are required.');
      return;
    }
    setBrk((s) => ({ ...s, busy: true, message: null }));
    const result = await desk.evaluateBreakout({
      instrument_id: instrument,
      breakout_level: level,
      current_price: price,
      close_confirmed: brkClose,
      volume_expansion: brkVol,
      momentum_accel: brkMom,
      ...(brkAtr.trim() ? { atr: brkAtr.trim() } : {}),
      data_health: 'LIVE',
      feed_health: 'HEALTHY',
    });
    setBrk({ busy: false, message: result.message, ok: result.ok, data: result.data });
    push(result.ok ? 'success' : 'error', result.message);
  }, [desk, instrument, brkLevel, brkPrice, brkAtr, brkClose, brkVol, brkMom, push]);

  const submitRisk = useCallback(async () => {
    if (!riskNotional.trim() || !riskMargin.trim()) {
      push('error', 'Notional and margin are required for portfolio risk.');
      return;
    }
    setRisk((s) => ({ ...s, busy: true, message: null }));
    const result = await desk.evaluateRisk({
      new_order_instrument: instrument,
      new_order_notional: riskNotional.trim(),
      new_order_margin: riskMargin.trim(),
      side: riskSide,
    });
    setRisk({ busy: false, message: result.message, ok: result.ok, data: result.data });
    push(result.ok ? 'success' : 'error', result.message);
  }, [desk, instrument, riskNotional, riskMargin, riskSide, push]);

  const submitContract = useCallback(async () => {
    if (!ctPrice.trim() || !ctQty.trim()) {
      push('error', 'Price and quantity are required for contract validation.');
      return;
    }
    setContract((s) => ({ ...s, busy: true, message: null }));
    const result = await desk.validateContract(instrument, ctPrice.trim(), ctQty.trim());
    setContract({ busy: false, message: result.message, ok: result.ok, data: result.data });
    push(result.ok ? 'success' : 'error', result.message);
  }, [desk, instrument, ctPrice, ctQty, push]);

  const riskVerdict = risk.data ? String(risk.data.result ?? '') : '';
  const contractValid = contract.data ? contract.data.valid === true : null;

  return (
    <div className="flex flex-col gap-2">
      <EvalShell title="Market intelligence — evaluate" meta={instrument} state={mi} onSubmit={() => void submitMI()}>
        <TextField label="spot price" value={miSpot} onChange={setMiSpot} placeholder="optional" inputMode="decimal" />
        <TextField label="vwap" value={miVwap} onChange={setMiVwap} placeholder="optional" inputMode="decimal" />
      </EvalShell>

      <EvalShell title="Breakout — evaluate" meta={instrument} state={brk} onSubmit={() => void submitBreakout()}>
        <TextField label="breakout level *" value={brkLevel} onChange={setBrkLevel} placeholder="e.g. 25950.5" inputMode="decimal" />
        <TextField label="current price *" value={brkPrice} onChange={setBrkPrice} placeholder="e.g. 25910.2" inputMode="decimal" />
        <TextField label="atr" value={brkAtr} onChange={setBrkAtr} placeholder="optional" inputMode="decimal" />
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={brkClose} onChange={(e) => setBrkClose(e.target.checked)} />
          <span className="card-meta">close confirmed</span>
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={brkVol} onChange={(e) => setBrkVol(e.target.checked)} />
          <span className="card-meta">volume expansion</span>
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={brkMom} onChange={(e) => setBrkMom(e.target.checked)} />
          <span className="card-meta">momentum accel</span>
        </label>
      </EvalShell>

      <EvalShell title="Portfolio risk — readout" meta={instrument} state={risk} onSubmit={() => void submitRisk()}>
        <TextField label="notional *" value={riskNotional} onChange={setRiskNotional} placeholder="e.g. 1500000" inputMode="decimal" />
        <TextField label="margin *" value={riskMargin} onChange={setRiskMargin} placeholder="e.g. 180000" inputMode="decimal" />
        <span className="seg" title="Order side">
          {(['BUY', 'SELL'] as const).map((side) => (
            <button
              key={side}
              type="button"
              className="seg-btn"
              data-active={riskSide === side}
              onClick={() => setRiskSide(side)}
            >
              {side}
            </button>
          ))}
        </span>
        {riskVerdict ? (
          <span className={`badge ${badgeClass(healthTone(riskVerdict === 'PASS' ? 'VALID' : 'REJECT'))}`}>
            {riskVerdict}
          </span>
        ) : null}
      </EvalShell>

      <EvalShell title="Contract validation — readout" meta={instrument} state={contract} onSubmit={() => void submitContract()}>
        <TextField label="price *" value={ctPrice} onChange={setCtPrice} placeholder="e.g. 25950.5" inputMode="decimal" />
        <TextField label="quantity *" value={ctQty} onChange={setCtQty} placeholder="e.g. 50" inputMode="decimal" />
        {contractValid !== null ? (
          <span className={`badge ${contractValid ? 'b-bull' : 'b-bear'}`}>
            {contractValid ? 'VALID' : 'INVALID'}
          </span>
        ) : null}
      </EvalShell>
    </div>
  );
}
