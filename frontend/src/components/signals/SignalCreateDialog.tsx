'use client';

/* Manual signal creation, kept out of the desk surface: the old always-visible
   10-field form rendered unstyled inputs and made the page look like a debug
   panel. A dialog keeps the desk clean while preserving the capability. */

import { useCallback, useState } from 'react';
import { ShieldCheck, Sparkles } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { api } from '@/lib/api';
import { asStr, getObj, pickStr, prettyKey } from './signalsNormalize';
import { resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import type { AITradeValidationResponse } from '@/lib/types';

const UNDERLYINGS = ['NIFTY', 'BANKNIFTY', 'SENSEX'];
const TIMEFRAMES = ['1M', '3M', '5M', '15M'];
const DIRECTIONS = ['LONG_CALL', 'LONG_PUT'];

type CreateForm = {
  underlying: string;
  strategy: string;
  direction: string;
  timeframe: string;
  trigger: string;
  sl: string;
  t1: string;
  t2: string;
  confidence: string;
  lots: string;
  executePaper: boolean;
};

const EMPTY_FORM: CreateForm = {
  underlying: 'NIFTY',
  strategy: 'BREAKOUT',
  direction: 'LONG_CALL',
  timeframe: '5M',
  trigger: '',
  sl: '',
  t1: '',
  t2: '',
  confidence: '70',
  lots: '1',
  executePaper: true,
};

const SECTION_LABEL: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 750,
  letterSpacing: '0.07em',
  textTransform: 'uppercase',
  color: 'var(--ds-ink-3)',
};

const GRID_4: React.CSSProperties = {
  display: 'grid',
  gap: 10,
  gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
};

