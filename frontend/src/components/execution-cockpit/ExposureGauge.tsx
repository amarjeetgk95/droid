'use client';

import React, { useCallback, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { errorMessage } from '@/lib/errors';
import { ageLabel } from '@/lib/feedState';
import { Card } from '@/components/ui/card';
import { Gauge } from '@/components/ui/gauge';

interface ExposureState {
  gross_exposure_pct: number | null;
  net_exposure_pct: number | null;
  margin_utilization_pct: number | null;
  portfolio_delta: number | null;
}

const EMPTY_EXPOSURE: ExposureState = {
  gross_exposure_pct: null,
  net_exposure_pct: null,
  margin_utilization_pct: null,
  portfolio_delta: null,
};

export const ExposureGauge: React.FC = () => {
  const [exposure, setExposure] = useState<ExposureState>(EMPTY_EXPOSURE);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api.getAlgoExposure();
      if (!res?.data) throw new Error('Backend returned no exposure payload.');
      const data = res.data;
      setExposure({
        gross_exposure_pct: toNumber(data.gross_exposure_pct),
        net_exposure_pct: toNumber(data.net_exposure_pct),
        margin_utilization_pct: toNumber(data.margin_utilization_pct),
        portfolio_delta: toNumber(data.portfolio_delta),
      });
      setLoaded(true);
      setLastUpdated(Date.now());
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err, 'Unknown exposure error'));
    }
  }, []);

  usePolling(refresh, 5000);

  const lastAge = lastUpdated === null ? null : ageLabel(lastUpdated);
  const gross = exposure.gross_exposure_pct;
  const net = exposure.net_exposure_pct;
  const margin = exposure.margin_utilization_pct;
  const delta = exposure.portfolio_delta;

  return (
    <Card
      title="PORTFOLIO EXPOSURE & DELTA METRICS"
      subtitle="Gross / Net exposure vs risk mandate ceilings"
    >
      <div className="space-y-3 font-mono text-xs">
        {loadError && (
          <div
            role={loaded ? 'status' : 'alert'}
            className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong"
          >
            Exposure refresh failed{lastAge ? ` — showing last known values (${lastAge})` : ''}: {loadError}
          </div>
        )}

        {!loaded ? (
          <div className="p-2.5 rounded-lg bg-surface-subtle border border-border text-ink-3">
            {loadError ? 'Exposure unavailable.' : 'Loading exposure metrics…'}
          </div>
        ) : (
          <>
            {gross === null ? (
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border text-ink-3">
                Gross exposure unavailable — backend did not report it.
              </div>
            ) : (
              <Gauge
                value={gross}
                label="Gross Exposure Limit"
                sublabel="Ceiling: 100% of regulatory capital"
                thresholds={{ warning: 70, danger: 85 }}
              />
            )}

            {net === null ? (
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border text-ink-3">
                Net directional skew unavailable — backend did not report it.
              </div>
            ) : (
              <Gauge
                value={Math.abs(net)}
                label="Net Directional Skew"
                sublabel={
                  delta === null
                    ? 'Current delta: unavailable'
                    : `Current delta: ${delta > 0 ? '+' : ''}${delta.toFixed(1)}`
                }
                thresholds={{ warning: 40, danger: 65 }}
              />
            )}

            {margin === null ? (
              <div className="p-2.5 rounded-lg bg-surface-subtle border border-border text-ink-3">
                Margin utilization unavailable — backend did not report it.
              </div>
            ) : (
              <Gauge
                value={margin}
                label="Margin Utilization"
                sublabel="Share of margin limit currently consumed"
                thresholds={{ warning: 60, danger: 85 }}
              />
            )}
          </>
        )}
      </div>
    </Card>
  );
};
