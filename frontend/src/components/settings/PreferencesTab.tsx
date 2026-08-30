'use client';

import React, { useState, useRef } from 'react';
import { Palette, Globe, Volume2, Download, Upload, RotateCcw, CheckCircle2, AlertCircle, LayoutGrid, Sliders } from 'lucide-react';
import { PreferencesSettings, AppSettings, exportSettingsJson, importSettingsJson } from '@/lib/settings';

interface Props {
  settings: PreferencesSettings;
  fullSettings: AppSettings;
  onChange: (updated: Partial<PreferencesSettings>) => void;
  onFullSettingsChange: (newFull: AppSettings) => void;
  onResetAll: () => void;
}

export function PreferencesTab({ settings, fullSettings, onChange, onFullSettingsChange, onResetAll }: Props) {
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [includeSecretsInExport, setIncludeSecretsInExport] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExport = () => {
    try {
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(
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
          ? 'Settings exported WITH API keys — store this file securely!'
          : 'Settings exported (API keys/secrets stripped for safety).',
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
        setMsg({ type: 'success', text: 'Settings successfully imported from backup file!' });
      } catch {
        setMsg({ type: 'error', text: 'Invalid settings JSON backup file format.' });
      }
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="space-y-6">
      {msg && (
        <div
          className={`p-3.5 rounded-xl text-xs flex items-center gap-2 ${
            msg.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {msg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span>{msg.text}</span>
        </div>
      )}

      {/* 1. Interface & Number Format Preferences */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Palette className="w-4 h-4 text-primary" />
            Display & Regional Formatting
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Personalize terminal theme, number representations, and default trading assets.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs pt-1">
          <div>
            <label className="font-semibold text-foreground block mb-1">
              Terminal Visual Theme
            </label>
            <select
              value={settings.theme}
              onChange={(e) => onChange({ theme: e.target.value as any })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden"
            >
              <option value="dark">Cyberpunk Dark (Default OLED)</option>
              <option value="light">Daylight Light Theme</option>
              <option value="system">Follow Operating System</option>
            </select>
          </div>

          <div>
            <label className="font-semibold text-foreground block mb-1">
              Currency & Number System
            </label>
            <select
              value={settings.numberFormat}
              onChange={(e) => onChange({ numberFormat: e.target.value as any })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden"
            >
              <option value="INDIAN">Indian (₹ Lakhs & Crores — ₹1,25,000)</option>
              <option value="INTERNATIONAL">International (Millions & Billions — 125,000)</option>
            </select>
          </div>

          <div>
            <label className="font-semibold text-foreground block mb-1">
              Default Primary Index
            </label>
            <select
              value={settings.defaultIndexSymbol}
              onChange={(e) => onChange({ defaultIndexSymbol: e.target.value })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden"
            >
              <option value="NIFTY 50">NIFTY 50</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
              <option value="FINNIFTY">FINNIFTY</option>
              <option value="SENSEX">SENSEX</option>
            </select>
          </div>
        </div>


      </div>

      {/* 2. Backup, Import & Factory Reset */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Sliders className="w-4 h-4 text-primary" />
            Configuration Backup & Reset
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Export your quantitative rules and broker configurations to a JSON file or restore defaults.
            API keys are stripped by default for safety.
          </p>
        </div>

        {/* Include secrets toggle */}
        <div className="bg-secondary/30 border border-border/50 rounded-lg p-3 flex items-center justify-between text-xs">
          <div>
            <span className="font-semibold text-foreground block">Include API Keys in Export</span>
            <span className="text-[11px] text-muted-foreground">
              {includeSecretsInExport
                ? '⚠️ API keys WILL be included — store the exported file securely!'
                : 'API keys and secrets will be stripped from the exported file'}
            </span>
          </div>
          <input
            type="checkbox"
            checked={includeSecretsInExport}
            onChange={(e) => setIncludeSecretsInExport(e.target.checked)}
            className="w-4 h-4 rounded text-primary accent-primary cursor-pointer"
          />
        </div>

        <div className="flex flex-wrap gap-3 pt-1">
          <button
            type="button"
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs"
          >
            <Download className="w-4 h-4 text-primary" />
            <span>Export Settings (JSON)</span>
          </button>

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs"
          >
            <Upload className="w-4 h-4 text-emerald-400" />
            <span>Import Settings File</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleImportFile}
            className="hidden"
          />

          <button
            type="button"
            onClick={() => {
              if (confirm('Are you sure you want to restore all settings to default values?')) {
                onResetAll();
                setMsg({ type: 'success', text: 'All settings restored to factory defaults.' });
              }
            }}
            className="flex items-center gap-2 px-4 py-2 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/20 rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs ml-auto"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Restore Factory Defaults</span>
          </button>
        </div>
      </div>
    </div>
  );
}
