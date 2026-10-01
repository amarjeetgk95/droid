'use client';

import { useState } from 'react';
import { FlaskConical, Play, ShieldCheck, AlertTriangle, Loader2 } from 'lucide-react';
import { useIndicatorResearch, type ResearchTab } from '@/hooks/useIndicatorResearch';
import { IndicatorLibrary } from './IndicatorLibrary';
import { IndicatorParameterPanel } from './IndicatorParameterPanel';
import { SignalBuilder } from './SignalBuilder';
import { BacktestControls } from './BacktestControls';
import { ResearchChart } from './ResearchChart';
import { EquityCurve } from './EquityCurve';
import { TradeTable } from './TradeTable';
import { PerformanceDashboard, NoLookaheadBadge, OrderFlowProvenanceBadge } from './PerformanceDashboard';
import { ParameterOptimizer } from './ParameterOptimizer';
import { IndicatorCompare } from './IndicatorCompare';
import { PredictionPanel } from './PredictionPanel';
import { ExperimentsPanel } from './ExperimentsPanel';
import { SelectivityPanel } from './SelectivityPanel';
import { RobustnessPanel } from './RobustnessPanel';
import { PresetSelector } from './PresetSelector';
import { fmtInt, resultScopeLine } from '@/lib/indicatorResearch';

const TABS: Array<{ id: ResearchTab; label: string }> = [
  { id: 'chart', label: 'Chart & Backtest' },
  { id: 'results', label: 'Results' },
  { id: 'selectivity', label: 'Selectivity' },
  { id: 'robustness', label: 'Robustness & Ablation' },
  { id: 'compare', label: 'Compare' },
  { id: 'predict', label: 'Prediction' },
  { id: 'optimize', label: 'Optimise' },
  { id: 'experiments', label: 'Experiments' },
];

