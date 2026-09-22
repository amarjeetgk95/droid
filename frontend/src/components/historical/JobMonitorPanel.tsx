'use client';

import { useState } from 'react';
import { CheckCircle2, AlertCircle, Clock, RefreshCw, XCircle, StopCircle, Trash2 } from 'lucide-react';
import type { HistoricalDownloadJob } from '@/lib/api/historical';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/toast';

interface JobMonitorPanelProps {
  jobs: HistoricalDownloadJob[];
  onRefresh: () => void;
}

export function JobMonitorPanel({ jobs, onRefresh }: JobMonitorPanelProps) {
  const { push } = useToast();
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleCancelJob = async (jobId: string) => {
    setActionLoading(jobId);
    try {
      await api.cancelHistoricalJob(jobId);
      push('info', 'Job Cancelled', `Job ${jobId} marked as cancelled.`);
      onRefresh();
    } catch (err: any) {
      push('error', 'Cancel Failed', err?.message || 'Failed to cancel job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    setActionLoading(jobId);
    try {
      await api.deleteHistoricalJob(jobId);
      push('info', 'Job Dismissed', 'Job record removed from queue.');
      onRefresh();
    } catch (err: any) {
      push('error', 'Delete Failed', err?.message || 'Failed to delete job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCleanupAll = async () => {
    setActionLoading('cleanup');
    try {
      const res = await api.cleanupHistoricalJobs();
      push('success', 'Queue Reconciled', `Cleaned up ${res.reconciled_count} stale/orphaned jobs.`);
      onRefresh();
    } catch (err: any) {
      push('error', 'Cleanup Failed', err?.message || 'Failed to clean queue');
    } finally {
      setActionLoading(null);
    }
  };

  const getJobStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-bull/10 px-2 py-0.5 text-xs font-medium text-bull">
            <CheckCircle2 className="h-3 w-3" /> Completed
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            <RefreshCw className="h-3 w-3 animate-spin" /> In Progress
          </span>
        );
      case 'QUEUED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            <Clock className="h-3 w-3" /> Queued
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            <XCircle className="h-3 w-3" /> Cancelled
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-bear/10 px-2 py-0.5 text-xs font-medium text-bear">
            <AlertCircle className="h-3 w-3" /> Failed
          </span>
        );
      default:
        return <span className="text-xs text-muted-foreground">{status}</span>;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Ingestion Job Queue</h3>
          <p className="text-xs text-muted-foreground">
            Real-time tracking of broker requests, chunk progress, and automated validation workers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCleanupAll}
            disabled={actionLoading === 'cleanup'}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50"
            title="Reconcile any hung or orphaned jobs"
          >
            <StopCircle className="h-3.5 w-3.5 text-muted-foreground" /> Reconcile Stale
          </button>
          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {jobs.length === 0 ? (
        <div className="p-8 text-center text-xs text-muted-foreground">
          No ingestion jobs have been run yet.
        </div>
      ) : (
        <div className="divide-y divide-border">
          {jobs.map((job) => (
            <div key={job.job_id} className="p-6 transition-colors hover:bg-muted/20">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-bold text-foreground">
                    {job.symbol}
                  </span>
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {job.timeframe}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {job.range_from} &rarr; {job.range_to}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {getJobStatusBadge(job.status)}
                  {(job.status === 'RUNNING' || job.status === 'QUEUED') && (
                    <button
                      onClick={() => handleCancelJob(job.job_id)}
                      disabled={actionLoading === job.job_id}
                      className="inline-flex items-center gap-1 rounded-md border border-bear/30 bg-bear/10 px-2 py-0.5 text-xs font-medium text-bear hover:bg-bear/20 disabled:opacity-50"
                      title="Cancel this download job"
                    >
                      <StopCircle className="h-3 w-3" /> Cancel
                    </button>
                  )}
                  {job.status !== 'RUNNING' && job.status !== 'QUEUED' && (
                    <button
                      onClick={() => handleDeleteJob(job.job_id)}
                      disabled={actionLoading === job.job_id}
                      className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                      title="Dismiss job from history"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {/* Progress Bar */}
              <div className="mt-4">
                <div className="flex justify-between text-xs text-muted-foreground mb-1">
                  <span>
                    Chunks: {job.completed_chunks} / {job.total_chunks}
                  </span>
                  <span>{job.progress_pct}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
                  />
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-6 text-xs text-muted-foreground">
                <span>
                  Rows Downloaded:{' '}
                  <strong className="text-foreground">
                    {job.rows_downloaded.toLocaleString()}
                  </strong>
                </span>
                <span>
                  Valid Rows:{' '}
                  <strong className="text-foreground">
                    {job.rows_valid.toLocaleString()}
                  </strong>
                </span>
                <span>
                  Started: {job.started_at ? new Date(job.started_at).toLocaleTimeString() : 'N/A'}
                </span>
                {job.completed_at && (
                  <span>
                    Completed: {new Date(job.completed_at).toLocaleTimeString()}
                  </span>
                )}
                {job.error_message && (
                  <span className="text-bear font-mono text-[11px]">
                    {job.error_message}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
