'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Bot,
  Zap,
  ShieldCheck,
  Settings2,
  Volume2,
  VolumeX,
  AlertOctagon,
  Clock,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useScalpContext } from './ScalpContext';

export function CommandRibbon() {
  const {
    sessionMTM,
    lossUsedPct,
    autoPilot,
    setAutoPilot,
    toggleAutoPilot,
    autoTradesCount,
    audioEnabled,
    setAudioEnabled,
    openPositions,
    panicPending,
    panicSquareOff,
    isFullscreen,
    toggleFullscreen,
  } = useScalpContext();

  const [showSettings, setShowSettings] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  // Session elapsed clock (IST market open: 09:15)
  const [elapsedStr, setElapsedStr] = useState<string>('00:00');

  useEffect(() => {
    const updateElapsed = () => {
      const now = new Date();
      // IST is UTC + 5:30
      const istUtcOffsetMs = 5.5 * 60 * 60 * 1000;
      const istTime = new Date(now.getTime() + istUtcOffsetMs);
      const hours = istTime.getUTCHours();
      const minutes = istTime.getUTCMinutes();

      const marketOpenMinutes = 9 * 60 + 15;
      const currentMinutes = hours * 60 + minutes;
      const marketCloseMinutes = 15 * 60 + 30;

      if (currentMinutes < marketOpenMinutes) {
        setElapsedStr('PRE-MKT');
      } else if (currentMinutes > marketCloseMinutes) {
        setElapsedStr('CLOSED');
      } else {
        const diff = currentMinutes - marketOpenMinutes;
        const h = Math.floor(diff / 60);
        const m = diff % 60;
        setElapsedStr(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
      }
    };

    updateElapsed();
    const interval = setInterval(updateElapsed, 30000);
    return () => clearInterval(interval);
  }, []);

  // Close limits popover when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setShowSettings(false);
      }
    };
    if (showSettings) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showSettings]);

  const pnlFormatted = useMemo(() => {
    const prefix = sessionMTM >= 0 ? '+' : '';
    return `${prefix}₹${sessionMTM.toLocaleString('en-IN', { maximumFractionDigits: 1 })}`;
  }, [sessionMTM]);

  const panicDisabled = openPositions.length === 0 || panicPending;

  return (
    <div className="relative bg-card border border-border rounded-lg px-3 py-1.5 flex flex-col gap-1.5 shrink-0 shadow-xs select-none">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        {/* Left: Auto-Pilot State & Master Trigger */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleAutoPilot}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-mono font-bold text-xs transition-all cursor-pointer shadow-sm ${
              autoPilot.enabled
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white ring-2 ring-emerald-400/40 animate-pulse'
                : 'bg-secondary hover:bg-secondary/80 text-muted-foreground border border-border'
            }`}
          >
            <Bot className={`w-3.5 h-3.5 ${autoPilot.enabled ? 'text-white' : 'text-muted-foreground'}`} />
            <span>{autoPilot.enabled ? '⚡ ARMED (Hands-Free)' : 'STANDBY (Manual)'}</span>
          </button>

          {/* Market session clock */}
          <div
            className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground bg-secondary/50 px-2 py-1 rounded border border-border/40"
            title="Elapsed market session time since 09:15 IST"
          >
            <Clock className="w-3 h-3 text-muted-foreground" />
            <span>{elapsedStr}</span>
          </div>
        </div>

        {/* Center: Live Risk Budget Meter */}
        <div className="flex items-center gap-2.5 text-[11px] font-mono bg-background/60 px-3 py-1 rounded border border-border/60">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground text-[10px] uppercase tracking-wider">Session MTM:</span>
            <span
              className={`font-bold ${
                sessionMTM > 0
                  ? 'text-emerald-400'
                  : sessionMTM < 0
                    ? 'text-rose-400'
                    : 'text-foreground'
              }`}
            >
              {pnlFormatted}
            </span>
          </div>

          <span className="text-border">|</span>

          <div className="flex items-center gap-1.5" title={`Stop limit: ₹${autoPilot.maxDailyLoss}`}>
            <span className="text-muted-foreground text-[10px]">Risk Stop:</span>
            <span className="text-rose-400 font-semibold">-₹{autoPilot.maxDailyLoss}</span>
            {/* Progress bar towards daily stop with numeric percent */}
            <div className="w-20 h-2 bg-secondary rounded-full overflow-hidden border border-border/60 relative">
              <div
                className={`h-full transition-all ${
                  lossUsedPct >= 80
                    ? 'bg-rose-500'
                    : lossUsedPct >= 40
                      ? 'bg-amber-500'
                      : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.max(2, lossUsedPct)}%` }}
              />
            </div>
            <span className="text-[10px] text-muted-foreground">{Math.round(lossUsedPct)}%</span>
          </div>

          <span className="text-border hidden md:inline">|</span>

          {/* Guards summary */}
          <div className="hidden md:flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            <span>Max {autoPilot.maxConcurrent} Open · Min {autoPilot.minConfidence}% Conf</span>
          </div>
        </div>

        {/* Right: Controls & Emergency Panic All */}
        <div className="flex items-center gap-1.5">
          <span
            className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-secondary text-muted-foreground"
            title="Auto-pilot trades executed this session"
          >
            Fired: {autoTradesCount}
          </span>

          <button
            type="button"
            onClick={() => setAudioEnabled(!audioEnabled)}
            className={`p-1.5 rounded transition-colors cursor-pointer ${
              audioEnabled
                ? 'bg-secondary text-foreground hover:bg-secondary/80'
                : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
            }`}
            title={audioEnabled ? 'Sound alerts enabled' : 'Sound alerts muted'}
          >
            {audioEnabled ? (
              <Volume2 className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <VolumeX className="w-3.5 h-3.5 text-muted-foreground" />
            )}
          </button>

          {/* Limits button with dropdown */}
          <div className="relative" ref={settingsRef}>
            <button
              type="button"
              onClick={() => setShowSettings((prev) => !prev)}
              className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-colors cursor-pointer ${
                showSettings
                  ? 'bg-primary text-primary-foreground font-bold'
                  : 'bg-secondary text-muted-foreground hover:text-foreground'
              }`}
              title="Configure auto-pilot circuit breakers"
            >
              <Settings2 className="w-3.5 h-3.5" />
              <span>Limits</span>
            </button>

            {/* Popover Card for Circuit Breaker Settings */}
            {showSettings && (
              <div className="absolute right-0 top-full mt-1.5 w-72 bg-popover text-popover-foreground border border-border shadow-xl rounded-lg p-3 z-50 flex flex-col gap-2.5 text-xs animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between border-b border-border/60 pb-1.5">
                  <span className="font-bold text-foreground flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" /> Circuit Breaker Limits
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowSettings(false)}
                    className="text-muted-foreground hover:text-foreground text-[10px]"
                  >
                    ✕
                  </button>
                </div>

                <div>
                  <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
                    <span>Min Confidence</span>
                    <span className="text-foreground font-bold">{autoPilot.minConfidence}%</span>
                  </div>
                  <input
                    type="range"
                    min={70}
                    max={95}
                    step={5}
                    value={autoPilot.minConfidence}
                    onChange={(e) =>
                      setAutoPilot((prev) => ({
                        ...prev,
                        minConfidence: Number(e.target.value),
                      }))
                    }
                    className="w-full accent-primary cursor-pointer h-1.5 bg-secondary rounded-lg"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
                    <span>Max Concurrent Scalps</span>
                    <span className="text-foreground font-bold">{autoPilot.maxConcurrent}</span>
                  </div>
                  <input
                    type="range"
                    min={1}
                    max={4}
                    step={1}
                    value={autoPilot.maxConcurrent}
                    onChange={(e) =>
                      setAutoPilot((prev) => ({
                        ...prev,
                        maxConcurrent: Number(e.target.value),
                      }))
                    }
                    className="w-full accent-primary cursor-pointer h-1.5 bg-secondary rounded-lg"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
                    <span>Daily Max Loss Stop</span>
                    <span className="text-rose-400 font-bold">₹{autoPilot.maxDailyLoss}</span>
                  </div>
                  <input
                    type="range"
                    min={1000}
                    max={20000}
                    step={500}
                    value={autoPilot.maxDailyLoss}
                    onChange={(e) =>
                      setAutoPilot((prev) => ({
                        ...prev,
                        maxDailyLoss: Number(e.target.value),
                      }))
                    }
                    className="w-full accent-primary cursor-pointer h-1.5 bg-secondary rounded-lg"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
                    <span>Anti-Chase Tolerance</span>
                    <span className="text-foreground font-bold">{autoPilot.antiChaseTolerance} pts</span>
                  </div>
                  <input
                    type="range"
                    min={5}
                    max={40}
                    step={5}
                    value={autoPilot.antiChaseTolerance}
                    onChange={(e) =>
                      setAutoPilot((prev) => ({
                        ...prev,
                        antiChaseTolerance: Number(e.target.value),
                      }))
                    }
                    className="w-full accent-primary cursor-pointer h-1.5 bg-secondary rounded-lg"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Fullscreen Mode Toggle Button */}
          <button
            type="button"
            onClick={toggleFullscreen}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-all cursor-pointer ${
              isFullscreen
                ? 'bg-amber-500 hover:bg-amber-400 text-black font-black ring-2 ring-amber-400/40 shadow-xs'
                : 'bg-secondary text-muted-foreground hover:text-foreground hover:bg-secondary/80'
            }`}
            title={isFullscreen ? 'Exit Fullscreen (F)' : 'Expand to Fullscreen / Theater Mode (F)'}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{isFullscreen ? 'Exit' : 'Full'}</span>
            <kbd className="hidden lg:inline text-[9px] bg-black/15 px-1 rounded opacity-80 font-mono">F</kbd>
          </button>

          {/* Single Global Anchored Emergency Panic Square Off Button */}
          <button
            type="button"
            disabled={panicDisabled}
            onClick={panicSquareOff}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-mono font-bold text-[11px] shadow-sm shadow-rose-950/30 transition-all disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            title="Emergency Square Off All Open Positions (Shift+Esc)"
          >
            <AlertOctagon className={`w-3.5 h-3.5 ${panicPending ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{panicPending ? 'EXITING…' : 'PANIC ALL'}</span>
            <kbd className="hidden lg:inline text-[9px] bg-rose-800 px-1 rounded opacity-85">
              Shift+Esc
            </kbd>
          </button>
        </div>
      </div>
    </div>
  );
}
