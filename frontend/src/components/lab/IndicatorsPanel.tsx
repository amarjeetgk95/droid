'use client';

import { useCallback, useState } from 'react';
import { useToast } from '@/components/ui/toast';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { fmtLabNum, tagClass, directionToneOf } from '@/lib/labDesk';
import { getObj, pickStr } from '@/lib/signalsNormalize';
import type { useResearchLab } from '@/hooks/useResearchLab';

type Lab = ReturnType<typeof useResearchLab>;

export function IndicatorsPanel({ lab }: { lab: Lab }) {
  const { push } = useToast();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('5m');
  const [paramsJson, setParamsJson] = useState('{}');
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const handleSelect = useCallback(async (id: string) => {
    setSelectedId(id);
    await lab.openIndicator(id);
  }, [lab]);

  const handleCalculate = useCallback(async () => {
    if (!confirmId) return;
    let params: Record<string, unknown> = {};
    try {
      const parsed: unknown = JSON.parse(paramsJson || '{}');
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) params = parsed as Record<string, unknown>;
    } catch {
      push('error', 'Parameters must be valid JSON — using {}.');
    }
    const res = await lab.calculateIndicator(confirmId, { instrument: lab.apiInstrument, timeframe, parameters: params });
    push(res.ok ? 'success' : 'error', res.message);
    setConfirmId(null);
  }, [confirmId, paramsJson, timeframe, lab, push]);

  const detailObj = lab.indicatorDetail ? getObj(lab.indicatorDetail) : null;
  const calcObj = lab.calcResult ? getObj(lab.calcResult) : null;

  return (
    <div className="flex flex-col gap-3">
      <section className="card" aria-label="Indicator registry">
        <div className="card-hd">
          <h3 className="card-title">Indicator registry</h3>
          <span className="card-meta num">{lab.indicators.length} registered</span>
        </div>
        <div className="card-bd">
          {lab.indError ? <p className="sg-err">{lab.indError}</p> : null}
          {lab.indLoading ? <p className="sg-empty">Loading indicators…</p> : null}
          {!lab.indLoading && lab.indicators.length === 0 && !lab.indError ? (
            <p className="sg-empty">No indicators registered on this backend.</p>
          ) : null}
          {lab.indicators.length > 0 ? (
            <div className="tbl-scroll">
              <table className="sg-table">
                <thead><tr><th>Indicator</th><th>Category</th><th>Lifecycle</th><th>Actions</th></tr></thead>
                <tbody>
                  {lab.indicators.map((ind) => (
                    <tr key={ind.id} data-active={selectedId === ind.id}>
                      <td><span className="sg-sym">{ind.id}</span><div className="sg-rownote">{ind.name}{ind.version ? ` · ${ind.version}` : ''}</div></td>
                      <td><span className={`sg-tag neut`}>{ind.category ?? '—'}</span></td>
                      <td><span className={`sg-tag ${ind.lifecycle === 'ACTIVE' || ind.lifecycle === 'PRODUCTION' ? 'bull' : ind.lifecycle ? 'warn' : 'neut'}`}>{ind.lifecycle ?? '—'}</span></td>
                      <td><span className="sg-actions">
                        <button type="button" className="sg-ibtn" title="View definition" onClick={() => void handleSelect(ind.id)}>↗</button>
                        <button type="button" className="sg-ibtn" title="Calculate on demand" onClick={() => { setSelectedId(ind.id); setConfirmId(ind.id); }}>▶</button>
                      </span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </section>

      {selectedId ? (
        <section className="card" aria-label="Indicator detail">
          <div className="card-hd"><h3 className="card-title">Indicator · {selectedId}</h3></div>
          <div className="card-bd">
            {!detailObj ? <p className="sg-empty">Select an indicator to view its definition.</p> : (
              <div className="sg-kvlist">
                <div className="sg-kv"><span className="l">name</span><span className="v">{pickStr(detailObj, 'name') ?? '—'}</span></div>
                <div className="sg-kv"><span className="l">category</span><span className="v">{pickStr(detailObj, 'category') ?? '—'}</span></div>
                <div className="sg-kv"><span className="l">lifecycle</span><span className="v">{pickStr(detailObj, 'lifecycle') ?? '—'}</span></div>
                <div className="sg-kv"><span className="l">version</span><span className="v">{pickStr(detailObj, 'indicator_version', 'version') ?? '—'}</span></div>
                <div className="sg-kv"><span className="l">description</span><span className="v">{pickStr(detailObj, 'description') ?? '—'}</span></div>
              </div>
            )}
            <p className="sg-note">Calculate runs on live market candles for {lab.apiInstrument}. Confirm before running.</p>
            <div className="ds-filters">
              <span className="seg">
                {['1m', '5m', '15m'].map((tf) => (
                  <button key={tf} type="button" className="seg-btn" data-active={timeframe === tf} onClick={() => setTimeframe(tf)}>{tf}</button>
                ))}
              </span>
              <button type="button" className="btn btn-primary" onClick={() => setConfirmId(selectedId)}>Calculate</button>
            </div>
            <label className="field"><span className="field-l">parameters (JSON)</span><input className="input mono" value={paramsJson} onChange={(e) => setParamsJson(e.target.value)} spellCheck={false} /></label>
            {calcObj ? (
              <div className="mt-3 border-t border-border-subtle pt-3">
                <p className="sg-note">Last calculation · direction <span className={`sg-tag ${tagClass(directionToneOf(pickStr(calcObj, 'direction')))}`}>{pickStr(calcObj, 'direction') ?? '—'}</span></p>
                <div className="sg-kvlist">
                  <div className="sg-kv"><span className="l">value</span><span className="v">{fmtLabNum(calcObj.value ?? calcObj.score ?? calcObj.raw_value)}</span></div>
                  <div className="sg-kv"><span className="l">confidence</span><span className="v">{fmtLabNum(calcObj.confidence)}</span></div>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      <ConfirmDialog
        open={confirmId !== null}
        onOpenChange={(o) => { if (!o) setConfirmId(null); }}
        tone="primary"
        confirmLabel="Calculate now"
        busy={lab.calcBusy}
        title={`Calculate ${confirmId ?? 'indicator'} on ${lab.apiInstrument} ${timeframe}?`}
        description="Runs the indicator over live market candles. Read-only — no state is mutated."
        onConfirm={handleCalculate}
      />
    </div>
  );
}