export function SignalCreateDialog({
  open,
  onOpenChange,
  strategies,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  strategies: string[];
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; msg: string } | null>(null);
  const aiSettings = useAISettings();
  const [thesis, setThesis] = useState('');
  const [audit, setAudit] = useState<AITradeValidationResponse | null>(null);
  const [auditBusy, setAuditBusy] = useState(false);
  const [auditErr, setAuditErr] = useState<string | null>(null);

  const set = (key: keyof CreateForm, value: string | boolean) =>
    setForm((p) => ({ ...p, [key]: value }));

  const canAudit = (() => {
    const e = Number(form.trigger);
    const s = Number(form.sl);
    const t = Number(form.t1 || form.t2);
    return Number.isFinite(e) && e > 0 && Number.isFinite(s) && s > 0 && Number.isFinite(t) && t > 0;
  })();

  const runAudit = useCallback(async () => {
    if (!canAudit) {
      setAuditErr('Enter trigger / stop / target to pre-check.');
      return;
    }
    setAuditBusy(true);
    setAuditErr(null);
    setAudit(null);
    try {
      const resolved = resolveAISettings(aiSettings);
      const dir = form.direction === 'LONG_PUT' ? 'SELL' as const : 'BUY' as const;
      const res = await api.validateTradeSetup({
        symbol: toBackendSymbol(form.underlying),
        direction: dir,
        entry_price: Number(form.trigger),
        stop_loss: Number(form.sl),
        target_price: Number(form.t1 || form.t2),
        thesis_notes: thesis.trim() || null,
        provider: resolved.provider,
        model: resolved.model,
        allow_paid: resolved.allow_paid,
        openrouter_api_key: resolved.openRouterApiKey || null,
        gemini_api_key: resolved.geminiApiKey || null,
      });
      setAudit(res.data);
    } catch (e) {
      setAuditErr(e instanceof Error ? e.message : 'Pre-check failed');
    } finally {
      setAuditBusy(false);
    }
  }, [form, thesis, aiSettings, canAudit]);

  const submit = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      const numOrUndef = (s: string): number | undefined => {
        const t = s.trim();
        if (!t) return undefined;
        const n = Number(t);
        return Number.isFinite(n) ? n : undefined;
      };
      const payload: Record<string, unknown> = {
        underlying: form.underlying,
        strategy: form.strategy,
        direction: form.direction,
        timeframe: form.timeframe,
        execute_paper: form.executePaper,
      };
      const trigger = numOrUndef(form.trigger);
      const sl = numOrUndef(form.sl);
      const t1 = numOrUndef(form.t1);
      const t2 = numOrUndef(form.t2);
      const conf = numOrUndef(form.confidence);
      const lots = numOrUndef(form.lots);
      if (trigger !== undefined) payload.trigger_price = trigger;
      if (sl !== undefined) payload.stop_loss = sl;
      if (t1 !== undefined) payload.target_1 = t1;
      if (t2 !== undefined) payload.target_2 = t2;
      if (conf !== undefined) payload.confidence = conf;
      if (lots !== undefined) payload.lots = lots;
      const res = await api.generateSignal(payload);
      const r = res as unknown as Record<string, unknown>;
      if (r?.success === false) {
        setNote({ ok: false, msg: asStr(r?.message) ?? 'generate failed' });
        return;
      }
      const sig = getObj(r?.signal);
      const sid = (sig ? pickStr(sig, 'signal_id', 'id') : null) ?? 'created';
      setNote({ ok: true, msg: `Signal ${sid} created.` });
      onCreated();
      window.setTimeout(() => onOpenChange(false), 700);
    } catch (e) {
      setNote({ ok: false, msg: e instanceof Error ? e.message : 'generate failed' });
    } finally {
      setBusy(false);
    }
  }, [form, onCreated, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>New signal</DialogTitle>
          <DialogDescription>
            Manually register a setup. Optionally attach levels and execute a paper trade on create.
          </DialogDescription>
        </DialogHeader>

        <div style={{ display: 'grid', gap: 14 }}>
          <div style={GRID_4}>
            <label className="field">
              <span>Underlying</span>
              <select className="input" value={form.underlying} onChange={(e) => set('underlying', e.target.value)}>
                {UNDERLYINGS.map((u) => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Strategy</span>
              <select className="input" value={form.strategy} onChange={(e) => set('strategy', e.target.value)}>
                {strategies.map((s) => (
                  <option key={s} value={s}>{prettyKey(s).toUpperCase()}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Direction</span>
              <select className="input" value={form.direction} onChange={(e) => set('direction', e.target.value)}>
                {DIRECTIONS.map((d) => (
                  <option key={d} value={d}>{prettyKey(d).replace(/\b\w/g, (c) => c.toUpperCase())}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Timeframe</span>
              <select className="input" value={form.timeframe} onChange={(e) => set('timeframe', e.target.value)}>
                {TIMEFRAMES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
          </div>

          <div style={{ display: 'grid', gap: 8 }}>
            <div style={SECTION_LABEL}>Levels â€” optional</div>
            <div style={GRID_4}>
              {(
                [
                  ['trigger', 'Trigger'],
                  ['sl', 'Stop loss'],
                  ['t1', 'Target 1'],
                  ['t2', 'Target 2'],
                ] as Array<[keyof CreateForm, string]>
              ).map(([key, label]) => (
                <label key={key} className="field">
                  <span>{label}</span>
                  <input
                    className="input num"
                    inputMode="decimal"
                    placeholder="â€”"
                    value={String(form[key])}
                    onChange={(e) => set(key, e.target.value)}
                  />
                </label>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gap: 8 }}>
            <div style={SECTION_LABEL}>Sizing</div>
            <div style={{ ...GRID_4, alignItems: 'end' }}>
              <label className="field">
                <span>Confidence</span>
                <input
                  className="input num"
                  inputMode="decimal"
                  value={form.confidence}
                  onChange={(e) => set('confidence', e.target.value)}
                />
              </label>
              <label className="field">
                <span>Lots</span>
                <input
                  className="input num"
                  inputMode="decimal"
                  value={form.lots}
                  onChange={(e) => set('lots', e.target.value)}
                />
              </label>
              <label
                style={{
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                  fontSize: 13,
                  fontWeight: 600,
                  paddingBottom: 9,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                <input
                  type="checkbox"
                  checked={form.executePaper}
                  onChange={(e) => set('executePaper', e.target.checked)}
                />
                Execute paper on create
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 8, borderTop: '1px solid var(--ds-border)', paddingTop: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={SECTION_LABEL}>AI pre-check — thesis vs live walls &amp; regime</span>
              <span style={{ marginLeft: 'auto' }} />
              <button type="button" className="btn btn-ic" disabled={auditBusy || !canAudit} onClick={() => void runAudit()} title={canAudit ? 'Validate setup against live market' : 'Enter trigger / stop / target first'}>
                <ShieldCheck size={14} />
                {auditBusy ? 'Checking…' : 'Pre-check'}
              </button>
            </div>
            <input
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              placeholder="Thesis (optional) — e.g. breakout above VWAP with PCR support"
              style={{ width: '100%', background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 10, padding: '8px 12px', fontSize: 12.5 }}
            />
            {auditErr ? <p style={{ margin: 0, fontSize: 12, color: 'var(--ds-bear-strong)' }}>{auditErr}</p> : null}
            {audit ? (
              <div style={{ display: 'grid', gap: 8, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 10, padding: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span className={`badge ${audit.decision === 'CONFIRM' ? 'b-bull' : audit.decision === 'REJECT' ? 'b-bear' : audit.decision === 'WATCH' ? 'b-warn' : 'b-neut'}`}>{audit.decision}</span>
                  <span style={{ fontSize: 12, fontFamily: 'var(--sg-mono)' }}>score {audit.score} · RR {Number(audit.risk_reward_calculated).toFixed(2)}</span>
                </div>
                <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}>{audit.executive_verdict}</p>
                {audit.invalidation_conditions?.length ? (
                  <div style={{ fontSize: 12 }}><strong>Invalidate if:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 16 }}>{audit.invalidation_conditions.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
                ) : null}
                {audit.warning_traps?.length ? (
                  <div style={{ fontSize: 12 }} className="muted"><strong>Traps:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 16 }}>{audit.warning_traps.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <DialogFooter>
          {note ? (
            <span
              className={note.ok ? 'v-bull' : 'v-bear'}
              style={{ fontSize: 12.5, fontWeight: 600, marginRight: 'auto', textAlign: 'left' }}
            >
              {note.msg}
            </span>
          ) : null}
          <button type="button" className="btn" disabled={busy} onClick={() => onOpenChange(false)}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary btn-ic" disabled={busy} onClick={() => void submit()}>
            <Sparkles size={15} />
            {busy ? 'Generatingâ€¦' : 'Generate'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SignalCreateDialog;

