'use client';

import { useState, useEffect } from 'react';
import { Database, Download, ShieldCheck, Activity, Eye, Layers, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import type { HistoricalDataset, HistoricalDownloadJob, HistoricalDataGap } from '@/lib/api/historical';
import { DashboardOverview } from './DashboardOverview';
import { DatasetCatalogTable } from './DatasetCatalogTable';
import { DownloadWizardModal } from './DownloadWizardModal';
import { JobMonitorPanel } from './JobMonitorPanel';
import { QualityAndGapView } from './QualityAndGapView';
import { CandleInspectorTable } from './CandleInspectorTable';

type Tab = 'overview' | 'datasets' | 'download' | 'gaps' | 'jobs' | 'candles';

export function HistoricalConsole() {
  const [currentTab, setCurrentTab] = useState<Tab>('overview');
  const [datasets, setDatasets] = useState<HistoricalDataset[]>([]);
  const [jobs, setJobs] = useState<HistoricalDownloadJob[]>([]);
  const [gaps, setGaps] = useState<HistoricalDataGap[]>([]);
  const [inspectTarget, setInspectTarget] = useState({ symbol: 'SENSEX', timeframe: '1m' });
  const [isSyncing, setIsSyncing] = useState(false);

  const loadData = async () => {
    try {
      const [dsRes, jobsRes, gapsRes] = await Promise.all([
        api.getHistoricalDatasets(),
        api.getHistoricalJobs(20),
        api.getHistoricalGaps('SENSEX_1M'),
      ]);

      let loadedDatasets = dsRes.datasets || [];
      // Cold-start fallback: if catalog is empty, trigger an immediate local disk scan
      if (loadedDatasets.length === 0) {
        try {
          const syncRes = await api.syncHistoricalDatasets();
          if (syncRes.datasets && syncRes.datasets.length > 0) {
            loadedDatasets = syncRes.datasets;
          }
        } catch {
          // Keep empty if sync fails
        }
      }

      setDatasets(loadedDatasets);
      setJobs(jobsRes.jobs || []);
      setGaps(gapsRes.gaps || []);
    } catch {
      // Offline / loopback fallback
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSyncDisk = async () => {
    setIsSyncing(true);
    try {
      await api.syncHistoricalDatasets();
      await loadData();
    } catch (err) {
      console.error('Failed to sync historical disk:', err);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSelectInspect = (symbol: string, timeframe: string) => {
    setInspectTarget({ symbol, timeframe });
    setCurrentTab('candles');
  };

  const tabs: { id: Tab; label: string; icon: any }[] = [
    { id: 'overview', label: 'Overview', icon: Database },
    { id: 'datasets', label: 'Datasets', icon: Layers },
    { id: 'download', label: 'Ingestion Wizard', icon: Download },
    { id: 'gaps', label: 'Quality & Gaps', icon: ShieldCheck },
    { id: 'jobs', label: 'Job Monitor', icon: Activity },
    { id: 'candles', label: 'Candle Inspector', icon: Eye },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">
            Historical Data Management
          </h1>
          <p className="text-xs text-muted-foreground">
            Dedicated market data acquisition, two-tier quality validation, Parquet storage & research service.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleSyncDisk}
            disabled={isSyncing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
            title="Scan local disk for Parquet files and hydrate catalog"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? 'animate-spin text-primary' : 'text-muted-foreground'}`} />
            {isSyncing ? 'Scanning...' : 'Rescan Disk'}
          </button>
          <button
            onClick={() => setCurrentTab('download')}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <Download className="h-4 w-4" /> New Ingestion Job
          </button>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex flex-wrap gap-2 border-b border-border pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setCurrentTab(tab.id)}
              className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
              {tab.id === 'gaps' && gaps.length > 0 && (
                <span className="rounded-full bg-bear/20 px-1.5 py-0.2 text-[10px] text-bear">
                  {gaps.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Panels */}
      {currentTab === 'overview' && (
        <DashboardOverview
          datasets={datasets}
          jobs={jobs}
          onNavigateTab={(t) => setCurrentTab(t as Tab)}
          onRefreshData={loadData}
        />
      )}

      {currentTab === 'datasets' && (
        <DatasetCatalogTable
          datasets={datasets}
          onSelectInspect={handleSelectInspect}
          onDatasetUpdated={loadData}
        />
      )}

      {currentTab === 'download' && (
        <DownloadWizardModal
          onJobStarted={() => {
            loadData();
            setCurrentTab('jobs');
          }}
        />
      )}

      {currentTab === 'gaps' && (
        <QualityAndGapView
          gaps={gaps}
          onGapUpdated={loadData}
        />
      )}

      {currentTab === 'jobs' && (
        <JobMonitorPanel
          jobs={jobs}
          onRefresh={loadData}
        />
      )}

      {currentTab === 'candles' && (
        <CandleInspectorTable
          initialSymbol={inspectTarget.symbol}
          initialTimeframe={inspectTarget.timeframe}
        />
      )}
    </div>
  );
}
