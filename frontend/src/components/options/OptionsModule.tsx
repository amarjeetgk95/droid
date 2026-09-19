'use client';

import { useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useOptionsDesk } from '@/hooks/useOptionsDesk';
import { fmtExpiry, getObj, pickNum } from '@/lib/signalsNormalize';
import { safeNum } from '@/lib/utils';
import { regimeBadge } from '@/lib/optionsDesk';
import { AnalyticsPanel } from './AnalyticsPanel';
import { ChainPanel } from './ChainPanel';
import { FuturesPanel } from './FuturesPanel';
import { QuantToolsPanel } from './QuantToolsPanel';
import { StrategyPanel } from './StrategyPanel';

type ModuleTab = 'chain' | 'analytics' | 'tools' | 'strategy' | 'futures';

const TABS: Array<{ id: ModuleTab; label: string }> = [
  { id: 'chain', label: 'Chain' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'tools', label: 'Quant tools' },
  { id: 'strategy', label: 'Strategy' },
  { id: 'futures', label: 'Futures' },
];

export function OptionsModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const [tab, setTab] = useState<ModuleTab>('chain');

  const desk = useOptionsDesk(instrument, { safetyRefreshMs: isOpen ? 60_000 : null });

  const spot = useMemo(() => {
    if (typeof desk.chain?.spot_price === 'number') return desk.chain.spot_price;
    const analyticsObj = getObj(desk.analytics);
    return analyticsObj ? pickNum(analyticsObj, 'spot_price', 'spot') : null;
  }, [desk.chain, desk.analytics]);

  const atm = useMemo(() => {
    const analyticsObj = getObj(desk.analytics);
    const fromAnalytics = analyticsObj ? pickNum(analyticsObj, 'atm_strike') : null;
    if (fromAnalytics !== null) return fromAnalytics;
    return desk.chain?.strikes.find((row) => row.is_atm)?.strike ?? null;
  }, [desk.chain, desk.analytics]);

  const analyticsObj = getObj(desk.analytics);
  const pcr = analyticsObj ? pickNum(analyticsObj, 'pcr_oi', 'pcr') : null;
  const atmIv = analyticsObj ? pickNum(analyticsObj, 'atm_iv') : null;
  const maxPainStrike =
    (analyticsObj ? pickNum(analyticsObj, 'max_pain_strike', 'max_pain') : null) ??
    desk.maxPain?.max_pain_strike ??
    null;
  const strikeCount = desk.chain?.strikes.length ?? 0;
  const regime = useMemo(() => regimeBadge(desk.regimeOverview?.regime_state), [desk.regimeOverview]);

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>Options &amp; Strategy</h2>
          <span className={`badge ${regime.cls}`} title="Market regime for this instrument">
            {regime.label}
          </span>
          <span className="card-meta">{desk.instrument}</span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            spot <b>{spot !== null ? safeNum(spot, '—', 1) : '—'}</b>
          </span>
          <span className="stat-chip">
            ATM IV <b>{atmIv !== null ? `${safeNum(atmIv)}%` : '—'}</b>
          </span>
          <span className="stat-chip">
            PCR <b>{pcr !== null ? safeNum(pcr) : '—'}</b>
          </span>
          <span className="stat-chip">
            max pain <b>{maxPainStrike !== null ? safeNum(maxPainStrike, '—', 0) : '—'}</b>
          </span>
          <span className="stat-chip">
            strikes <b>{strikeCount}</b>
          </span>
          <span className="stat-chip">{isOpen ? 'market open' : 'market closed'}</span>
        </div>
        <div className="ds-filters">
          <label className="field">
            <span className="field-l">Expiry</span>
            <select
              className="input"
              value={desk.expiry ?? ''}
              onChange={(event) => desk.setExpiry(event.target.value || null)}
              aria-label="Option expiry"
            >
              <option value="">Default</option>
              {desk.expiries.map((expiry) => (
                <option key={expiry} value={expiry}>
                  {fmtExpiry(expiry)} · {expiry}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn"
            disabled={desk.refreshing}
            onClick={() => void desk.refresh()}
          >
            <RefreshCw size={13} className={desk.refreshing ? 'animate-spin' : undefined} />
            {desk.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <section className="tabbar w-fit" role="tablist" aria-label="Options module sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            className={`tab ${tab === entry.id ? 'is-active' : ''}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
            {entry.id === 'chain' && strikeCount > 0 ? <span className="n">{strikeCount}</span> : null}
            {entry.id === 'strategy' && desk.templates.length > 0 ? (
              <span className="n">{desk.templates.length}</span>
            ) : null}
          </button>
        ))}
      </section>

      {desk.error ? <p className="sg-err">{desk.error}</p> : null}

      <p className="sg-note">
        Chain and analytics repoll every 60s while the market is open; quant tools run only on
        demand. Regime and options context prefer the CommandView stream, everything else reads
        REST. Futures legs report honest empty states until the broker feed is wired.
      </p>

      {tab === 'chain' ? (
        <ChainPanel chain={desk.chain} loading={desk.loading} instrument={desk.instrument} />
      ) : null}

      {tab === 'analytics' ? (
        <AnalyticsPanel
          analytics={desk.analytics}
          analyticsSource={desk.analyticsSource}
          maxPain={desk.maxPain}
          flow={desk.flow}
          regime={desk.regimeOverview}
          regimeSource={desk.regimeSource}
          pivots={desk.pivots}
          indicators={desk.indicators}
          vix={desk.vix}
        />
      ) : null}

      {tab === 'tools' ? <QuantToolsPanel desk={desk} spot={spot} atm={atm} /> : null}

      {tab === 'strategy' ? <StrategyPanel desk={desk} spot={spot} /> : null}

      {tab === 'futures' ? <FuturesPanel desk={desk} /> : null}
    </div>
  );
}
