'use client';

import React, { useCallback, useState } from 'react';
import { DeskHeader, DeskShell } from '@/components/layout/DeskShell';
import { useInstrument } from '@/context/InstrumentContext';
import { api } from '@/lib/api';
import { ScannerPanel, type ScannerData } from '@/components/signals/ScannerPanel';
import {
  CalibrationHeatmap,
  ExperimentRunner,
  FeatureInspector,
  IndicatorWorkbench,
  MLModelRegistry,
  PredictionTracker,
  StrategyLabBuilder,
} from '@/components/research-lab';

export default function ResearchLabPage() {
  const {
    instrument,
    setInstrument,
    timeframe,
    setTimeframe,
    allInstruments,
    allTimeframes,
  } = useInstrument();

  /* Scanner is on-demand only (no poll): one GET per explicit Scan click, and
     the same defensive flow as the signals desk loader. */
  const [scannerData, setScannerData] = useState<ScannerData | null>(null);
  const [scannerLoading, setScannerLoading] = useState(false);
  const [scannerError, setScannerError] = useState<string | null>(null);

  const loadScanner = useCallback(async () => {
    setScannerLoading(true);
    setScannerError(null);
    try {
      const res = await api.getSignalsScanner();
      setScannerData(res);
    } catch (e) {
      setScannerError(e instanceof Error ? e.message : 'Scanner failed');
    } finally {
      setScannerLoading(false);
    }
  }, []);

  return (
    <DeskShell>
      <DeskHeader
        title="Research Lab"
        meta={`${instrument} · ${timeframe} · isolated research pipeline (registry → validation → calibration)`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="seg" role="group" aria-label="Instrument">
              {allInstruments.map((inst) => (
                <button
                  key={inst}
                  type="button"
                  className="seg-btn"
                  data-active={instrument === inst}
                  aria-pressed={instrument === inst}
                  onClick={() => setInstrument(inst)}
                >
                  {inst}
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label="Timeframe">
              {allTimeframes.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  className="seg-btn"
                  data-active={timeframe === tf}
                  aria-pressed={timeframe === tf}
                  onClick={() => setTimeframe(tf)}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
        }
      />

      <div className="space-y-5">
        <ScannerPanel
          scannerData={scannerData}
          scannerLoading={scannerLoading}
          scannerError={scannerError}
          onScan={loadScanner}
        />

        <StrategyLabBuilder />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <MLModelRegistry />
          <CalibrationHeatmap />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <IndicatorWorkbench />
          <FeatureInspector />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <ExperimentRunner />
          <PredictionTracker />
        </div>
      </div>
    </DeskShell>
  );
}
