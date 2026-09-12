'use client';

import React, { useState, useRef } from 'react';
import {
  Palette,
  Sliders,
  Download,
  Upload,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { PreferencesSettings, AppSettings, exportSettingsJson, importSettingsJson } from '@/lib/settings';
import {
  SettingSection,
  SettingRow,
  SettingSelect,
  SettingSwitch,
} from './ui/SettingPrimitives';

interface Props {
  settings: PreferencesSettings;
  fullSettings: AppSettings;
  onChange: (updated: Partial<PreferencesSettings>) => void;
  onFullSettingsChange: (newFull: AppSettings) => void;
  onResetAll: () => void;
  errors?: { path: string; message: string }[];
}

export function PreferencesTab({
  settings,
  fullSettings,
  onChange,
  onFullSettingsChange,
  onResetAll,
  errors = [],
}: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `preferences.${field}`)?.message;
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [includeSecretsInExport, setIncludeSecretsInExport] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExport = () => {
    try {
      const dataStr =
        'data:text/json;charset=utf-8,' +
        encodeURIComponent(
          exportSettingsJson(fullSettings, { includeSecrets: includeSecretsInExport })
        );
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute('href', dataStr);
      downloadAnchor.setAttribute('download', `droid_settings_${new Date().toISOString().slice(0, 10)}.json`);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      setMsg({
        type: 'success',
        text: includeSecretsInExport
          ? 'Settings exported WITH API keys. Store this file securely.'
          : 'Settings exported safely (API keys stripped).',
      });
    } catch (err: any) {
      setMsg({ type: 'error', text: 'Failed to export settings: ' + err?.message });
    }
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = event.target?.result as string;
        const imported = importSettingsJson(content);
        onFullSettingsChange(imported);
        setMsg({ type: 'success', text: 'Configuration imported successfully.' });
      } catch {
        setMsg({ type: 'error', text: 'Invalid JSON backup format.' });
      }
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="space-y-4">
      {msg && (
        <div
          className={`card card-pad flex items-center gap-2.5 text-xs ${
            msg.type === 'success'
              ? 'border-[var(--ds-bull)]/30 bg-[var(--ds-bull-wash)] text-[var(--ds-bull-strong)]'
              : 'border-[var(--ds-bear)]/30 bg-[var(--ds-bear-wash)] text-[var(--ds-bear-strong)]'
          }`}
        >
          {msg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span className="font-medium">{msg.text}</span>
          <button
            type="button"
            onClick={() => setMsg(null)}
            className="ml-auto text-xs opacity-70 hover:opacity-100 cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 1. Display & Regional Formatting */}
      <SettingSection
        title="Display & Regional Formatting"
        description="Theme appearance, numerical conventions, and default benchmark index."
        icon={Palette}
      >
        <SettingRow
          label="Visual Appearance"
          description="Color scheme optimized for high-density tabular financial data."
        >
          <div className="seg" role="group" aria-label="Visual appearance">
            <button
              type="button"
              className="seg-btn"
              data-active={settings.theme !== 'dark'}
              aria-pressed={settings.theme !== 'dark'}
              onClick={() => onChange({ theme: 'light' })}
            >
              Kite Light (Standard)
            </button>
            <button
              type="button"
              className="seg-btn"
              data-active={settings.theme === 'dark'}
              aria-pressed={settings.theme === 'dark'}
              onClick={() => onChange({ theme: 'dark' })}
            >
              Desk Dark
            </button>
          </div>
        </SettingRow>

        <SettingRow
          label="Numeral & Currency System"
          description="Format monetary values across option chains, P&L, and order book."
          error={getError('numberFormat')}
        >
          <SettingSelect
            value={settings.numberFormat}
            onChange={(e) => onChange({ numberFormat: e.target.value as any })}
          >
            <option value="INDIAN">Indian (₹ Lakhs & Crores — ₹1,25,000)</option>
            <option value="INTERNATIONAL">International (Millions & Billions — 125,000)</option>
          </SettingSelect>
        </SettingRow>

        <SettingRow
          label="Primary Benchmark Index"
          description="Default selected underlying asset when launching terminal desks."
          error={getError('defaultIndexSymbol')}
        >
          <SettingSelect
            value={settings.defaultIndexSymbol}
            onChange={(e) => onChange({ defaultIndexSymbol: e.target.value })}
          >
            <option value="NIFTY 50">NIFTY 50</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
            <option value="SENSEX">SENSEX</option>
          </SettingSelect>
        </SettingRow>
      </SettingSection>

      {/* 2. Backup, Import & Reset */}
      <SettingSection
        title="Configuration Management"
        description="Export configuration snapshots, migrate setups, or restore factory defaults."
        icon={Sliders}
      >
        <SettingRow
          label="Include Sensitive Credentials in Export"
          description="Include broker keys and AI API credentials in the exported JSON file."
        >
          <SettingSwitch
            checked={includeSecretsInExport}
            onChange={setIncludeSecretsInExport}
            aria-label="Include API keys in export"
          />
        </SettingRow>

        <SettingRow
          label="Backup & Restore"
          description="Download current configuration snapshot or restore from a JSON backup."
        >
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExport}
              className="btn btn-sm flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5 muted" />
              <span>Export JSON</span>
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="btn btn-sm flex items-center gap-1.5"
            >
              <Upload className="w-3.5 h-3.5 muted" />
              <span>Import JSON</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleImportFile}
              className="hidden"
            />
          </div>
        </SettingRow>

        <SettingRow
          label="Factory Reset"
          description="Revert all terminal parameters, risk limits, and pricing models to system defaults."
        >
          <button
            type="button"
            onClick={() => {
              if (confirm('Are you sure you want to restore all terminal settings to default values?')) {
                onResetAll();
                setMsg({ type: 'success', text: 'All settings restored to factory defaults.' });
              }
            }}
            className="btn btn-sm flex items-center gap-1.5 text-[var(--ds-bear)] hover:border-[var(--ds-bear)]"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Restore Defaults</span>
          </button>
        </SettingRow>
      </SettingSection>
    </div>
  );
}
