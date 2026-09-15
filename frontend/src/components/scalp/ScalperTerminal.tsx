'use client';

import React, { useState } from 'react';
import { ScalpProvider, useScalpContext } from './ScalpContext';
import { CommandRibbon } from './CommandRibbon';
import { ScalperChart } from './ScalperChart';
import { QuickScalpTicket } from './QuickScalpTicket';
import { TacticalDock } from './TacticalDock';

function ScalperTerminalInner() {
  const { openPositions, underlying, isFullscreen } = useScalpContext();
  const [bracket, setBracket] = useState<{ sl: number; tp: number }>({ sl: 8, tp: 16 });
  const [timeframe, setTimeframe] = useState<'1m' | '3m' | '5m'>('1m');
  const [showHelpModal, setShowHelpModal] = useState(false);

  const activePosition = openPositions.find((p) => {
    const und = (p.underlying || '').toUpperCase();
    if (und) return und === underlying;
    // Fallback for legacy positions without underlying: exact prefix match
    // (BANKNIFTY must not match NIFTY — check longer names first).
    const sym = (p.symbol || '').toUpperCase();
    if (underlying === 'BANKNIFTY') return sym.includes('BANKNIFTY') || sym.includes('NIFTYBANK');
    if (underlying === 'SENSEX') return sym.includes('SENSEX');
    return sym.includes('NIFTY') && !sym.includes('BANKNIFTY') && !sym.includes('FINNIFTY');
  });

  return (
    <div
      className={
        isFullscreen
          ? 'fixed inset-0 z-50 p-2 md:p-3 bg-background flex flex-col h-screen w-screen overflow-hidden select-none gap-2 shadow-2xl'
          : 'flex flex-col h-full flex-1 min-h-0 gap-2 select-none overflow-hidden'
      }
    >
      {/* Top Command & Risk Flight Ribbon */}
      <CommandRibbon />

      {/* Mid Execution Core: Chart (65%) | Quick Ticket (35%) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-2 flex-1 min-h-0">
        {/* Left: Scalper Execution Chart */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col h-full min-h-0">
          <ScalperChart
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            slDistance={bracket.sl}
            tpDistance={bracket.tp}
            activeEntryPrice={activePosition?.average_price ?? null}
          />
        </div>

        {/* Right: Quick Scalp Ticket */}
        <div className="lg:col-span-5 xl:col-span-4 flex flex-col h-full min-h-0 overflow-y-auto">
          <QuickScalpTicket
            onBracketChange={(sl, tp) =>
              setBracket((prev) => (prev.sl === sl && prev.tp === tp ? prev : { sl, tp }))
            }
            onToggleHelp={() => setShowHelpModal((prev) => !prev)}
          />
        </div>
      </div>

      {/* Bottom Docked Tactical Deck (Positions, Radar, Trade Log) */}
      <TacticalDock
        showHelpModal={showHelpModal}
        onCloseHelpModal={() => setShowHelpModal(false)}
        onOpenHelpModal={() => setShowHelpModal(true)}
      />
    </div>
  );
}

export function ScalperTerminal() {
  return (
    <ScalpProvider>
      <ScalperTerminalInner />
    </ScalpProvider>
  );
}
