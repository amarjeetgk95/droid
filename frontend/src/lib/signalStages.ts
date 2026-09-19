import type { ActiveRow } from '@/lib/signalsNormalize';
import { getObj, pickMs, pickStr } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';

export const SIGNAL_STAGES = ['DETECTED', 'ARMED', 'TRIGGERED', 'EXECUTED', 'CLOSED'] as const;

export type SignalStageId = (typeof SIGNAL_STAGES)[number];

export const STAGE_META: Record<SignalStageId, { label: string; description: string }> = {
  DETECTED: {
    label: 'Detected',
    description: 'Scanner found a setup; confluence still forming',
  },
  ARMED: {
    label: 'Armed',
    description: 'Above threshold, waiting for the trigger to cross',
  },
  TRIGGERED: {
    label: 'Triggered',
    description: 'Trigger crossed; confirmation proof being evaluated',
  },
  EXECUTED: {
    label: 'Executed',
    description: 'Confirmed and auto-filled in the paper book',
  },
  CLOSED: {
    label: 'Closed',
    description: 'Target, stop, time-stop, expiry or invalidation',
  },
};

const STAGE_OF: Record<string, SignalStageId> = {
  DETECTED: 'DETECTED',
  VALIDATED: 'DETECTED',
  ARMED: 'ARMED',
  TRIGGERED: 'TRIGGERED',
  CONFIRMED: 'EXECUTED',
  TARGET_1_HIT: 'EXECUTED',
  TARGET_2_HIT: 'CLOSED',
  STOP_LOSS_HIT: 'CLOSED',
  TIME_STOP_HIT: 'CLOSED',
  RUNNER_TIME_STOP_HIT: 'CLOSED',
  INVALIDATED: 'CLOSED',
  EXPIRED: 'CLOSED',
  CLOSED: 'CLOSED',
};

export function stageOf(state: string | null | undefined): SignalStageId {
  const key = (state ?? '').toUpperCase().trim();
  return STAGE_OF[key] ?? 'DETECTED';
}

export function stageIndex(stage: SignalStageId): number {
  return SIGNAL_STAGES.indexOf(stage);
}

export function stageProgressPct(stage: SignalStageId): number {
  return Math.round((stageIndex(stage) / (SIGNAL_STAGES.length - 1)) * 100);
}

export function isClosedStage(stage: SignalStageId): boolean {
  return stage === 'CLOSED';
}

export function closedOutcome(state: string | null | undefined): 'WIN' | 'LOSS' | 'FLAT' {
  const s = (state ?? '').toUpperCase();
  if (/TARGET_1_HIT|TARGET_2_HIT/.test(s)) return 'WIN';
  if (/STOP_LOSS|TIME_STOP/.test(s)) return 'LOSS';
  return 'FLAT';
}

export type StageGroup = {
  stage: SignalStageId;
  label: string;
  description: string;
  rows: ActiveRow[];
};

export function groupByStage(rows: ActiveRow[]): StageGroup[] {
  const buckets: Record<SignalStageId, ActiveRow[]> = {
    DETECTED: [],
    ARMED: [],
    TRIGGERED: [],
    EXECUTED: [],
    CLOSED: [],
  };
  for (const row of rows) {
    buckets[stageOf(row.state)].push(row);
  }
  for (const stage of SIGNAL_STAGES) {
    buckets[stage].sort((a, b) => (b.timeMs ?? 0) - (a.timeMs ?? 0));
  }
  return SIGNAL_STAGES.map((stage) => ({
    stage,
    label: STAGE_META[stage].label,
    description: STAGE_META[stage].description,
    rows: buckets[stage],
  }));
}

