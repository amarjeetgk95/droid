'use client';

import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';

export type MarketSessionPhase = 'PRE_OPEN' | 'OPEN' | 'POST_CLOSE' | 'CLOSED';

interface MarketSessionContextType {
  phase: MarketSessionPhase;
  isOpen: boolean;
  sessionTimeIST: string;
  nextSessionChange: string;
}

const MarketSessionContext = createContext<MarketSessionContextType | null>(null);

/**
 * Deterministic placeholder used for SSR and the first client render. A live
 * clock value cannot match between server and hydration, so the real value is
 * computed in an effect immediately after mount.
 */
const SSR_SESSION: MarketSessionContextType = {
  phase: 'CLOSED',
  isOpen: false,
  sessionTimeIST: '--:--:-- IST',
  nextSessionChange: 'Syncing…',
};

function computeISTSession(now: Date = new Date()): MarketSessionContextType {
  // IST is UTC + 5:30
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const ist = new Date(utc + 3600000 * 5.5);

  const day = ist.getDay(); // 0 is Sunday, 6 is Saturday
  const isWeekend = day === 0 || day === 6;

  const hours = ist.getHours();
  const minutes = ist.getMinutes();
  const timeInMinutes = hours * 60 + minutes;

  const timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(ist.getSeconds()).padStart(2, '0')} IST`;

  if (isWeekend) {
    return {
      phase: 'CLOSED',
      isOpen: false,
      sessionTimeIST: timeStr,
      nextSessionChange: 'Monday 09:15 IST',
    };
  }

  // 09:00 - 09:15 (540 - 555)
  if (timeInMinutes >= 540 && timeInMinutes < 555) {
    return {
      phase: 'PRE_OPEN',
      isOpen: false,
      sessionTimeIST: timeStr,
      nextSessionChange: 'Market Open in ' + (555 - timeInMinutes) + 'm',
    };
  }

  // 09:15 - 15:30 (555 - 930)
  if (timeInMinutes >= 555 && timeInMinutes < 930) {
    const minsLeft = 930 - timeInMinutes;
    const hrsLeft = Math.floor(minsLeft / 60);
    const remMins = minsLeft % 60;
    return {
      phase: 'OPEN',
      isOpen: true,
      sessionTimeIST: timeStr,
      nextSessionChange: `Closes in ${hrsLeft}h ${remMins}m`,
    };
  }

  // 15:30 - 16:00 (930 - 960)
  if (timeInMinutes >= 930 && timeInMinutes < 960) {
    return {
      phase: 'POST_CLOSE',
      isOpen: false,
      sessionTimeIST: timeStr,
      nextSessionChange: 'Session ending in ' + (960 - timeInMinutes) + 'm',
    };
  }

  return {
    phase: 'CLOSED',
    isOpen: false,
    sessionTimeIST: timeStr,
    nextSessionChange: 'Opens next trading day 09:15 IST',
  };
}

function sessionsEqual(a: MarketSessionContextType, b: MarketSessionContextType): boolean {
  return (
    a.phase === b.phase &&
    a.isOpen === b.isOpen &&
    a.sessionTimeIST === b.sessionTimeIST &&
    a.nextSessionChange === b.nextSessionChange
  );
}

export const MarketSessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<MarketSessionContextType>(SSR_SESSION);

  useEffect(() => {
    const update = () => {
      setSession((prev) => {
        const next = computeISTSession();
        // Same displayed value => keep the previous object so consumers do not
        // re-render (interval ticks often repeat a value).
        return sessionsEqual(prev, next) ? prev : next;
      });
    };
    update(); // Swap the SSR placeholder for the real clock after hydration.
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  const { phase, isOpen, sessionTimeIST, nextSessionChange } = session;
  const value = useMemo<MarketSessionContextType>(
    () => ({ phase, isOpen, sessionTimeIST, nextSessionChange }),
    [phase, isOpen, sessionTimeIST, nextSessionChange],
  );

  return (
    <MarketSessionContext.Provider value={value}>
      {children}
    </MarketSessionContext.Provider>
  );
};

export function useMarketSession() {
  const ctx = useContext(MarketSessionContext);
  if (!ctx) {
    throw new Error('useMarketSession must be used within a MarketSessionProvider');
  }
  return ctx;
}
