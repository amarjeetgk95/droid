'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { AlertRule, AlertPayload, AlertTriggerLog, SystemTelemetry } from '@/lib/types';
import { TelemetryStrip } from '@/components/alerts/TelemetryStrip';
import { AlertRuleForm } from '@/components/alerts/AlertRuleForm';
import { AlertRulesTable } from '@/components/alerts/AlertRulesTable';
import { TriggeredFeed } from '@/components/alerts/TriggeredFeed';
import { Play } from 'lucide-react';

export default function AlertsPage() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [history, setHistory] = useState<AlertTriggerLog[]>([]);
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [rulesRes, histRes, telRes] = await Promise.all([
        api.listAlerts(),
        api.getAlertHistory(),
        api.getTelemetry(),
      ]);
      setRules(rulesRes.data);
      setHistory(histRes.data);
      setTelemetry(telRes.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts & telemetry');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;

    const run = async () => {
      try {
        const [rulesRes, histRes, telRes] = await Promise.all([
          api.listAlerts(),
          api.getAlertHistory(),
          api.getTelemetry(),
        ]);
        if (isMounted) {
          setRules(rulesRes.data);
          setHistory(histRes.data);
          setTelemetry(telRes.data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load alerts & telemetry');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    run();
    const interval = setInterval(run, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleCreateRule = async (payload: AlertPayload) => {
    setLoading(true);
    try {
      await api.createAlert(payload);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create alert rule');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleRule = async (id: string) => {
    try {
      await api.toggleAlert(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle alert rule');
    }
  };

  const handleDeleteRule = async (id: string) => {
    try {
      await api.deleteAlert(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete alert rule');
    }
  };

  const handleManualEvaluate = async () => {
    setLoading(true);
    try {
      await api.evaluateAlerts();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Evaluation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Production Telemetry Strip */}
      <TelemetryStrip telemetry={telemetry} />

      {/* Manual Evaluation Trigger Button */}
      <div className="flex items-center justify-between bg-card border border-border rounded-xl p-3 shadow-xs">
        <span className="text-xs text-muted-foreground font-semibold">
          Continuous Automated Rule Evaluation Worker: Active
        </span>
        <button
          onClick={handleManualEvaluate}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5" />
          <span>Trigger Real-Time Evaluation Now</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive text-xs font-semibold">
          {error}
        </div>
      )}

      {/* Form to Create New Rules */}
      <AlertRuleForm onCreate={handleCreateRule} loading={loading} />

      {/* Table of Active Rules */}
      <AlertRulesTable
        rules={rules}
        onToggle={handleToggleRule}
        onDelete={handleDeleteRule}
      />

      {/* Triggered Notifications Feed */}
      <TriggeredFeed history={history} />
    </div>
  );
}
