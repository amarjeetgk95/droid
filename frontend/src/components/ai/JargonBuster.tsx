'use client';

import React, { useState } from 'react';
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react';

const TERMS: { word: string; simple: string }[] = [
  { word: 'Bullish / Bearish', simple: 'Bullish = price may go up. Bearish = price may go down.' },
  { word: 'Support / Resistance', simple: 'Support = a price level where falling usually stops. Resistance = a level where rising usually stops.' },
  { word: 'PCR (Put-Call Ratio)', simple: 'Compares how many put options vs call options traders hold. Above 1 = cautious crowd. Below 0.7 = greedy crowd.' },
  { word: 'Max Pain', simple: 'The price where most option buyers lose money at expiry. Price is often pulled toward it.' },
  { word: 'Open Interest (OI)', simple: 'How many option/future contracts are currently open. Rising OI = new money entering.' },
  { word: 'IV (Implied Volatility)', simple: 'How big a move the market expects. High IV = options are costly and a big swing is expected.' },
  { word: 'India VIX', simple: 'The market fear meter. Below 13 = calm. Above 20 = nervous.' },
  { word: 'Basis / Premium', simple: 'How much higher the future price is vs today\u2019s price. Big gap = traders expect upside.' },
  { word: 'Call writing / Put writing', simple: 'Big traders selling options to earn premium — it usually blocks price from crossing that level.' },
  { word: 'Breakout / Breakdown', simple: 'Breakout = price jumps above resistance. Breakdown = price falls below support.' },
  { word: 'R:R (Risk-Reward)', simple: 'How much you can win vs lose. 1:2 means risk \u20B91 to possibly make \u20B92.' },
  { word: 'Theta decay', simple: 'Options lose a little value every day. Sellers earn it, buyers pay it.' },
];

export function JargonBuster() {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-card border border-border rounded-2xl shadow-xs overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
      >
        <span className="flex items-center gap-2">
          <span className="p-1.5 bg-amber-500/10 text-amber-500 rounded-lg">
            <BookOpen className="w-4 h-4" />
          </span>
          <span className="text-left">
            <span className="block text-xs font-bold text-foreground">Confused by a word?</span>
            <span className="block text-[11px] text-muted-foreground">Tap to see market terms in simple language</span>
          </span>
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-border/60 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {TERMS.map((t) => (
            <div key={t.word} className="bg-secondary/30 rounded-xl p-2.5 border border-border/60">
              <p className="text-xs font-bold text-foreground">{t.word}</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">{t.simple}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
