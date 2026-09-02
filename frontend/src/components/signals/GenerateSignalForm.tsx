'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { AlertTriangle, Eye, Send, Sparkles, Zap } from 'lucide-react';

const INSTRUMENTS = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as const;
const ENGINES = [
  { id: 'institutional', label: 'Institutional Breakout (recommended)' },
  { id: 'algo', label: 'Algo Fusion (weighted)' },
] as const;
const STATUSES = ['CONFIRMED', 'TRIGGERED', 'POSSIBLE_BREAKOUT', 'POSSIBLE_BREAKDOWN', 'WATCH'] as const;
const DIRECTIONS = ['BULLISH', 'BEARISH'] as const;

type Props = {
  onGenerated?: (result: any) => void;
};

export function GenerateSignalForm({ onGenerated }: Props) {
  const [instrument, setInstrument] = useState<string>('NIFTY');
  const [candleTf, setCandleTf] = useState<string>('5M');
  const [engine, setEngine] = useState<string>('institutional');
  const [status, setStatus] = useState<string>('CONFIRMED');
  const [direction, setDirection] = useState<string>('BULLISH');
  const [triggerLevel, setTriggerLevel] = useState<string>('');
  const [confidence, setConfidence] = useState<string>('82');
  const [breakoutPressure, setBreakoutPressure] = useState<string>('78');
  const [stopLoss, setStopLoss] = useState<string>('');
  const [notifyTelegram, setNotifyTelegram] = useState<boolean>(true);
  const [isLinked, setIsLinked] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Check Telegram link status
  useEffect(() => {
    api
      .getTelegramStatus()
      .then((r: any) => {
        const linked = !!(r.binding?.linked || r.binding?.telegram_chat_id);
        setIsLinked(linked);
        if (!linked) setNotifyTelegram(false);
      })
      .catch(() => setIsLinked(null));
  }, []);

  const doPreview = async () => {
    setPreviewing(true);
    setError(null);
    try {
      const res: any = await api.previewSignal({
        instrument_id: instrument,
        candle_timeframe: candleTf,
        direction,
        status,
        trigger_level: triggerLevel ? Number(triggerLevel) : undefined,
        confidence: confidence ? Number(confidence) : undefined,
        breakout_pressure: breakoutPressure ? Number(breakoutPressure) : undefined,
        stop_loss: stopLoss ? Number(stopLoss) : undefined,
      });
      setPreview(res.preview || res.data?.preview || JSON.stringify(res, null, 2));
    } catch (e: any) {
      setError(e.message || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const doGenerate = async () => {
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const payload: Record<string, any> = {
        instrument_id: instrument,
        candle_timeframe: candleTf,
        engine,
        strategy: 'BREAKOUT',
        direction,
        status,
        trigger_level: triggerLevel ? Number(triggerLevel) : undefined,
        current_price: triggerLevel ? Number(triggerLevel) : undefined,
        confidence: confidence ? Number(confidence) : undefined,
        breakout_pressure: breakoutPressure ? Number(breakoutPressure) : undefined,
        notify_telegram: notifyTelegram,
      };
      if (stopLoss) payload.short_horizon = { stop_loss: Number(stopLoss), status, confidence: Number(confidence) || 75 };
      const res: any = await api.generateSignal(payload);
      setResult(res);
      onGenerated?.(res);
    } catch (e: any) {
      setError(e.message || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" /> Generate Signal
          </CardTitle>
          <CardDescription>
            Creates an authoritative Signal (FSM + TTL 5s) and — if enabled — fans out a <span className="font-mono font-medium">SignalEvent</span> to Telegram via the
            rate-limited queue. Telegram is downstream: failure never blocks creation (§35).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Telegram link banner */}
          {isLinked === false && (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
              <div>
                <p className="font-semibold">Telegram not linked</p>
                <p className="text-muted-foreground">Generate will still succeed, but no Telegram notification will be sent. Link in Settings → Telegram.</p>
              </div>
            </div>
          )}
          {isLinked === true && (
            <div className="rounded border border-emerald-300 bg-emerald-50 p-2 text-xs flex items-center gap-2">
              <Zap className="w-3 h-3 text-emerald-600" /> Telegram linked — notifications will be sent per your preferences (see Settings → Telegram).
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Instrument</label>
              <select value={instrument} onChange={(e) => setInstrument(e.target.value)} className="h-8 rounded border px-2 text-sm bg-background">
                {INSTRUMENTS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Timeframe §13</label>
              <select value={candleTf} onChange={(e) => setCandleTf(e.target.value)} className="h-8 rounded border px-2 text-sm bg-background">
                <option value="1M">1M — ⚡</option>
                <option value="5M">5M — 🟢/🔴</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Engine</label>
              <select value={engine} onChange={(e) => setEngine(e.target.value)} className="h-8 rounded border px-2 text-sm bg-background">
                {ENGINES.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Status</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 rounded border px-2 text-sm bg-background">
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Direction</label>
              <select value={direction} onChange={(e) => setDirection(e.target.value)} className="h-8 rounded border px-2 text-sm bg-background">
                {DIRECTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Trigger Level</label>
              <input value={triggerLevel} onChange={(e) => setTriggerLevel(e.target.value)} placeholder="e.g. 24885" className="h-8 rounded border px-2 text-sm" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Stop Loss</label>
              <input value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} placeholder="e.g. 24700" className="h-8 rounded border px-2 text-sm" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Confidence %</label>
              <input value={confidence} onChange={(e) => setConfidence(e.target.value)} placeholder="82" className="h-8 rounded border px-2 text-sm" />
            </div>
          </div>

          <div className="flex items-center gap-2 rounded border p-2 bg-secondary/30">
            <input id="notify-telegram" type="checkbox" checked={notifyTelegram} onChange={(e) => setNotifyTelegram(e.target.checked)} className="h-4 w-4" />
            <label htmlFor="notify-telegram" className="text-sm font-medium flex items-center gap-1.5">
              <Send className="w-3.5 h-3.5" /> Send to Telegram after generation
            </label>
            <span className="text-xs text-muted-foreground ml-2 hidden sm:inline">
              Uses <code className="bg-muted px-1 rounded">should_publish_instrument_event 60s</code> + per-user prefs + dedup
            </span>
          </div>

          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" size="sm" onClick={doPreview} disabled={previewing}>
              <Eye className="w-4 h-4 mr-1" />
              {previewing ? 'Previewing…' : 'Preview Telegram Message'}
            </Button>
            <Button size="sm" onClick={doGenerate} disabled={generating}>
              <Zap className="w-4 h-4 mr-1" />
              {generating ? 'Generating…' : 'Generate & Notify'}
            </Button>
          </div>

          {error && <div className="rounded bg-destructive/10 border border-destructive/20 p-2 text-xs text-destructive">{error}</div>}

          {preview && (
            <div className="rounded border bg-muted/30 p-3">
              <div className="text-xs font-semibold tracking-widest mb-2 flex items-center gap-2">
                <Eye className="w-3 h-3" /> TELEGRAM PREVIEW — exactly what will be sent
              </div>
              <pre className="text-xs font-mono whitespace-pre-wrap break-words bg-background rounded p-3 border max-h-64 overflow-auto">{preview}</pre>
              <p className="text-[11px] text-muted-foreground mt-1">1M messages show ⚡, 5M show 🟢/🔴 per telegram_templates.py:41. No data is invented — only SignalEvent fields.</p>
            </div>
          )}

          {result && (
            <div className="rounded border border-emerald-300 bg-emerald-50 p-3 space-y-2">
              <div className="text-sm font-semibold flex items-center gap-2">
                ✅ Signal Generated <Badge variant="outline">{result.signal?.signal_id?.slice(0, 8)}…</Badge>{' '}
                <Badge className="bg-emerald-600 text-white">{result.signal?.status}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div>Signal ID: {result.signal?.signal_id}</div>
                <div>FSM: {result.signal?.fsm_state || result.signal_obj?.fsm_state}</div>
                <div>
                  TTL: {result.signal?.ttl_ms}ms • {result.ttl_remaining_ms}ms left • {result.is_expired ? 'EXPIRED' : 'VALID'}
                </div>
                <div>Telegram enqueued: {result.telegram?.enqueued ?? 0}</div>
              </div>
              {result.telegram?.notification_ids?.length > 0 && (
                <div className="text-xs">
                  <span className="font-semibold">Notification IDs:</span>{' '}
                  <span className="font-mono">{result.telegram.notification_ids.join(', ')}</span>
                </div>
              )}
              {result.telegram?.skipped_reason && (
                <div className="text-xs text-amber-700">Telegram note: {result.telegram.skipped_reason}</div>
              )}
              <p className="text-[11px] text-muted-foreground">
                Check Settings → Telegram → Audit for delivery status (SENT / FAILED / SKIPPED / DEDUPED). Re-generating same signal within 60s is throttled per
                instrument.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
