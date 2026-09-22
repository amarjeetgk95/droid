'use client';

/* Trade Ops (OMS) data hook for the /trade module.
   The `algo` command section streams {account, exposure, orders,
   portfolio_greeks} every ~2s — those render from the stream with a REST
   fallback. Everything else (positions, capital, consent, strategies, drift,
   SLO, broker caps, audit) is REST-only. Mutations never auto-fire; each
   action reloads after completion. Polling is read-only. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { useCommandSection } from '@/context/AppStreamContext';
import { getObj, pickNum, pickStr, maxPayloadTimestampMs } from '@/lib/signalsNormalize';
import { toNumber } from '@/lib/coerce';
import { useSmartInterval } from './useSmartInterval';
import {
  normalizeTradeMode,
  toAiModelRow,
  toSizingPreview,
  toStrategyRow,
  toTradeAccount,
  toTradeAuditRow,
  toTradeExposure,
  toTradeOrder,
  toTradePosition,
  type AiModelRow,
  type SizingPreview,
  type StrategyRow,
  type TradeAccount,
  type TradeAuditRow,
  type TradeExposure,
  type TradeMode,
  type TradeOrder,
  type TradePosition,
} from '@/lib/tradeOps';

type AlgoSectionValue = {
  account?: unknown;
  exposure?: unknown;
  orders?: unknown;
  portfolio_greeks?: unknown;
};

function narrowAlgoSection(value: unknown): AlgoSectionValue | null {
  const o = getObj(value);
  if (!o) return null;
  return {
    account: o.account ?? undefined,
    exposure: o.exposure ?? undefined,
    orders: o.orders ?? undefined,
    portfolio_greeks: o.portfolio_greeks ?? undefined,
  };
}

export type TradeCapital = {
  limit: number | null;
  deployed: number | null;
  reserved: number | null;
  available: number | null;
  utilizationPct: number | null;
  config: Record<string, unknown> | null;
};

function toTradeCapital(input: unknown): TradeCapital | null {
  const data = getObj(getObj(input)?.data ?? input);
  if (!data) return null;
  if (data.limit === undefined && data.available === undefined) return null;
  return {
    limit: pickNum(data, 'limit'),
    deployed: pickNum(data, 'deployed'),
    reserved: pickNum(data, 'reserved', 'reserved_pending'),
    available: pickNum(data, 'available'),
    utilizationPct: pickNum(data, 'utilization_pct'),
    config: getObj(data.config),
  };
}

export type TradeConsent = {
  currentOk: boolean | null;
  version: string | null;
  count: number | null;
};

function toTradeConsent(input: unknown): TradeConsent | null {
  const data = getObj(getObj(input)?.data);
  if (!data) return null;
  const disclosure = getObj(data.disclosure);
  const consents = Array.isArray(data.consents) ? data.consents : null;
  const currentOk =
    typeof data.current_ok === 'boolean'
      ? data.current_ok
      : consents !== null
        ? consents.length > 0
        : null;
  return {
    currentOk,
    version: disclosure ? pickStr(disclosure, 'version') : null,
    count: consents ? consents.length : null,
  };
}

function toRecordList(input: unknown): unknown[] {
  const data = getObj(input)?.data;
  return Array.isArray(data) ? data : [];
}

export type TradeOpsActionResult = { ok: boolean; message: string };

export type SizingPreviewResult = TradeOpsActionResult & { preview: SizingPreview | null };

export type TradeOpsState = {
  mode: TradeMode;
  account: TradeAccount | null;
  accountSource: 'stream' | 'rest' | null;
  exposure: TradeExposure | null;
  orders: TradeOrder[];
  ordersSource: 'stream' | 'rest';
  positions: TradePosition[];
  capital: TradeCapital | null;
  consent: TradeConsent | null;
  strategies: StrategyRow[];
  aiModels: AiModelRow[];
  drift: Record<string, unknown> | null;
  slo: Record<string, unknown> | null;
  brokerCaps: Record<string, unknown> | null;
  greeks: Record<string, unknown> | null;
  audit: TradeAuditRow[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  source: 'stream' | 'rest';
  liveSource: 'stream' | 'rest';
  refresh: () => Promise<void>;
  cancelOrder: (clientOrderId: string) => Promise<TradeOpsActionResult>;
  reconcileOrder: (clientOrderId: string) => Promise<TradeOpsActionResult>;
  exitPosition: (positionId: string) => Promise<TradeOpsActionResult>;
  exitAll: () => Promise<TradeOpsActionResult>;
  previewSizing: (payload: Record<string, number>) => Promise<SizingPreviewResult>;
};

function statusText(raw: unknown): string | null {
  const o = getObj(getObj(raw)?.data ?? raw);
  return o ? pickStr(o, 'status', 'exit_state', 'reconciled', 'message') : null;
}

export function useTradeOps(
  options: { safetyRefreshMs?: number | null; auditLimit?: number } = {},
): TradeOpsState {
  const { safetyRefreshMs = null, auditLimit = 50 } = options;
  const section = useCommandSection('algo');
  const sectionValue = useMemo(() => narrowAlgoSection(section?.value), [section?.value]);

  const [restAccount, setRestAccount] = useState<TradeAccount | null>(null);
  const [restExposure, setRestExposure] = useState<TradeExposure | null>(null);
  const [restOrders, setRestOrders] = useState<TradeOrder[]>([]);
  const [positions, setPositions] = useState<TradePosition[]>([]);
  const [capital, setCapital] = useState<TradeCapital | null>(null);
  const [consent, setConsent] = useState<TradeConsent | null>(null);
  const [strategies, setStrategies] = useState<StrategyRow[]>([]);
  const [aiModels, setAiModels] = useState<AiModelRow[]>([]);
  const [drift, setDrift] = useState<Record<string, unknown> | null>(null);
  const [slo, setSlo] = useState<Record<string, unknown> | null>(null);
  const [brokerCaps, setBrokerCaps] = useState<Record<string, unknown> | null>(null);
  const [audit, setAudit] = useState<TradeAuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(
    async (showSpinner: boolean) => {
      const requestId = ++requestIdRef.current;
      if (showSpinner) setRefreshing(true);
      const [
        accountResult,
        capitalResult,
        exposureResult,
        ordersResult,
        positionsResult,
        consentResult,
        strategiesResult,
        aiModelsResult,
        driftResult,
        sloResult,
        capsResult,
        auditResult,
      ] = await Promise.allSettled([
        api.getAlgoAccount(),
        api.getAlgoCapital(),
        api.getAlgoExposure(),
        api.getAlgoOrders(),
        api.getAlgoPositions(),
        api.getAlgoConsent(),
        api.getAlgoStrategies(),
        api.getAlgoAiModels(),
        api.getAlgoAiDrift(),
        api.getAlgoSloDashboard(),
        api.getBrokerCapabilities(),
        api.getAlgoAudit(auditLimit),
      ]);
      if (requestIdRef.current !== requestId) return;

      const failures: string[] = [];

      if (accountResult.status === 'fulfilled') {
        setRestAccount(toTradeAccount(getObj(accountResult.value)?.data));
      } else {
        failures.push(errorMessage(accountResult.reason, 'Algo account unavailable'));
      }
      if (capitalResult.status === 'fulfilled') {
        setCapital(toTradeCapital(capitalResult.value));
      } else {
        failures.push(errorMessage(capitalResult.reason, 'Capital snapshot unavailable'));
      }
      if (exposureResult.status === 'fulfilled') {
        setRestExposure(toTradeExposure(getObj(exposureResult.value)?.data));
      } else {
        failures.push(errorMessage(exposureResult.reason, 'Exposure unavailable'));
      }
      if (ordersResult.status === 'fulfilled') {
        setRestOrders(
          toRecordList(ordersResult.value)
            .map((raw) => toTradeOrder(raw))
            .filter((row): row is TradeOrder => row !== null),
        );
      } else {
        failures.push(errorMessage(ordersResult.reason, 'Orders unavailable'));
      }
      if (positionsResult.status === 'fulfilled') {
        setPositions(
          toRecordList(positionsResult.value)
            .map((raw) => toTradePosition(raw))
            .filter((row): row is TradePosition => row !== null),
        );
      } else {
        failures.push(errorMessage(positionsResult.reason, 'Positions unavailable'));
      }
      if (consentResult.status === 'fulfilled') {
        setConsent(toTradeConsent(consentResult.value));
      } else {
        failures.push(errorMessage(consentResult.reason, 'Consent status unavailable'));
      }
      if (strategiesResult.status === 'fulfilled') {
        setStrategies(
          toRecordList(strategiesResult.value)
            .map((raw) => toStrategyRow(raw))
            .filter((row): row is StrategyRow => row !== null),
        );
      } else {
        failures.push(errorMessage(strategiesResult.reason, 'Strategies unavailable'));
      }
      if (aiModelsResult.status === 'fulfilled') {
        setAiModels(
          toRecordList(aiModelsResult.value)
            .map((raw) => toAiModelRow(raw))
            .filter((row): row is AiModelRow => row !== null),
        );
      } else {
        failures.push(errorMessage(aiModelsResult.reason, 'AI models unavailable'));
      }
      if (driftResult.status === 'fulfilled') {
        setDrift(getObj(getObj(driftResult.value)?.data) ?? null);
      } else {
        failures.push(errorMessage(driftResult.reason, 'Drift metrics unavailable'));
      }
      if (sloResult.status === 'fulfilled') {
        setSlo(getObj(getObj(sloResult.value)?.data) ?? null);
      } else {
        failures.push(errorMessage(sloResult.reason, 'SLO dashboard unavailable'));
      }
      if (capsResult.status === 'fulfilled') {
        setBrokerCaps(getObj(getObj(capsResult.value)?.data) ?? null);
      } else {
        failures.push(errorMessage(capsResult.reason, 'Broker capabilities unavailable'));
      }
      if (auditResult.status === 'fulfilled') {
        setAudit(
          toRecordList(auditResult.value)
            .map((raw) => toTradeAuditRow(raw))
            .filter((row): row is TradeAuditRow => row !== null),
        );
      } else {
        failures.push(errorMessage(auditResult.reason, 'Audit trail unavailable'));
      }

      setError(failures.length > 0 ? failures[0] : null);
      // Honest freshness: backend instants win; fully-failed loads keep last age.
      const settled = [
        accountResult,
        capitalResult,
        exposureResult,
        ordersResult,
        positionsResult,
        consentResult,
        strategiesResult,
        aiModelsResult,
        driftResult,
        sloResult,
        capsResult,
        auditResult,
      ];
      if (settled.some((r) => r.status === 'fulfilled')) {
        const payloadTs = maxPayloadTimestampMs(
          settled.flatMap((r) => {
            if (r.status !== 'fulfilled') return [];
            const v = r.value as unknown;
            const metaTs =
              v !== null && typeof v === 'object' && 'meta' in (v as Record<string, unknown>)
                ? ((v as Record<string, unknown>).meta as Record<string, unknown> | undefined)?.timestamp
                : undefined;
            return [v, metaTs ?? null];
          }),
        );
        setUpdatedAt(payloadTs ?? Date.now());
      }
      setLoading(false);
      if (showSpinner) setRefreshing(false);
    },
    [auditLimit],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  useSmartInterval(
    useCallback(() => load(false), [load]),
    safetyRefreshMs,
    { fireOnMount: false },
  );

  const streamAccount = useMemo(
    () => toTradeAccount(sectionValue?.account),
    [sectionValue?.account],
  );
  const streamExposure = useMemo(
    () => toTradeExposure(sectionValue?.exposure),
    [sectionValue?.exposure],
  );
  const streamOrders = useMemo(() => {
    const raw = sectionValue?.orders;
    if (!Array.isArray(raw)) return null;
    return raw
      .map((entry) => toTradeOrder(entry))
      .filter((row): row is TradeOrder => row !== null);
  }, [sectionValue?.orders]);
  const greeks = useMemo(
    () => getObj(sectionValue?.portfolio_greeks),
    [sectionValue?.portfolio_greeks],
  );

  const account = streamAccount ?? restAccount;
  const accountSource: 'stream' | 'rest' | null = streamAccount
    ? 'stream'
    : restAccount
      ? 'rest'
      : null;
  const exposure = streamExposure ?? restExposure;
  const orders = streamOrders ?? restOrders;
  const ordersSource: 'stream' | 'rest' = streamOrders ? 'stream' : 'rest';
  const mode: TradeMode = normalizeTradeMode(account?.mode);

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const cancelOrder = useCallback(
    async (clientOrderId: string): Promise<TradeOpsActionResult> => {
      try {
        const raw: unknown = await api.cancelAlgoOrder(clientOrderId);
        await load(false);
        const status = statusText(raw) ?? 'CANCELLED';
        return { ok: true, message: `Order cancelled — ${status}.` };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Cancel failed') };
      }
    },
    [load],
  );

  const reconcileOrder = useCallback(
    async (clientOrderId: string): Promise<TradeOpsActionResult> => {
      try {
        const raw: unknown = await api.reconcileAlgoOrder(clientOrderId);
        await load(false);
        const status = statusText(raw);
        return {
          ok: true,
          message: status ? `Order reconciled — ${status}.` : 'Order reconciled with broker.',
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Reconcile failed') };
      }
    },
    [load],
  );

  const exitPosition = useCallback(
    async (positionId: string): Promise<TradeOpsActionResult> => {
      try {
        const raw: unknown = await api.exitAlgoPosition(positionId);
        await load(false);
        const status = statusText(raw);
        return {
          ok: true,
          message: status ? `Exit triggered — ${status}.` : 'Exit triggered.',
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Exit failed') };
      }
    },
    [load],
  );

  const exitAll = useCallback(async (): Promise<TradeOpsActionResult> => {
    try {
      const raw: unknown = await api.exitAllAlgoPositions();
      await load(false);
      const data = getObj(raw)?.data;
      const count = Array.isArray(data)
        ? data.length
        : toNumber(getObj(data)?.closed_count, { coerceNonString: true });
      return {
        ok: true,
        message:
          count !== null ? `Exit triggered on ${count} open position(s).` : 'Exit-all triggered.',
      };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Exit-all failed') };
    }
  }, [load]);

  const previewSizing = useCallback(
    async (payload: Record<string, number>): Promise<SizingPreviewResult> => {
      try {
        const entry = payload.entry_price;
        if (!Number.isFinite(entry) || entry <= 0) {
          return { ok: false, message: 'Entry price must be greater than zero.', preview: null };
        }
        const response: unknown = await api.previewAlgoSizingRisk({
          entry_price: entry,
          stop_price: payload.stop_price ?? null,
          risk_budget: payload.risk_budget ?? null,
          lot_size: payload.lot_size ?? null,
          contract_multiplier: payload.contract_multiplier ?? null,
          max_capital_per_trade: payload.max_capital_per_trade ?? null,
          max_position_size: payload.max_position_size ?? null,
          available_capital: payload.available_capital ?? null,
        });
        const preview = toSizingPreview(response);
        if (!preview) return { ok: false, message: 'Sizing preview returned no quantity.', preview: null };
        return { ok: true, message: 'Sizing preview computed.', preview };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Sizing preview failed'), preview: null };
      }
    },
    [],
  );

  return {
    mode,
    account,
    accountSource,
    exposure,
    orders,
    ordersSource,
    positions,
    capital,
    consent,
    strategies,
    aiModels,
    drift,
    slo,
    brokerCaps,
    greeks,
    audit,
    loading,
    refreshing,
    error,
    updatedAt,
    source: ordersSource,
    liveSource: ordersSource,
    refresh,
    cancelOrder,
    reconcileOrder,
    exitPosition,
    exitAll,
    previewSizing,
  };
}
