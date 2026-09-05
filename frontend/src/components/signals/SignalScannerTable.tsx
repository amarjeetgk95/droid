'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Crosshair,
  ExternalLink,
  RefreshCw,
  Search,
  Zap,
} from 'lucide-react';
import { SignalDTO } from './SignalCard';
import { safeNum, safeState, formatDateTime } from '@/lib/signal-utils';

const STRATEGY_FILTERS = ['ALL', 'BREAKOUT', 'MEAN_REVERSION', 'TREND_PULLBACK', 'GAMMA_SQUEEZE', 'ORB', 'VWAP_SCALP', 'MICRO_MOMENTUM', 'EMA_RIBBON', 'GAMMA_SPIKE'];

interface Props {
  signals: SignalDTO[];
  onInspect: (signalId: string) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

export function SignalScannerTable({ signals, onInspect, onRefresh, loading }: Props) {
  const [searchTerm, setSearchTerm] = useState('');
  const [strategyFilter, setStrategyFilter] = useState('ALL');
  const [executingId, setExecutingId] = useState<string | null>(null);

  const filtered = (signals || []).filter((s) => {
    const underlying = String(s?.underlying || '').toLowerCase();
    const strategy = String(s?.strategy || '').toLowerCase();
    const matchesSearch = underlying.includes(searchTerm.toLowerCase()) || strategy.includes(searchTerm.toLowerCase());
    const matchesStrat = strategyFilter === 'ALL' || s?.strategy === strategyFilter;
    return matchesSearch && matchesStrat;
  });

  const handleExecutePaper = async (sigId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExecutingId(sigId);
    try {
      await api.executeSignalPaper(sigId);
      onRefresh?.();
    } catch {
    } finally {
      setExecutingId(null);
    }
  };

  return (
    <div className="space-y-3">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap flex-1">
          <div className="relative flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Filter NIFTY, BANKNIFTY, SENSEX…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-8 pl-8 pr-3 text-xs rounded-lg border bg-background w-full"
            />
          </div>

          <div className="flex items-center gap-1 overflow-x-auto">
            {STRATEGY_FILTERS.map((st) => (
              <button
                key={st}
                onClick={() => setStrategyFilter(st)}
                className={`px-2.5 py-1 text-[11px] font-mono rounded-md border transition-all ${strategyFilter === st ? 'bg-primary text-primary-foreground border-primary font-bold' : 'bg-secondary/60 hover:bg-secondary border-transparent'}`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} className="h-8 text-xs gap-1">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Scan Radar
        </Button>
      </div>

      {/* Table Container */}
      <div className="rounded-xl border overflow-x-auto bg-card shadow-sm">
        <table className="w-full text-xs">
          <thead className="bg-muted/50 border-b text-muted-foreground font-semibold">
            <tr>
              <th className="p-3 text-left">Underlying</th>
              <th className="p-3 text-left">Strategy</th>
              <th className="p-3 text-left">Direction</th>
              <th className="p-3 text-right">Spot Price</th>
              <th className="p-3 text-right">Trigger Level</th>
              <th className="p-3 text-right">Stop Loss</th>
              <th className="p-3 text-right">Target 1 & 2</th>
              <th className="p-3 text-center">R:R</th>
              <th className="p-3 text-center">Confidence</th>
              <th className="p-3 text-center">State</th>
              <th className="p-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y font-mono">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={11} className="p-8 text-center text-muted-foreground font-sans">
                  No active setups match criteria. Run a scan across NIFTY, BANKNIFTY, SENSEX.
                </td>
              </tr>
            ) : (
              filtered.map((s) => {
                if (!s?.signal_id) return null;
                const isCall = s.direction?.includes('CALL');
                const fsm = safeState(s.fsm_state);
                return (
                  <tr
                    key={s.signal_id}
                    className="hover:bg-muted/40 cursor-pointer transition-colors"
                    onClick={() => onInspect(s.signal_id)}
                  >
                    <td className="p-3 font-bold font-sans">
                      <div className="flex items-center gap-1.5">
                        <span>{s.underlying}</span>
                        <span className="text-[10px] text-muted-foreground font-mono bg-secondary px-1 py-0.5 rounded">
                          {s.timeframe || '5M'}
                        </span>
                      </div>
                      {s.created_at_utc ? (
                        <div className="text-[10px] text-muted-foreground font-mono font-normal mt-0.5" title="Generated Date & Time (IST)">
                          {formatDateTime(s.created_at_utc)}
                        </div>
                      ) : null}
                    </td>
                    <td className="p-3">
                      <Badge variant="outline" className="text-[10px] font-mono">
                        {s.strategy}
                      </Badge>
                    </td>
                    <td className="p-3 font-sans">
                      <span className={`flex items-center gap-0.5 font-bold ${isCall ? 'text-emerald-600' : 'text-red-600'}`}>
                        {isCall ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                        {s.direction}
                      </span>
                    </td>
                    <td className="p-3 text-right font-medium">₹{safeNum(s.spot_price)}</td>
                    <td className="p-3 text-right font-bold text-foreground">
                      <div>₹{safeNum(s.trigger)}</div>
                      {typeof s.distance_to_trigger_pts === 'number' && Number.isFinite(s.distance_to_trigger_pts) && (
                        <div className="text-[10px] text-muted-foreground font-normal">
                          {s.distance_to_trigger_pts.toFixed(1)} pts away
                        </div>
                      )}
                    </td>
                    <td className="p-3 text-right text-destructive font-semibold">₹{safeNum(s.stop_loss)}</td>
                    <td className="p-3 text-right text-emerald-600 font-semibold">
                      <div>₹{safeNum(s.target_1)} (T1)</div>
                      <div className="text-[10px] text-emerald-700 font-bold">₹{safeNum(s.target_2)} (T2)</div>
                    </td>
                    <td className="p-3 text-center font-bold text-emerald-600">1:{safeNum(s.risk_reward_t2 ?? 3.0, 1)}</td>
                    <td className="p-3 text-center font-bold text-primary">{safeNum(s.confidence, 1)}%</td>
                    <td className="p-3 text-center">
                      <Badge
                        variant={fsm.includes('TARGET') ? 'default' : fsm === 'STOP_LOSS_HIT' ? 'destructive' : 'outline'}
                        className="text-[10px]"
                      >
                        {fsm}
                      </Badge>
                    </td>
                    <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                      {s.paper_order ? (
                        <span className="text-emerald-600 font-bold text-[10px] flex items-center justify-end gap-1">
                          <CheckCircle2 className="w-3 h-3" /> Filled
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-[11px] bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-300 font-medium gap-1 px-2"
                          onClick={(e) => handleExecutePaper(s.signal_id, e)}
                          disabled={executingId === s.signal_id}
                        >
                          <Zap className="w-3 h-3" /> {executingId === s.signal_id ? '…' : 'Paper Trade'}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
