'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { SwingSetupDTO, SwingPositionDTO, PortfolioRiskDTO } from '@/lib/api/swing';

export type SwingFilterParams = {
  strategy?: string;
  underlying?: string;
  sector?: string;
  min_score?: number;
  state?: string;
  direction?: string;
  horizon?: string;
};

export function useSwingData(filters?: SwingFilterParams) {
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [setups, setSetups] = useState<SwingSetupDTO[]>([]);
  const [openPositions, setOpenPositions] = useState<SwingPositionDTO[]>([]);
  const [closedPositions, setClosedPositions] = useState<SwingPositionDTO[]>([]);
  const [portfolioRisk, setPortfolioRisk] = useState<PortfolioRiskDTO | null>(null);
  const [regime, setRegime] = useState<any>(null);
  const [sectors, setSectors] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [setupsRes, posRes, regRes] = await Promise.all([
        api.getSwingSetups(filters),
        api.getSwingPositions(),
        api.getSwingRegime(),
      ]);

      if (setupsRes?.data) {
        setSetups(setupsRes.data.setups || []);
      }
      if (posRes?.data) {
        setOpenPositions(posRes.data.open_positions || []);
        setClosedPositions(posRes.data.closed_positions || []);
        setPortfolioRisk(posRes.data.portfolio_risk || null);
      }
      if (regRes?.data) {
        setRegime(regRes.data.regime || null);
        setSectors(regRes.data.sectors || []);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load swing data.');
    } finally {
      setLoading(false);
    }
  }, [filters?.strategy, filters?.underlying, filters?.sector, filters?.min_score, filters?.state, filters?.direction, filters?.horizon]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const triggerScan = useCallback(async (forceRefresh: boolean = false, horizon?: string) => {
    setScanning(true);
    try {
      setError(null);
      const res = await api.triggerSwingScan({ force_refresh: forceRefresh, horizon: horizon || filters?.horizon });
      if (res?.data) {
        setSetups(res.data.setups || []);
        setOpenPositions(res.data.open_positions || []);
        setPortfolioRisk(res.data.portfolio_risk || null);
        setRegime(res.data.regime || null);
        setSectors(res.data.sectors || []);
      }
      return res?.data;
    } catch (err: any) {
      setError(err?.message || 'Scan execution failed.');
      throw err;
    } finally {
      setScanning(false);
    }
  }, [filters?.horizon]);

  const enterTrade = useCallback(async (setupId: string, fillPremium?: number, numLots?: number) => {
    try {
      const res = await api.enterSwingPosition({ setup_id: setupId, fill_premium: fillPremium, num_lots: numLots });
      await refresh();
      return res?.data;
    } catch (err: any) {
      setError(err?.message || 'Failed to enter swing position.');
      throw err;
    }
  }, [refresh]);

  const exitTrade = useCallback(async (positionId: string, exitPremium?: number, exitReason: string = 'MANUAL_EXIT') => {
    try {
      const res = await api.exitSwingPosition({ position_id: positionId, exit_premium: exitPremium, exit_reason: exitReason });
      await refresh();
      return res?.data;
    } catch (err: any) {
      setError(err?.message || 'Failed to exit swing position.');
      throw err;
    }
  }, [refresh]);

  return {
    loading,
    scanning,
    setups,
    openPositions,
    closedPositions,
    portfolioRisk,
    regime,
    sectors,
    error,
    refresh,
    triggerScan,
    enterTrade,
    exitTrade,
  };
}
