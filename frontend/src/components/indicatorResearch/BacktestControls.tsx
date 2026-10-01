'use client';

import type { SettingsState } from '@/hooks/useIndicatorResearch';
import { COST_PRESETS, fmtInt } from '@/lib/indicatorResearch';

type Props = {
  settings: SettingsState;
  onChange: (settings: SettingsState) => void;
  disabled?: boolean;
};

const STOP_MODES: Array<{ id: string; label: string }> = [
  { id: 'none', label: 'No stop' },
  { id: 'percent', label: 'Percent of entry' },
  { id: 'atr', label: 'ATR multiple' },
  { id: 'points', label: 'Fixed points' },
];

export function BacktestControls({ settings, onChange, disabled }: Props) {
  const patch = <K extends keyof SettingsState>(section: K, values: Partial<SettingsState[K]>) => {
    onChange({ ...settings, [section]: { ...(settings[section] as object), ...values } as SettingsState[K] });
  };

  const costs = settings.costs;
  const roundTripBps =
    (costs.slippage_bps ?? 0) * 2 +
    (costs.brokerage_bps ?? 0) * 2 +
    (costs.exchange_bps ?? 0) * 2 +
    (costs.sebi_bps ?? 0) * 2 +
    (costs.stt_sell_bps ?? 0) +
    (costs.stamp_buy_bps ?? 0);
  const gstMultiplier = 1 + (costs.gst_on_fees_pct ?? 0) / 100;
  const gstAdjusted = roundTripBps * gstMultiplier;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-1.5">
        <span className="micro-label">Execution &amp; costs</span>
        <span className="badge badge-sm b-neut ml-auto">default · next open</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="field col-span-2">
          <span className="field-l">Signal → fill</span>
          <select
            className="input w-full"
            value={settings.execution.entry_fill}
            disabled={disabled}
            onChange={(e) => patch('execution', { entry_fill: e.target.value as 'next_open' | 'signal_close' })}
          >
            <option value="next_open">Signal at close, fill at next open</option>
            <option value="signal_close">Signal at close, fill at same close</option>
          </select>
        </label>
        {settings.execution.entry_fill === 'signal_close' ? (
          <p className="notice notice--warn col-span-2 text-[10px]">
            Same-close fills assume you could trade at the exact closing print — optimistic by roughly one bar of drift.
          </p>
        ) : null}

        <label className="field">
          <span className="field-l">Sizing</span>
          <select
            className="input w-full"
            value={settings.execution.size_mode}
            disabled={disabled}
            onChange={(e) => patch('execution', { size_mode: e.target.value as 'fixed_fraction' | 'fixed_units' })}
          >
            <option value="fixed_fraction">% of equity</option>
            <option value="fixed_units">Fixed units</option>
          </select>
        </label>
        <label className="field">
          <span className="field-l">Capital</span>
          <input
            type="number"
            className="input w-full"
            value={settings.execution.initial_capital}
            disabled={disabled}
            min={1}
            step={10_000}
            onChange={(e) => patch('execution', { initial_capital: Math.max(1, Number(e.target.value) || 1) })}
          />
        </label>
        {settings.execution.size_mode === 'fixed_fraction' ? (
        <label className="field">
          <span className="field-l">Allocation (0–1)</span>
          <input
            type="number"
            className="input w-full"
            value={settings.execution.allocation_pct}
            disabled={disabled}
            min={0.01}
            max={1}
            step={0.05}
            onChange={(e) => patch('execution', { allocation_pct: Math.max(0.01, Math.min(1, Number(e.target.value) || 0.01)) })}
          />
        </label>
        ) : (
          <label className="field">
            <span className="field-l">Units</span>
            <input
              type="number"
              className="input w-full"
              value={settings.execution.fixed_units}
              disabled={disabled}
              min={0.01}
              step={0.01}
              onChange={(e) => patch('execution', { fixed_units: Math.max(0.01, Number(e.target.value) || 0.01) })}
            />
          </label>
        )}
        <label className="field">
          <span className="field-l">Leverage</span>
          <input
            type="number"
            className="input w-full"
            value={settings.execution.leverage}
            disabled={disabled}
            min={1}
            max={10}
            step={0.5}
            onChange={(e) => patch('execution', { leverage: Math.max(1, Math.min(10, Number(e.target.value) || 1)) })}
          />
        </label>
      </div>

      <div className="divider" />

      <span className="micro-label">Risk exits</span>
      <div className="grid grid-cols-2 gap-2">
        <label className="field">
          <span className="field-l">Stop</span>
          <select
            className="input w-full"
            value={settings.exits.stop_mode}
            disabled={disabled}
            onChange={(e) => patch('exits', { stop_mode: e.target.value as SettingsState['exits']['stop_mode'] })}
          >
            {STOP_MODES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-l">{settings.exits.stop_mode === 'points' ? 'Stop (pts)' : 'Stop (× / %)'}</span>
          <input
            type="number"
            className="input w-full"
            value={settings.exits.stop_value}
            disabled={disabled || settings.exits.stop_mode === 'none'}
            min={0.01}
            step={0.1}
            onChange={(e) => patch('exits', { stop_value: Number(e.target.value) || 0.1 })}
          />
        </label>
        <label className="field">
          <span className="field-l">Target</span>
          <select
            className="input w-full"
            value={settings.exits.target_mode}
            disabled={disabled}
            onChange={(e) => patch('exits', { target_mode: e.target.value as SettingsState['exits']['target_mode'] })}
          >
            {STOP_MODES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-l">{settings.exits.target_mode === 'points' ? 'Target (pts)' : 'Target (× / %)'}</span>
          <input
            type="number"
            className="input w-full"
            value={settings.exits.target_value}
            disabled={disabled || settings.exits.target_mode === 'none'}
            min={0.01}
            step={0.1}
            onChange={(e) => patch('exits', { target_value: Number(e.target.value) || 0.1 })}
          />
        </label>
        <label className="field">
          <span className="field-l">Max bars held</span>
          <input
            type="number"
            className="input w-full"
            value={settings.exits.max_bars_held ?? ''}
            disabled={disabled}
            min={1}
            placeholder="unlimited"
            onChange={(e) =>
              patch('exits', { max_bars_held: e.target.value === '' ? null : Math.max(1, Number(e.target.value) || 1) })
            }
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <Toggle
          label="Exit on opposite signal"
          checked={settings.exits.exit_on_opposite}
          disabled={disabled}
          onChange={(v) => patch('exits', { exit_on_opposite: v })}
        />
        <Toggle
          label="Exit at session close"
          checked={settings.exits.exit_at_session_close}
          disabled={disabled}
          onChange={(v) => patch('exits', { exit_at_session_close: v })}
        />
        <Toggle
          label="Allow long"
          checked={settings.exits.allow_long}
          disabled={disabled}
          onChange={(v) => patch('exits', { allow_long: v })}
        />
        <Toggle
          label="Allow short"
          checked={settings.exits.allow_short}
          disabled={disabled}
          onChange={(v) => patch('exits', { allow_short: v })}
        />
      </div>

      <div className="divider" />

      <div className="flex items-center gap-1">
        <span className="micro-label">Transaction costs (bps)</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {Object.entries(COST_PRESETS).map(([key, preset]) => (
          <button
            key={key}
            type="button"
            className="chip"
            disabled={disabled}
            title={preset.label}
            onClick={() => patch('costs', preset.costs)}
          >
            {key}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        <CostField label="Slippage" value={costs.slippage_bps} disabled={disabled} onChange={(v) => patch('costs', { slippage_bps: v })} />
        <CostField label="Brokerage" value={costs.brokerage_bps} disabled={disabled} onChange={(v) => patch('costs', { brokerage_bps: v })} />
        <CostField label="Exchange" value={costs.exchange_bps} disabled={disabled} onChange={(v) => patch('costs', { exchange_bps: v })} />
        <CostField label="SEBI" value={costs.sebi_bps} disabled={disabled} onChange={(v) => patch('costs', { sebi_bps: v })} />
        <CostField label="STT (sell)" value={costs.stt_sell_bps} disabled={disabled} onChange={(v) => patch('costs', { stt_sell_bps: v })} />
        <CostField label="Stamp (buy)" value={costs.stamp_buy_bps} disabled={disabled} onChange={(v) => patch('costs', { stamp_buy_bps: v })} />
      </div>
      <div className="sg-kvlist">
        <div className="sg-kv">
          <span className="sg-lab">Round-trip cost</span>
          <span className="sg-num">≈ {fmtCostBps(gstAdjusted)} bps of notional</span>
        </div>
        <div className="sg-kv">
          <span className="sg-lab">On capital</span>
          <span className="sg-num num">
            ≈ ₹{fmtInt(((settings.execution.initial_capital * settings.execution.allocation_pct * gstAdjusted) / 10_000))} per full-size round trip
          </span>
        </div>
      </div>
      {gstAdjusted === 0 ? (
        <p className="notice notice--warn text-[10px]">
          Zero-cost runs are diagnostic only. Any conclusion drawn from them is not tradeable.
        </p>
      ) : null}

      <div className="divider" />

      <Toggle
        label="Verify no-lookahead (re-derive features on truncated windows)"
        checked={settings.verify_causality}
        disabled={disabled}
        onChange={(v) => onChange({ ...settings, verify_causality: v })}
      />
    </div>
  );
}

function fmtCostBps(v: number): string {
  return v.toFixed(2);
}

function CostField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <label className="field">
      <span className="field-l">{label}</span>
      <input
        type="number"
        className="input w-full"
        value={value}
        disabled={disabled}
        min={0}
        step={0.1}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
      />
    </label>
  );
}

function Toggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-1.5">
      <input
        type="checkbox"
        className="mt-0.5 h-3.5 w-3.5 accent-[var(--ds-accent)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-[11px] leading-tight text-ink-2">{label}</span>
    </label>
  );
}
