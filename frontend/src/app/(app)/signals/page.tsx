'use client';

import { Suspense, useCallback, useMemo } from 'react';
import SignalsDesk, { type SignalsDeskProps } from '@/components/signals/SignalsDesk';
import { useEnumQueryParam, useQueryParam, useQueryParamsWriter, decodeParam, encodeParam } from '@/lib/urlState';
import type { DeskFilter, InstrumentFilter } from '@/components/signals/useSignalsData';

function SignalsPageInner() {
  // Desk filters + tab are URL state (Phase 5): shareable desk views.
  const writeParams = useQueryParamsWriter();
  const desk = useEnumQueryParam<'ALL' | 'SCALP' | 'INTRADAY'>(
    'desk',
    ['ALL', 'SCALP', 'INTRADAY'] as const,
    'ALL',
  );
  const underlyingParam = useQueryParam('underlying');
  const underlying = useMemo((): InstrumentFilter => {
    const decoded = decodeParam(underlyingParam);
    const allowed: readonly string[] = ['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'];
    return decoded !== null && allowed.includes(decoded) ? (decoded as InstrumentFilter) : 'ALL';
  }, [underlyingParam]);
  const tab = useEnumQueryParam<'live' | 'performance' | 'history'>(
    'tab',
    ['live', 'performance', 'history'] as const,
    'live',
  );

  const setDeskFilter = useCallback(
    (v: DeskFilter) => writeParams({ desk: v === 'ALL' ? null : v }),
    [writeParams],
  );
  const setInstrumentFilter = useCallback(
    (v: InstrumentFilter) => writeParams({ underlying: v === 'ALL' ? null : encodeParam(v) }),
    [writeParams],
  );
  const setTab = useCallback(
    (v: string) => writeParams({ tab: v === 'live' ? null : v }),
    [writeParams],
  );

  return (
    <SignalsDesk
      initialDeskFilter={desk}
      initialInstrumentFilter={underlying}
      initialTab={tab}
      onDeskFilterChange={setDeskFilter}
      onInstrumentFilterChange={setInstrumentFilter}
      onTabChange={setTab}
    />
  );
}

/** Suspense boundary required: useSearchParams on a prerendered static route. */
export default function SignalsPage() {
  return (
    <Suspense fallback={<div className="ds-module ds-module-fill" />}>
      <SignalsPageInner />
    </Suspense>
  );
}