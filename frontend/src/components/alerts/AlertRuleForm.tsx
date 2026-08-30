'use client';

import { useState } from 'react';
import { AlertPayload } from '@/lib/types';
import { BellPlus, Plus } from 'lucide-react';

export function AlertRuleForm({
  onCreate,
  loading,
}: {
  onCreate: (payload: AlertPayload) => void;
  loading: boolean;
}) {
  const [name, setName] = useState('NIFTY Squeeze Breakout Alert');
  const [symbol, setSymbol] = useState('NIFTY');
  const [alertType, setAlertType] = useState<AlertPayload['alert_type']>('VOLATILITY_SQUEEZE');
  const [condition, setCondition] = useState<AlertPayload['condition']>('LESS_THAN');
  const [threshold, setThreshold] = useState(2.2);
  const [channel, setChannel] = useState<AlertPayload['channel']>('IN_APP');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onCreate({
      name: name.trim(),
      symbol: symbol.toUpperCase(),
      alert_type: alertType,
      condition,
      threshold: Number(threshold),
      channel,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center gap-2">
        <BellPlus className="w-4 h-4 text-primary" />
        <h3 className="font-bold text-sm text-foreground">Create Real-Time Alert Rule</h3>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
        {/* Rule Name */}
        <div className="space-y-1 sm:col-span-2">
          <label className="text-muted-foreground font-semibold">Rule Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden"
            placeholder="e.g. NIFTY Squeeze Breakout"
            required
          />
        </div>

        {/* Symbol */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Underlying</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            <option value="NIFTY">NIFTY</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
            <option value="FINNIFTY">FINNIFTY</option>
            <option value="SENSEX">SENSEX</option>
          </select>
        </div>

        {/* Alert Type */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Metric / Type</label>
          <select
            value={alertType}
            onChange={(e) => setAlertType(e.target.value as AlertPayload['alert_type'])}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            <option value="VOLATILITY_SQUEEZE">Volatility Squeeze (Bandwidth %)</option>
            <option value="PRICE_LEVEL">Spot Price Level</option>
            <option value="PCR_THRESHOLD">Put-Call Ratio (PCR)</option>
            <option value="MAX_PAIN_SHIFT">Max Pain Strike</option>
          </select>
        </div>

        {/* Condition */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Trigger Condition</label>
          <select
            value={condition}
            onChange={(e) => setCondition(e.target.value as AlertPayload['condition'])}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            <option value="GREATER_THAN">Greater Than or Equal (&gt;=)</option>
            <option value="LESS_THAN">Less Than or Equal (&lt;=)</option>
            <option value="CROSSES_ABOVE">Crosses Above</option>
            <option value="CROSSES_BELOW">Crosses Below</option>
          </select>
        </div>

        {/* Threshold */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Threshold Value</label>
          <input
            type="number"
            step="0.05"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden"
            required
          />
        </div>

        {/* Channel */}
        <div className="space-y-1">
          <label className="text-muted-foreground font-semibold">Channel</label>
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value as AlertPayload['channel'])}
            className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            <option value="IN_APP">In-App Notification</option>
            <option value="WEBHOOK">Webhook (HTTP)</option>
            <option value="TELEGRAM">Telegram</option>
            <option value="EMAIL">Email</option>
          </select>
        </div>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="w-full py-2 bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50"
      >
        <Plus className="w-4 h-4" />
        <span>Add Alert Rule</span>
      </button>
    </form>
  );
}
