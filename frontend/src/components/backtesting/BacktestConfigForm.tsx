'use client';

import { BacktestPayload, BacktestPreset } from '@/lib/types';
import { Play, Settings2, Shield, Percent, DollarSign, Clock } from 'lucide-react';

export function BacktestConfigForm({
  payload,
  presets,
  onChange,
  onRun,
  loading,
}: {
  payload: BacktestPayload;
  presets: BacktestPreset[];
  onChange: (updated: Partial<BacktestPayload>) => void;
  onRun: () => void;
  loading: boolean;
}) {
  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

  const handleSelectPreset = (preset: BacktestPreset) => {
    onChange({
      strategy_id: preset.id,
      underlying: preset.default_underlying,
      stop_loss_pct: preset.default_stop_loss_pct,
      target_pct: preset.default_target_pct,
    });
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Quantitative Strategy Parameters</h3>
        </div>
        <span className="text-[11px] text-muted-foreground">Institutional F&O Simulator</span>
      </div>

      {/* Preset Pills */}
      <div className="space-y-1.5">
        <label className="text-xs font-semibold text-muted-foreground block">Strategy Preset</label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {presets.map((p) => {
            const isSelected = payload.strategy_id === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => handleSelectPreset(p)}
                className={`p-2.5 rounded-lg border text-left transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-primary/10 border-primary text-primary shadow-xs'
                    : 'bg-secondary/40 border-border hover:bg-secondary/70 text-foreground'
                }`}
              >
                <div className="font-bold text-xs">{p.name}</div>
                <div className="text-[10px] text-muted-foreground line-clamp-1 mt-0.5">{p.description}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Parameters Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        {/* Underlying */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Underlying</label>
          <select
            value={payload.underlying}
            onChange={(e) => onChange({ underlying: e.target.value })}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            {symbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        {/* Initial Capital */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold flex items-center gap-1">
            <DollarSign className="w-3 h-3 text-primary" /> Capital (₹)
          </label>
          <input
            type="number"
            value={payload.initial_capital}
            onChange={(e) => onChange({ initial_capital: Number(e.target.value) })}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
          />
        </div>

        {/* Duration / Days */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold flex items-center gap-1">
            <Clock className="w-3 h-3 text-primary" /> Horizon (Days)
          </label>
          <input
            type="number"
            min={10}
            max={365}
            value={payload.num_days}
            onChange={(e) => onChange({ num_days: Number(e.target.value) })}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
          />
        </div>

        {/* Stop Loss % */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold flex items-center gap-1">
            <Shield className="w-3 h-3 text-destructive" /> Stop Loss (%)
          </label>
          <input
            type="number"
            value={payload.stop_loss_pct}
            onChange={(e) => onChange({ stop_loss_pct: Number(e.target.value) })}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
          />
        </div>

        {/* Target % */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold flex items-center gap-1">
            <Percent className="w-3 h-3 text-success" /> Target (%)
          </label>
          <input
            type="number"
            value={payload.target_pct}
            onChange={(e) => onChange({ target_pct: Number(e.target.value) })}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
          />
        </div>

        {/* Slippage % */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Slippage (%)</label>
          <input
            type="number"
            step="0.001"
            value={payload.slippage_pct * 100}
            onChange={(e) => onChange({ slippage_pct: Number(e.target.value) / 100 })}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
          />
        </div>

        {/* Include Costs Toggle */}
        <div className="space-y-1 col-span-2 flex items-center justify-between bg-secondary/30 p-2 rounded-lg border border-border">
          <div>
            <span className="font-semibold text-foreground block">Statutory Taxes & Brokerage</span>
            <span className="text-[10px] text-muted-foreground">STT, NSE, SEBI, GST, Stamp Duty & Brokerage</span>
          </div>
          <input
            type="checkbox"
            checked={payload.include_costs}
            onChange={(e) => onChange({ include_costs: e.target.checked })}
            className="w-4 h-4 accent-primary cursor-pointer"
          />
        </div>
      </div>

      {/* Action Button */}
      <button
        onClick={onRun}
        disabled={loading}
        className="w-full py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50"
      >
        <Play className={`w-4 h-4 fill-current ${loading ? 'animate-spin' : ''}`} />
        <span>{loading ? 'Running Multi-Period Quantitative Simulation...' : 'Run Quantitative Backtest'}</span>
      </button>
    </div>
  );
}