export function ageSeconds(row: ActiveRow, nowMs: number): number | null {
  if (!row.timeMs || nowMs <= 0) return null;
  return Math.max(0, Math.round((nowMs - row.timeMs) / 1000));
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return '—';
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export type ExecutionFillInfo = {
  fillPrice: number | null;
  quantity: number | null;
  optionSymbol: string | null;
  orderId: string | null;
};

export function executionInfo(row: ActiveRow): ExecutionFillInfo {
  const o = row.raw;
  const contract = o.option_contract;
  const contractRecord =
    contract && typeof contract === 'object' ? (contract as Record<string, unknown>) : null;
  const fillPrice = row.entryFill;
  const quantityRaw = o.quantity ?? o.filled_quantity ?? o.intended_qty;
  const quantity =
    typeof quantityRaw === 'number' && Number.isFinite(quantityRaw) ? quantityRaw : null;
  const symbolRaw =
    (typeof o.option_symbol === 'string' && o.option_symbol) ||
    (contractRecord && typeof contractRecord.symbol === 'string' ? contractRecord.symbol : null);
  const orderIdRaw = o.order_id ?? o.paper_order_id;
  return {
    fillPrice,
    quantity,
    optionSymbol: symbolRaw || null,
    orderId: typeof orderIdRaw === 'string' ? orderIdRaw : null,
  };
}

const STATE_LABELS: Record<string, string> = {
  DETECTED: 'Detected',
  VALIDATED: 'Validated',
  ARMED: 'Armed',
  TRIGGERED: 'Triggered',
  CONFIRMED: 'Confirmed / filled',
  TARGET_1_HIT: 'Target 1 hit',
  TARGET_2_HIT: 'Target 2 hit',
  STOP_LOSS_HIT: 'Stop loss hit',
  TIME_STOP_HIT: 'Time stop hit',
  RUNNER_TIME_STOP_HIT: 'Runner time stop',
  INVALIDATED: 'Invalidated',
  EXPIRED: 'Expired',
  CLOSED: 'Closed',
};

export function stateLabel(state: string | null | undefined): string {
  const key = (state ?? '').toUpperCase().trim();
  if (STATE_LABELS[key]) return STATE_LABELS[key];
  if (!key) return '—';
  return key
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export type ChecklistStepStatus = 'done' | 'current' | 'pending' | 'terminal' | 'skipped';

export type ChecklistStep = {
  stage: SignalStageId;
  label: string;
  status: ChecklistStepStatus;
  timestampMs: number | null;
  reachedState: string | null;
  reason: string | null;
};

type ReachedInfo = { ms: number | null; state: string; reason: string | null };

function historyEntries(row: ActiveRow): Array<Record<string, unknown>> {
  const raw = row.raw.state_history;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => getObj(entry))
    .filter((entry): entry is Record<string, unknown> => entry !== null);
}

export function buildStageChecklist(row: ActiveRow): ChecklistStep[] {
  const history = historyEntries(row);
  const reached = new Map<SignalStageId, ReachedInfo>();
  const createdMs = pickMs(row.raw, 'created_at_utc') ?? row.timeMs;

  if (history.length > 0) {
    const firstFrom = pickStr(history[0], 'from_state');
    if (firstFrom) {
      reached.set(stageOf(firstFrom), { ms: createdMs, state: firstFrom, reason: null });
    }
  } else {
    reached.set(stageOf(row.state), { ms: createdMs, state: row.state, reason: null });
  }

  for (const transition of history) {
    const to = pickStr(transition, 'to_state');
    if (!to) continue;
    const stage = stageOf(to);
    const ms = pickMs(transition, 'processed_timestamp');
    const previous = reached.get(stage);
    if (!previous || (previous.ms === null && ms !== null)) {
      reached.set(stage, { ms, state: to, reason: pickStr(transition, 'reason_code') });
    }
  }

  const currentStage = stageOf(row.state);
  const terminal = isClosedStage(currentStage);
  const currentIndex = stageIndex(currentStage);
  const hasHistory = history.length > 0;

  return SIGNAL_STAGES.map((stage, index) => {
    const hit = reached.get(stage);
    let status: ChecklistStepStatus;
    if (hit) {
      status = stage === currentStage ? (terminal ? 'terminal' : 'current') : 'done';
    } else if (stage === currentStage) {
      status = terminal ? 'terminal' : 'current';
    } else if (index < currentIndex) {
      // With transition history present, a missing intermediate stage was
      // genuinely bypassed (e.g. ARMED -> EXPIRED). Without history the log
      // was truncated, so the FSM path must have passed through it.
      status = hasHistory ? 'skipped' : 'done';
    } else {
      status = 'pending';
    }

    const reachedState = hit?.state ?? (stage === currentStage ? row.state : null);
    const label =
      stage === 'CLOSED' && terminal && reachedState
        ? stateLabel(reachedState)
        : STAGE_META[stage].label;

    return {
      stage,
      label,
      status,
      timestampMs: hit?.ms ?? (stage === currentStage ? row.timeMs : null),
      reachedState,
      reason: hit?.reason ?? null,
    };
  });
}

export function matchPosition(
  row: ActiveRow,
  positions: VirtualPosition[],
): VirtualPosition | undefined {
  const open = positions.filter((position) => position.is_open !== false);
  const symbol = executionInfo(row).optionSymbol;
  if (symbol) {
    const exact = open.find((position) => position.symbol === symbol);
    if (exact) return exact;
  }
  const underlying = row.symbol.toUpperCase();
  const candidates = open.filter((position) => position.underlying.toUpperCase() === underlying);
  return candidates.length === 1 ? candidates[0] : undefined;
}

