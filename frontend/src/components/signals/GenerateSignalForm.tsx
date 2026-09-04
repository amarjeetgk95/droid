'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { AlertTriangle, Crosshair, Eye, RefreshCw, Send, Sparkles, Wand2, Zap } from 'lucide-react';

const UNDERLYINGS = ['NIFTY', 'BANKNIFTY', 'SENSEX'] as const;
const STRATEGIES = [
  { id: 'BREAKOUT', label: 'Institutional Breakout (S/R Volume)', desk: 'INTRADAY' },
  { id: 'MEAN_REVERSION', label: 'Mean Reversion (Bollinger/RSI Exhaustion)', desk: 'INTRADAY' },
  { id: 'TREND_PULLBACK', label: 'Trend Pullback (20 EMA Retest)', desk: 'INTRADAY' },
  { id: 'GAMMA_SQUEEZE', label: 'Gamma Squeeze (0DTE OI Unwinding)', desk: 'INTRADAY' },
  { id: 'ORB', label: 'Opening Range Breakout (15M High/Low)', desk: 'INTRADAY' },
  { id: 'VWAP_REJECTION', label: '⚡ VWAP Rejection (Mean Reversion Scalp)', desk: 'SCALP' },
  { id: 'MICRO_MOMENTUM', label: '⚡ Micro-Momentum (Breakout Scalp)', desk: 'SCALP' },
  { id: 'EMA_RIBBON', label: '⚡ EMA Ribbon (Pullback Scalp)', desk: 'SCALP' },
  { id: 'GAMMA_SPIKE', label: '⚡ Expiry Gamma Spike (0-DTE Scalp)', desk: 'SCALP' },
] as const;
const DIRECTIONS = [
  { id: 'LONG_CALL', label: 'LONG_CALL (Bullish Call Option)' },
  { id: 'LONG_PUT', label: 'LONG_PUT (Bearish Put Option)' },
] as const;

type Props = {
  onGenerated?: (result: any) => void;
};

