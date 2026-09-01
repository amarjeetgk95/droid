'use client';

import { useEffect, useState, useCallback } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { SignalCard, type SignalDTO } from '@/components/signals/SignalCard';
import { GenerateSignalForm } from '@/components/signals/GenerateSignalForm';
import { Activity, RefreshCw, Radio, AlertTriangle, Clock, History as HistoryIcon, Settings as SettingsIcon } from 'lucide-react';
import Link from 'next/link';

type FilterInstrument = 'ALL' | 'NIFTY' | 'BANKNIFTY' | 'SENSEX' | 'BTCUSD';
type FilterStatus = 'ALL' | 'CONFIRMED' | 'TRIGGERED' | 'POSSIBLE_BREAKOUT' | 'POSSIBLE_BREAKDOWN' | 'WATCH' | 'NO_SETUP';

export default function SignalsPage() {
  const [active, setActive] = useState<SignalDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterInstr, setFilterInstr] = useState<FilterInstrument>('ALL');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('ALL');
  const [history, setHistory] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [telegramAudit, setTelegramAudit] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchActive = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const res: any = await api.getSignalsActive({
        instrument: filterInstr !== 'ALL' ? filterInstr : undefined,
        status: filterStatus !== 'ALL' ? filterStatus : undefined,
      });
      const payload = res.signals ?? res.data?.signals ?? res ?? [];
      const list: SignalDTO[] = Array.isArray(payload) ? payload : payload.signals || [];
      setActive(list);
    } catch (e: any) {
      setError(e.message || 'Failed to load signals');
    } finally {
      setLoading(false);
    }
  }, [filterInstr, filterStatus]);

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res: any = await api.getSignalsHistory(20);
      setHistory(res.records || res.data?.records || res.data || []);
      // also telegram audit
      try {
        const aud: any = await api.getTelegramAudit(20);
        setTelegramAudit(aud.records || aud.data?.records || []);
      } catch {}
    } catch {}
    finally { setHistoryLoading(false); }
  }, []);

  // Initial + poll active every 4s
  useEffect(() => {
    fetchActive(true);
    const id = setInterval(() => fetchActive(false), 4000);
    return () => clearInterval(id);
  }, [fetchActive]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const filtered = active; // server already filtered

  return (
    <div className="space-y-4 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <Radio className="w-5 h-5 text-primary" /> Signal Center
          <Badge variant="outline" className="ml-2 text-[10px]">NEW</Badge>
          <span className="text-xs font-normal text-muted-foreground ml-2 hidden sm:inline">
            Generate → FSM + TTL 5s → Telegram (rate-limited, deduped)
          </span>
        </h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => fetchActive(true)} className="h-8 text-xs">
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </Button>
          <Link href="/settings">
            <Button variant="ghost" size="sm" className="h-8 text-xs">
              <SettingsIcon className="w-3 h-3 mr-1" /> Telegram Settings
            </Button>
          </Link>
        </div>
      </div>

      <Tabs defaultValue="active" className="w-full">
        <TabsList className="w-full justify-start flex-wrap h-auto">
          <TabsTrigger value="active" className="gap-1.5">
            <Activity className="w-3.5 h-3.5" /> Active Signals
          </TabsTrigger>
          <TabsTrigger value="generate" className="gap-1.5">
            <Radio className="w-3.5 h-3.5" /> Generate
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-1.5">
            <HistoryIcon className="w-3.5 h-3.5" /> History & Audit
          </TabsTrigger>
        </TabsList>

        {/* ── ACTIVE ── */}
        <TabsContent value="active" className="space-y-4 pt-2">
          {/* Filters */}
          <Card>
            <CardContent className="pt-4 flex flex-wrap gap-2 items-center">
              <span className="text-xs font-semibold text-muted-foreground">Instrument:</span>
              {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilterInstr(f)}
                  className={`px-3 py-1 text-xs font-bold rounded border ${filterInstr === f ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary border-transparent hover:bg-accent'}`}
                >
                  {f}
                </button>
              ))}
              <span className="text-xs font-semibold text-muted-foreground ml-2">Status:</span>
              {(['ALL', 'CONFIRMED', 'TRIGGERED', 'POSSIBLE_BREAKOUT', 'WATCH'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilterStatus(s as any)}
                  className={`px-2.5 py-1 text-xs font-medium rounded border ${filterStatus === s ? 'bg-primary text-primary-foreground border-primary' : 'bg-secondary border-transparent hover:bg-accent'}`}
                >
                  {s}
                </button>
              ))}
              <span className="ml-auto text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" /> Polling 4s • {active.length} signals
              </span>
            </CardContent>
          </Card>

          {loading && active.length === 0 && (
            <Card>
              <CardContent className="pt-6">
                <div className="animate-pulse space-y-3">
                  <div className="h-4 bg-muted rounded w-32" />
                  <div className="h-20 bg-muted rounded" />
                </div>
              </CardContent>
            </Card>
          )}

          {error && (
            <div className="rounded border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {error}
            </div>
          )}

          {!loading && filtered.length === 0 && !error && (
            <Card>
              <CardContent className="pt-6 text-sm text-muted-foreground text-center">
                No signals match filters — try <code className="bg-muted px-1 rounded">ALL</code> or generate one in the Generate tab.
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filtered.map((sig) => (
              <SignalCard key={sig.signal_id} signal={sig} />
            ))}
          </div>

          <Card className="border-dashed">
            <CardContent className="pt-4 text-[11px] text-muted-foreground">
              Active signals are authoritative — generated by <code className="bg-muted px-1 rounded">signal_center</code> or <code className="bg-muted px-1 rounded">/api/v1/signals/generate</code> and stored in{' '}
              <code className="bg-muted px-1 rounded">signal_fsm</code>. Expired signals show <Badge variant="outline" className="text-[10px]">EXPIRED</Badge> and are non-actionable
              (TTL 5s). Any <code className="bg-muted px-1 rounded">CONFIRMED</code> created via Generate with <em>Send to Telegram</em> fans out to all linked chats via the rate-limited queue.
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── GENERATE ── */}
        <TabsContent value="generate" className="pt-2">
          <GenerateSignalForm onGenerated={() => { fetchActive(false); fetchHistory(); }} />
          <Card className="mt-4 border-dashed">
            <CardHeader>
              <CardTitle className="text-sm">How Telegram delivery works</CardTitle>
              <CardDescription className="text-xs">
                Signal Engine → <code className="bg-muted px-1 rounded">SignalEvent</code> → <code className="bg-muted px-1 rounded">telegram_notification_queue.publish_signal_event</code> → per-user{' '}
                <code className="bg-muted px-1 rounded">NotificationPreferences</code> + dedup + throttle → <code className="bg-muted px-1 rounded">telegram_outbound_queue</code> (global 20/s,
                per-chat 1/s) → <code className="bg-muted px-1 rounded">httpx</code> → Telegram API. Preview shows exactly what will be sent (templates never invent data).
              </CardDescription>
            </CardHeader>
          </Card>
        </TabsContent>

        {/* ── HISTORY & TELEGRAM AUDIT ── */}
        <TabsContent value="history" className="space-y-4 pt-2">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <HistoryIcon className="w-4 h-4" /> Signal Audit (recent 20)
                </CardTitle>
                <CardDescription className="text-xs">Append-only trail — why entered/rejected, scores, TTL.</CardDescription>
              </CardHeader>
              <CardContent>
                {historyLoading ? (
                  <div className="text-xs text-muted-foreground">Loading…</div>
                ) : history.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No records yet — generate a signal.</div>
                ) : (
                  <div className="max-h-96 overflow-auto rounded border">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-muted">
                        <tr>
                          <th className="p-2 text-left">Signal ID</th>
                          <th className="p-2">Instrument</th>
                          <th className="p-2">State</th>
                          <th className="p-2">TTL</th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((r: any, i: number) => (
                          <tr key={i} className="border-t">
                            <td className="p-2 font-mono text-[11px]">{String(r.signal_id || r.signalId || '').slice(0, 8)}…</td>
                            <td className="p-2 text-center">{String(r.instrument_id || r.instrument || '—')}</td>
                            <td className="p-2 text-center">
                              <Badge variant="outline" className="text-[11px]">
                                {String(r.final_state || r.status || '—')}
                              </Badge>
                            </td>
                            <td className="p-2 text-center font-mono">{String(r.ttl_ms || '—')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <Radio className="w-4 h-4" /> Telegram Audit (recent 20)
                </CardTitle>
                <CardDescription className="text-xs">PENDING / SENT / FAILED / SKIPPED / DEDUPED per notification.</CardDescription>
              </CardHeader>
              <CardContent>
                {telegramAudit.length === 0 ? (
                  <div className="text-xs text-muted-foreground">
                    No Telegram deliveries yet. Link Telegram in Settings and generate with <em>Send to Telegram</em> enabled.
                  </div>
                ) : (
                  <div className="max-h-96 overflow-auto rounded border">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-muted">
                        <tr>
                          <th className="p-2 text-left">Notification</th>
                          <th className="p-2">Event</th>
                          <th className="p-2">Status</th>
                          <th className="p-2">Attempts</th>
                        </tr>
                      </thead>
                      <tbody>
                        {telegramAudit.map((r: any, i: number) => (
                          <tr key={i} className="border-t">
                            <td className="p-2 font-mono text-[11px]">{String(r.notification_id || '').slice(0, 8)}…</td>
                            <td className="p-2 text-center">{String(r.event_type || '—')}</td>
                            <td className="p-2 text-center">
                              <Badge
                                variant={r.delivery_status === 'SENT' ? 'default' : r.delivery_status === 'FAILED' ? 'destructive' : 'secondary'}
                                className="text-[11px]"
                              >
                                {String(r.delivery_status)}
                              </Badge>
                            </td>
                            <td className="p-2 text-center">{String(r.attempt_count ?? '—')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
