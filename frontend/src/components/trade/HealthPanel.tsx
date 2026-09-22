'use client';

import type { ReactNode } from 'react';
import { getObj } from '@/lib/signalsNormalize';
import {
  toDisplayEntries,
  type AiModelRow,
  type DisplayEntry,
  type StrategyRow,
} from '@/lib/tradeOps';
import type { TradeCapital, TradeConsent } from '@/hooks/useTradeOps';

function KvList({ entries, emptyNote }: { entries: DisplayEntry[]; emptyNote: string }) {
  if (entries.length === 0) return <p className="sg-empty">{emptyNote}</p>;
  return (
    <div className="sg-kvlist">
      {entries.map((entry) => (
        <div className="sg-kv" key={entry.label}>
          <span className="l">{entry.label}</span>
          <span className="v">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

function Readout({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="card-hd">
        <h3 className="card-title">{title}</h3>
        {meta ? <span className="card-meta">{meta}</span> : null}
      </header>
      {children}
    </section>
  );
}

/** Compact read-only governance readouts. No mutations live in this tab. */
export function HealthPanel({
  consent,
  capital,
  strategies,
  aiModels,
  drift,
  slo,
  brokerCaps,
  greeks,
}: {
  consent: TradeConsent | null;
  capital: TradeCapital | null;
  strategies: StrategyRow[];
  aiModels: AiModelRow[];
  drift: Record<string, unknown> | null;
  slo: Record<string, unknown> | null;
  brokerCaps: Record<string, unknown> | null;
  greeks: Record<string, unknown> | null;
}) {
  const sloEntries: DisplayEntry[] = slo
    ? [
        ...(typeof slo.trading_allowed === 'boolean'
          ? [{ label: 'trading allowed', value: slo.trading_allowed ? 'yes' : 'no' }]
          : []),
        ...toDisplayEntries(getObj(slo.execution_quality) ?? {}, 6),
        ...toDisplayEntries(getObj(slo.slo_compliance) ?? {}, 6),
      ]
    : [];

  const brokerNames = brokerCaps ? Object.keys(brokerCaps) : [];
  const brokerEntries: DisplayEntry[] = [];
  for (const name of brokerNames.slice(0, 4)) {
    const caps = getObj(brokerCaps?.[name]);
    if (!caps) continue;
    const env = typeof caps.environment === 'string' ? caps.environment : null;
    const version = typeof caps.api_version === 'string' ? caps.api_version : null;
    const ops = typeof caps.orders_per_second === 'number' ? caps.orders_per_second : null;
    brokerEntries.push({
      label: name,
      value: [env, version ? `api ${version}` : null, ops !== null ? `${ops} ord/s` : null]
        .filter(Boolean)
        .join(' · '),
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <Readout title="Consent Status" meta={consent?.version ? `disclosure ${consent.version}` : undefined}>
        <KvList
          emptyNote="Consent status unavailable."
          entries={
            consent
              ? [
                  {
                    label: 'current disclosure',
                    value: consent.currentOk === true ? 'acknowledged' : consent.currentOk === false ? 'missing' : '—',
                  },
                  { label: 'consents on file', value: consent.count !== null ? String(consent.count) : '—' },
                ]
              : []
          }
        />
      </Readout>

      <Readout title="Capital Config" meta={capital ? 'risk limits' : undefined}>
        <KvList emptyNote="Capital config unavailable." entries={toDisplayEntries(capital?.config, 14)} />
      </Readout>

      <Readout title="Strategies Registry" meta={`${strategies.length} strategie(s)`}>
        {strategies.length === 0 ? (
          <p className="sg-empty">No strategies registered for this account.</p>
        ) : (
          <div className="sg-kvlist">
            {strategies.map((strategy) => (
              <div className="sg-kv" key={strategy.id}>
                <span className="l">{strategy.name}</span>
                <span className="v">
                  {[strategy.stage, strategy.active === true ? 'active' : strategy.active === false ? 'inactive' : null]
                    .filter(Boolean)
                    .join(' · ') || '—'}
                </span>
              </div>
            ))}
          </div>
        )}
      </Readout>

      <Readout title="AI Models & Drift" meta={aiModels.length > 0 ? `${aiModels.length} model(s)` : undefined}>
        {aiModels.length === 0 && !drift ? (
          <p className="sg-empty">No AI models or drift metrics reported.</p>
        ) : (
          <>
            {aiModels.length > 0 ? (
              <div className="sg-kvlist">
                {aiModels.map((model) => (
                  <div className="sg-kv" key={model.key}>
                    <span className="l">{model.modelId ?? model.key}</span>
                    <span className="v">
                      {[model.status, model.canaryPct !== null ? `canary ${model.canaryPct}%` : null]
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            {drift ? <KvList emptyNote="No drift metrics." entries={toDisplayEntries(drift, 10)} /> : null}
          </>
        )}
      </Readout>

      <Readout title="SLO Metrics" meta="production budgets">
        <KvList emptyNote="SLO dashboard unavailable." entries={sloEntries} />
      </Readout>

      <Readout title="Broker Capabilities" meta={brokerNames.length > 0 ? brokerNames.join(', ') : undefined}>
        <KvList emptyNote="Broker capabilities unavailable." entries={brokerEntries} />
      </Readout>

      <Readout title="Portfolio Greeks" meta="stream">
        <KvList emptyNote="No portfolio greeks reported." entries={toDisplayEntries(greeks, 12)} />
      </Readout>
    </div>
  );
}