export function GenerateSignalForm({ onGenerated }: Props) {
  const [underlying, setUnderlying] = useState<string>('NIFTY');
  const [strategy, setStrategy] = useState<string>('BREAKOUT');
  const [direction, setDirection] = useState<string>('LONG_CALL');
  const [timeframe, setTimeframe] = useState<string>('5M');
  
  const [triggerLevel, setTriggerLevel] = useState<string>('24900');
  const [stopLoss, setStopLoss] = useState<string>('24850');
  const [target1, setTarget1] = useState<string>('24975');
  const [target2, setTarget2] = useState<string>('25050');
  const [confidence, setConfidence] = useState<string>('85');
  const [lots, setLots] = useState<string>('2');
  
  const [executePaper, setExecutePaper] = useState<boolean>(true);
  const [notifyTelegram, setNotifyTelegram] = useState<boolean>(true);
  const [isLinked, setIsLinked] = useState<boolean | null>(null);

  const [autoDetecting, setAutoDetecting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

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

  const handleAutoDetect = async () => {
    setAutoDetecting(true);
    setError(null);
    try {
      const res = await api.autoDetectSignal({ underlying, strategy, timeframe });
      if (res && res.candidate) {
        const c = res.candidate;
        setDirection(c.direction || 'LONG_CALL');
        setTriggerLevel(String(c.trigger || c.spot_price));
        setStopLoss(String(c.stop_loss));
        setTarget1(String(c.target_1));
        setTarget2(String(c.target_2));
        setConfidence(String(c.confidence || 80));
      }
    } catch (e: any) {
      setError(e.message || 'Auto-detect failed');
    } finally {
      setAutoDetecting(false);
    }
  };

  const doPreview = async () => {
    setPreviewing(true);
    setError(null);
    try {
      const res: any = await api.previewSignal({
        instrument_id: underlying,
        candle_timeframe: timeframe,
        direction: direction.includes('CALL') ? 'BULLISH' : 'BEARISH',
        status: 'CONFIRMED',
        trigger_level: triggerLevel ? Number(triggerLevel) : undefined,
        stop_loss: stopLoss ? Number(stopLoss) : undefined,
        confidence: confidence ? Number(confidence) : undefined,
      });
      setPreview(res.preview || res.data?.preview || JSON.stringify(res, null, 2));
    } catch (e: any) {
      setError(e.message || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const handleStrategySelect = (val: string) => {
    setStrategy(val);
    const isScalp = ['VWAP_REJECTION', 'MICRO_MOMENTUM', 'EMA_RIBBON', 'GAMMA_SPIKE'].includes(val);
    if (isScalp && timeframe !== '1M' && timeframe !== '3M') {
      setTimeframe('1M');
    } else if (!isScalp && (timeframe === '1M' || timeframe === '3M')) {
      setTimeframe('5M');
    }
  };

  const doGenerate = async () => {
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const isScalp = ['VWAP_REJECTION', 'MICRO_MOMENTUM', 'EMA_RIBBON', 'GAMMA_SPIKE'].includes(strategy) || timeframe === '1M' || timeframe === '3M';
      const payload: Record<string, any> = {
        underlying,
        strategy,
        direction,
        timeframe,
        is_scalp: isScalp,
        signal_type: isScalp ? 'SCALP' : 'INTRADAY',
        time_stop_seconds: isScalp ? 180 : 3600,
        runner_ttl_seconds: isScalp ? 300 : undefined,
        trigger: triggerLevel ? Number(triggerLevel) : undefined,
        entry_min: triggerLevel ? Number(triggerLevel) : undefined,
        entry_max: triggerLevel ? Number(triggerLevel) + 10.0 : undefined,
        stop_loss: stopLoss ? Number(stopLoss) : undefined,
        target_1: target1 ? Number(target1) : undefined,
        target_2: target2 ? Number(target2) : undefined,
        confidence: confidence ? Number(confidence) : 80.0,
        execute_paper: executePaper,
        lots: lots ? Number(lots) : 2,
        notify_telegram: notifyTelegram,
      };
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
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" /> Signal Studio & Strategy Builder
              </CardTitle>
              <CardDescription>
                Deterministic quantitative setup generator with dynamic FYERS option resolution and FSM lifecycle tracking.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleAutoDetect}
              disabled={autoDetecting}
              className="h-8 text-xs bg-primary/5 hover:bg-primary/10 text-primary border-primary/30 font-semibold gap-1.5"
            >
              <Wand2 className={`w-3.5 h-3.5 ${autoDetecting ? 'animate-spin' : ''}`} />
              {autoDetecting ? 'Analyzing Market…' : '⚡ Auto-Detect Live Setup'}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted-foreground">Underlying Index</label>
              <select
                value={underlying}
                onChange={(e) => setUnderlying(e.target.value)}
                className="h-8 rounded-lg border px-2 text-xs bg-background font-semibold"
              >
                {UNDERLYINGS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted-foreground">Quant Strategy</label>
              <select
                value={strategy}
                onChange={(e) => handleStrategySelect(e.target.value)}
                className="h-8 rounded-lg border px-2 text-xs bg-background"
              >
                {STRATEGIES.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted-foreground">Trade Direction</label>
              <select
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
                className="h-8 rounded-lg border px-2 text-xs bg-background font-bold text-primary"
              >
                {DIRECTIONS.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted-foreground">Timeframe</label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="h-8 rounded-lg border px-2 text-xs bg-background font-mono"
              >
                <option value="1M">1M (Scalp)</option>
                <option value="3M">3M (Scalp)</option>
                <option value="5M">5M (Standard)</option>
                <option value="15M">15M (Swing)</option>
                <option value="1H">1H (Positional)</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted-foreground">Trigger Level (₹)</label>
              <input
                value={triggerLevel}
                onChange={(e) => setTriggerLevel(e.target.value)}
                placeholder="24900"
                className="h-8 rounded-lg border px-2 text-xs font-mono"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-destructive">Stop Loss (₹)</label>
              <input
                value={stopLoss}
                onChange={(e) => setStopLoss(e.target.value)}
                placeholder="24850"
                className="h-8 rounded-lg border px-2 text-xs font-mono text-destructive font-bold"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-emerald-600">Target 1 (1.5R)</label>
              <input
                value={target1}
                onChange={(e) => setTarget1(e.target.value)}
                placeholder="24975"
                className="h-8 rounded-lg border px-2 text-xs font-mono text-emerald-600 font-bold"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-emerald-700">Target 2 (3.0R)</label>
              <input
                value={target2}
                onChange={(e) => setTarget2(e.target.value)}
                placeholder="25050"
                className="h-8 rounded-lg border px-2 text-xs font-mono text-emerald-700 font-bold"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
            <div className="flex items-center gap-2 rounded-lg border p-2.5 bg-emerald-500/10 border-emerald-500/20">
              <input
                id="execute-paper"
                type="checkbox"
                checked={executePaper}
                onChange={(e) => setExecutePaper(e.target.checked)}
                className="h-4 w-4 accent-emerald-600"
              />
              <label htmlFor="execute-paper" className="text-xs font-semibold flex items-center gap-1.5 cursor-pointer">
                <Zap className="w-3.5 h-3.5 text-emerald-600" /> Execute Paper Order on the spot
              </label>
              <input
                type="number"
                min="1"
                max="20"
                value={lots}
                onChange={(e) => setLots(e.target.value)}
                className="ml-auto w-16 h-7 rounded border px-1.5 text-xs font-mono bg-background"
                placeholder="Lots"
              />
              <span className="text-[11px] text-muted-foreground">Lots</span>
            </div>

            <div className="flex items-center gap-2 rounded-lg border p-2.5 bg-secondary/40">
              <input
                id="notify-telegram"
                type="checkbox"
                checked={notifyTelegram}
                onChange={(e) => setNotifyTelegram(e.target.checked)}
                className="h-4 w-4"
              />
              <label htmlFor="notify-telegram" className="text-xs font-semibold flex items-center gap-1.5 cursor-pointer">
                <Send className="w-3.5 h-3.5 text-primary" /> Send to Telegram Notifier
              </label>
            </div>
          </div>

          <div className="flex gap-2 flex-wrap pt-2">
            <Button variant="outline" size="sm" onClick={doPreview} disabled={previewing} className="h-8 text-xs">
              <Eye className="w-3.5 h-3.5 mr-1" />
              {previewing ? 'Previewing…' : 'Preview Telegram Alert'}
            </Button>
            <Button size="sm" onClick={doGenerate} disabled={generating} className="h-8 text-xs gap-1">
              <Sparkles className="w-3.5 h-3.5" />
              {generating ? 'Generating Signal…' : 'Generate & Publish Signal'}
            </Button>
          </div>

          {error && <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-2.5 text-xs text-destructive">{error}</div>}

          {preview && (
            <div className="rounded-lg border bg-muted/30 p-3 space-y-1">
              <div className="text-[11px] font-bold text-muted-foreground uppercase flex items-center gap-1.5">
                <Eye className="w-3 h-3 text-primary" /> Telegram Alert Markdown Preview
              </div>
              <pre className="text-xs font-mono whitespace-pre-wrap break-words bg-background rounded-md p-3 border max-h-48 overflow-auto">{preview}</pre>
            </div>
          )}

          {result && (
            <div className="rounded-lg border border-emerald-300 bg-emerald-50/80 p-3 space-y-2">
              <div className="text-sm font-bold flex items-center gap-2 text-emerald-900">
                ✅ Signal Registered <Badge variant="outline">{result.signal?.signal_id?.slice(0, 8)}…</Badge>
                <Badge className="bg-emerald-600 text-white">{result.signal?.fsm_state || 'ARMED'}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs font-mono text-emerald-800">
                <div>Underlying: {result.signal?.underlying} ({result.signal?.strategy})</div>
                <div>Risk:Reward: 1:{result.signal?.risk_reward_t2}</div>
                <div>Trigger: ₹{result.signal?.trigger}</div>
                <div>Confidence: {result.signal?.confidence}%</div>
              </div>
              {result.paper_order && (
                <div className="rounded border border-emerald-400 bg-emerald-100 p-2 text-xs font-mono text-emerald-900 font-bold">
                  ⚡ Paper Order Filled: {result.paper_order.side} {result.paper_order.quantity} Qty @ ₹{result.paper_order.fill_price} (Order: {result.paper_order.order_id})
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