export function IndicatorResearchModule() {
  const store = useIndicatorResearch();
  const [tab, setTab] = useState<ResearchTab>('chart');

  const {
    catalog,
    researchCatalog,
    isolation,
    metaById,
    instrument,
    setInstrument,
    timeframe,
    setTimeframe,
    start,
    setStart,
    end,
    setEnd,
    selected,
    activeMeta,
    activeSpec,
    addIndicator,
    removeIndicator,
    setParams,
    resetParams,
    rules,
    setRules,
    rulesMode,
    setRulesMode,
    useIndicatorDefaults,
    presets,
    loadPreset,
    settings,
    setSettings,
    preview,
    backtest,
    selectivity,
    robustness,
    ablation,
    optimize,
    walkForward,
    compare,
    predict,
    experiments,
    saveNotice,
    setSaveNotice,
    canRun,
    runPreview,
    runBacktest,
    runSelectivity,
    runRobustness,
    runAblation,
    runOptimize,
    runWalkForward,
    runCompare,
    runPredict,
    refreshExperiments,
    saveExperiment,
    deleteExperiment,
    exportUrl,
  } = store;

  const features = preview.data ? Object.keys(preview.data.outputs) : [];
  const presetIds = ['fisher', 'stc', 'ebsw', 'rsi', 'macd', 'wavetrend', 'supertrend', 'ema', 'vwap', 'adx'].filter((id) =>
    metaById.has(id),
  );

  return (
    <div className="flex flex-col gap-3">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <section className="ds-commandbar" aria-label="Indicator research controls">
        <div className="ds-title">
          <h2>Indicator Research</h2>
          <span className="badge b-bull" title="This module can never place orders — see the isolation audit in Ops">
            <ShieldCheck size={11} /> research only
          </span>
          <NoLookaheadBadge validation={backtest.data?.validation} compact />
          {backtest.data ? (
            <OrderFlowProvenanceBadge
              provenance={backtest.data?.order_flow_provenance}
              recordsCount={backtest.data?.order_flow_records_count}
              compact
            />
          ) : null}
        </div>
        <div className="ds-filters flex-wrap">
          <label className="field w-auto">
            <span className="field-l">Instrument</span>
            <select className="input py-1" value={instrument} onChange={(e) => setInstrument(e.target.value)}>
              {(researchCatalog.data?.instruments ?? ['NIFTY', 'BANKNIFTY', 'SENSEX']).map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </label>
          <label className="field w-auto">
            <span className="field-l">Timeframe</span>
            <select className="input py-1" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {(researchCatalog.data?.timeframes ?? ['1m', '5m']).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="field w-auto">
            <span className="field-l">From</span>
            <input type="date" className="input py-1" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field w-auto">
            <span className="field-l">To</span>
            <input type="date" className="input py-1" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <button type="button" className="btn btn-primary" disabled={!canRun || preview.status === 'loading'} onClick={() => void runPreview()}>
            {preview.status === 'loading' ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            Load chart
          </button>
          <button type="button" className="btn" disabled={!canRun || backtest.status === 'loading'} onClick={() => void runBacktest()}>
            {backtest.status === 'loading' ? <Loader2 size={12} className="animate-spin" /> : <FlaskConical size={12} />}
            Backtest
          </button>
        </div>
      </section>

      {researchCatalog.error ? (
        <div className="notice notice--down">
          <span>{researchCatalog.error} — start the backend and retry.</span>
        </div>
      ) : null}

      {(() => {
        const entry = researchCatalog.data?.entries?.find((e) => e.instrument === instrument && e.timeframe === timeframe);
        if (entry && !entry.available) {
          return (
            <div className="notice notice--warn">
              <span>
                No {instrument} {timeframe}m dataset is currently available{entry.versions_on_disk?.length ? ` (found versions: ${entry.versions_on_disk.join(', ')})` : ''}
                {entry.status ? ` — ${entry.status}` : ''}. The module fails honestly instead of silently using another
                symbol&rsquo;s bars.
              </span>
            </div>
          );
        }
        return null;
      })()}

      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <section className="tabbar w-fit" role="tablist" aria-label="Indicator research sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'is-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.id === 'results' && backtest.data?.trade_count ? <span className="n">{fmtInt(backtest.data.trade_count)}</span> : null}
            {t.id === 'experiments' && experiments.data?.length ? <span className="n">{fmtInt(experiments.data.length)}</span> : null}
          </button>
        ))}
      </section>

      {tab === 'chart' ? (
        <div className="flex flex-col gap-3">
          <PresetSelector presets={presets.data ?? []} onSelect={loadPreset} />
          <div className="grid gap-3 xl:grid-cols-[16rem_minmax(0,1fr)_20rem]">
          {/* Left: indicator library */}
          <aside className="card flex max-h-[calc(100vh-13rem)] flex-col">
            <div className="card-bd flex min-h-0 flex-1 flex-col">
              <IndicatorLibrary
                catalog={catalog.data}
                loading={catalog.status === 'loading'}
                error={catalog.error}
                selectedIds={selected.map((s) => s.indicator_id)}
                activeId={activeSpec?.indicator_id ?? null}
                onSelect={addIndicator}
                onRemove={removeIndicator}
                onRetry={() => window.location.reload()}
              />
            </div>
          </aside>

          {/* Centre: chart */}
          <main className="card">
            <div className="card-hd">
              <h3 className="card-title">Price &amp; indicator chart</h3>
              <span className="card-meta num">{preview.data ? resultScopeLine({ data: preview.data } as never) : 'no window loaded'}</span>
            </div>
            <div className="card-bd flex flex-col gap-2">
              {preview.status === 'error' ? <p className="notice notice--down text-[11px]">{preview.error}</p> : null}
              {preview.data?.warnings?.length ? (
                <div className="notice notice--warn">
                  <ul className="list-disc pl-4 text-[10px]">
                    {preview.data.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {preview.data && preview.data.ok ? (
                <ResearchChart preview={preview.data} />
              ) : (
                <div className="flex h-64 items-center justify-center rounded-md border border-border-subtle bg-surface-subtle">
                  <p className="sg-note">
                    {canRun
                      ? 'Set the window and press "Load chart" to preview indicator values and raw signals.'
                      : 'Select an indicator from the library to begin.'}
                  </p>
                </div>
              )}
              {preview.data ? (
                <div className="sg-kvlist">
                  <div className="sg-kv">
                    <span className="sg-lab">Bars in window</span>
                    <span className="sg-num num">{fmtInt(preview.data.data.bars)}</span>
                  </div>
                  <div className="sg-kv">
                    <span className="sg-lab">Warm-up</span>
                    <span className="sg-num num">{fmtInt(preview.data.warmup_bars)} bars</span>
                  </div>
                  <div className="sg-kv">
                    <span className="sg-lab">Raw signals</span>
                    <span className="sg-num num">
                      {fmtInt(preview.data.signals.long.filter(Boolean).length)} long /{' '}
                      {fmtInt(preview.data.signals.short.filter(Boolean).length)} short
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
          </main>

          {/* Right: settings */}
          <aside className="card sg-scroll max-h-[calc(100vh-13rem)] overflow-y-auto">
            <div className="card-bd flex flex-col gap-3">
              {activeMeta && activeSpec ? (
                <>
                  <IndicatorParameterPanel
                    meta={activeMeta}
                    params={activeSpec.params}
                    onChange={(params) => setParams(activeSpec.indicator_id, params)}
                    onReset={() => resetParams(activeSpec.indicator_id)}
                    onRemove={() => removeIndicator(activeSpec.indicator_id)}
                  />
                  <div className="divider" />
                  <SignalBuilder
                    rules={rules}
                    onChange={setRules}
                    mode={rulesMode}
                    onModeChange={setRulesMode}
                    onUseDefaults={useIndicatorDefaults}
                    operators={catalog.data?.operators ?? []}
                    features={features}
                    ruleSummary={preview.data?.rule_summary ?? null}
                    problems={
                      preview.data?.rule_problems ? { long: preview.data.rule_problems.long ?? [], short: preview.data.rule_problems.short ?? [] } : null
                    }
                    indicatorName={activeMeta.name}
                  />
                  <div className="divider" />
                  <BacktestControls settings={settings} onChange={setSettings} />
                </>
              ) : (
                <div className="flex flex-col gap-2 py-6 text-center">
                  <AlertTriangle size={16} className="mx-auto text-warn" />
                  <p className="sg-note">Pick an indicator to reveal its parameters, signal rules and execution settings.</p>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
      ) : null}

      {tab === 'results' ? (
        <div className="flex flex-col gap-3">
          {backtest.status === 'error' ? (
            <div className="notice notice--down">
              <span>{backtest.error}</span>
            </div>
          ) : null}
          {backtest.status === 'idle' ? (
            <div className="card">
              <div className="card-bd">
                <p className="sg-note">No backtest yet — configure rules on the Chart tab and press Backtest.</p>
              </div>
            </div>
          ) : null}
          {backtest.data ? (
            <>
              <div className="grid gap-3 xl:grid-cols-2">
                <section className="card">
                  <div className="card-hd">
                    <h3 className="card-title">Equity curve &amp; drawdown</h3>
                    <span className="card-meta">net of modelled costs</span>
                  </div>
                  <div className="card-bd">
                    <EquityCurve
                      points={backtest.data.equity_curve ?? []}
                      initialCapital={backtest.data.metrics?.initial_capital ?? null}
                      thinned={backtest.data.equity_curve_thinned ?? null}
                    />
                  </div>
                </section>
                <section className="card">
                  <div className="card-hd">
                    <h3 className="card-title">Run configuration</h3>
                    <NoLookaheadBadge validation={backtest.data.validation} />
                  </div>
                  <div className="card-bd">
                    <div className="sg-kvlist">
                      <div className="sg-kv">
                        <span className="sg-lab">Window</span>
                        <span className="sg-num">{resultScopeLine(backtest.data)}</span>
                      </div>
                      <div className="sg-kv">
                        <span className="sg-lab">Indicators</span>
                        <span className="sg-num">
                          {(backtest.data.output_names ?? []).join(', ') || '—'}
                        </span>
                      </div>
                      <div className="sg-kv">
                        <span className="sg-lab">BUY rule</span>
                        <span className="sg-num">{backtest.data.signal_rule_summary?.long ?? '—'}</span>
                      </div>
                      <div className="sg-kv">
                        <span className="sg-lab">SELL rule</span>
                        <span className="sg-num">{backtest.data.signal_rule_summary?.short ?? '—'}</span>
                      </div>
                      <div className="sg-kv">
                        <span className="sg-lab">Execution</span>
                        <span className="sg-num">
                          {String((backtest.data.settings as Record<string, unknown> | undefined)?.execution ?? 'next open')}
                        </span>
                      </div>
                    </div>
                    <details className="sg-sect mt-2">
                      <summary className="micro-label cursor-pointer">Full settings JSON</summary>
                      <pre className="sg-scroll mt-1 max-h-40 overflow-auto rounded-md border border-border-subtle bg-surface-subtle p-2 font-mono text-[10px] text-ink-2">
                        {JSON.stringify(backtest.data.settings ?? {}, null, 2)}
                      </pre>
                    </details>
                  </div>
                </section>
              </div>

              <PerformanceDashboard result={backtest.data} />

              <section className="card">
                <div className="card-hd">
                  <h3 className="card-title">Trades</h3>
                  <span className="card-meta num">{fmtInt(backtest.data.trade_count ?? 0)} closed</span>
                </div>
                <div className="card-bd">
                  <TradeTable trades={backtest.data.trades ?? []} totalCount={backtest.data.trade_count ?? 0} />
                </div>
              </section>
            </>
          ) : null}
        </div>
      ) : null}

      {tab === 'selectivity' ? (
        <SelectivityPanel
          result={selectivity.data}
          loading={selectivity.status === 'loading'}
          error={selectivity.error}
          features={features}
          onRun={(feat, thresholds, op, dir, horizon) =>
            void runSelectivity(feat, thresholds, op, dir, horizon)
          }
        />
      ) : null}

      {tab === 'robustness' ? (
        <RobustnessPanel
          robustness={robustness.data}
          robustnessLoading={robustness.status === 'loading'}
          robustnessError={robustness.error}
          ablation={ablation.data}
          ablationLoading={ablation.status === 'loading'}
          ablationError={ablation.error}
          selectedCount={selected.length}
          onRunRobustness={() => void runRobustness()}
          onRunAblation={(obj) => void runAblation(obj)}
        />
      ) : null}

      {tab === 'compare' ? (
        <IndicatorCompare
          metas={catalog.data?.indicators ?? []}
          result={compare.data}
          loading={compare.status === 'loading'}
          error={compare.error}
          presetIds={presetIds}
          onRun={(ids, objective, useDefaults) => void runCompare(ids, objective, useDefaults)}
        />
      ) : null}

      {tab === 'predict' ? (
        <PredictionPanel
          result={predict.data}
          loading={predict.status === 'loading'}
          error={predict.error}
          onRun={(horizons) => void runPredict(horizons)}
        />
      ) : null}

      {tab === 'optimize' ? (
        <ParameterOptimizer
          meta={activeMeta}
          result={optimize.data}
          loading={optimize.status === 'loading'}
          error={optimize.error}
          onRun={(objective, maxCombos, minTrades, overrides, searchMode) =>
            void runOptimize(objective, maxCombos, minTrades, overrides, searchMode)
          }
          walkForward={walkForward.data}
          wfLoading={walkForward.status === 'loading'}
          wfError={walkForward.error}
          onRunWalkForward={(objective, folds, purge, overrides) =>
            void runWalkForward(objective, folds, purge, overrides)
          }
        />
      ) : null}

      {tab === 'experiments' ? (
        <ExperimentsPanel
          experiments={experiments.data ?? []}
          loading={experiments.status === 'loading'}
          error={experiments.error}
          notice={saveNotice}
          hasBacktest={Boolean(backtest.data)}
          canSave={Boolean(activeSpec)}
          onSave={(name, notes) => void saveExperiment(name, notes)}
          onDelete={(id) => void deleteExperiment(id)}
          exportUrl={exportUrl}
          onRefresh={() => void refreshExperiments()}
        />
      ) : null}

      {isolation ? (
        <p className="faint text-[10px]">
          Isolation audit: {isolation.isolated ? 'this module cannot reach trading code' : 'ISOLATION VIOLATION — see backend logs'}.
          {isolation.guarantees?.length ? ` Guarantees: ${isolation.guarantees.join('; ')}.` : ''}
        </p>
      ) : null}
    </div>
  );
}
