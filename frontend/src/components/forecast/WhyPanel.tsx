'use client';

import {
  DirectionBadge,
  Meter,
  fmtINR,
  fmtNum,
  fmtPct01,
  fmtSigned,
  normalizeDirection,
  toneFor,
} from '@/components/ui/desk';

export type WhyPanelProps = {
  explain?: unknown | null;
  fallbackLayerScores?: Record<string, number | null | undefined> | null;
  direction?: string | null;
  confidence?: number | null;
  compact?: boolean;
  invalidationPrice?: number | null;
  targetPrice?: number | null;
};

type MathsRow = {
  domain: string;
  score: number | null;
  weight: number | null;
  points: number | null;
  label: string;
};

type PenaltyRow = {
  rule: string;
  points: number;
};

const LAYER_WEIGHTS: Record<string, number> = {
  mtf_alignment: 0.3,
  indicators: 0.3,
  ml: 0.25,
  options: 0.1,
  structure: 0.05,
};

const DOMAIN_LABEL: Record<string, string> = {
  mtf_alignment: 'Trend agreement across timeframes',
  indicators: 'Momentum gauges (RSI, MACD, VWAP…)',
  ml: 'Machine-learning odds',
  options: 'Options positioning (PCR, walls)',
  structure: 'Chart structure (trend + levels)',
  technical: 'Technical triggers',
  mtf: 'Multi-timeframe agreement',
  fno: 'Futures & options flow',
  regime: 'Market regime fit',
  ai: 'AI assessment',
};

const DOMAIN_SHORT: Record<string, string> = {
  mtf_alignment: 'Trend alignment',
  indicators: 'Indicators',
  ml: 'ML ensemble',
  options: 'Options flow',
  structure: 'Structure',
  technical: 'Technical',
  mtf: 'MTF',
  fno: 'F&O',
  regime: 'Regime',
  ai: 'AI',
};

const EVIDENCE_KEYS = ['spot', 'vwap', 'rsi', 'adx', 'pcr', 'volume'] as const;

function asNum(v: unknown): number | null {
  const n = typeof v === 'string' ? Number(v) : (v as number);
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

function asStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s.length ? s : null;
}

function asStrArray(v: unknown, max: number): string[] {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const item of v) {
    const s = asStr(item);
    if (s) out.push(s);
    if (out.length >= max) break;
  }
  return out;
}

function normalizeConf01(v: unknown): number | null {
  const n = asNum(v);
  if (n === null) return null;
  const scaled = n > 1 ? n / 100 : n;
  if (!Number.isFinite(scaled)) return null;
  return Math.max(0, Math.min(1, scaled));
}

function weightPct(w: number | null): string {
  if (w === null || !Number.isFinite(w)) return '—';
  return `${Math.round(w * 100)}%`;
}

function mathsFromLayerScores(
  layerScores: Record<string, number | null | undefined> | null | undefined,
): MathsRow[] {
  if (!layerScores || typeof layerScores !== 'object') return [];
  const rows: MathsRow[] = [];
  for (const [domain, raw] of Object.entries(layerScores)) {
    const score = asNum(raw);
    if (score === null && raw !== null && raw !== undefined) continue;
    const weight = LAYER_WEIGHTS[domain] ?? null;
    const points = score !== null && weight !== null ? score * weight : score;
    rows.push({
      domain,
      score,
      weight,
      points,
      label: DOMAIN_LABEL[domain] ?? domain.replace(/_/g, ' '),
    });
  }
  const order = ['mtf_alignment', 'indicators', 'ml', 'options', 'structure'];
  rows.sort((a, b) => order.indexOf(a.domain) - order.indexOf(b.domain));
  return rows;
}

function mathsFromConfluence(confluence: unknown): MathsRow[] {
  if (!confluence || typeof confluence !== 'object' || Array.isArray(confluence)) return [];
  const entries = Object.entries(confluence as Record<string, unknown>);
  if (!entries.length) return [];
  const weight = entries.length > 0 ? 1 / entries.length : null;
  return entries.map(([domain, raw]) => {
    const score = asNum(raw);
    return {
      domain,
      score,
      weight,
      points: score !== null && weight !== null ? (score / 100) * 20 * weight * 5 : null,
      label: DOMAIN_LABEL[domain] ?? domain.replace(/_/g, ' '),
    };
  });
}

function getObj(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
  return null;
}

export default function WhyPanel({
  explain,
  fallbackLayerScores,
  direction,
  confidence,
  compact = false,
  invalidationPrice,
  targetPrice,
}: WhyPanelProps) {
  const ex = getObj(explain);
  const signalObj = getObj(ex?.signal) ?? getObj((ex as Record<string, unknown> | null)?.signal);
  const verdictObj = getObj(ex?.verdict);

  // — Direction / confidence (defensive across forecast + signal shapes) —
  const rawDirection =
    asStr(verdictObj?.direction) ??
    asStr(direction) ??
    asStr(signalObj?.direction) ??
    asStr(ex?.direction) ??
    'NEUTRAL';
  const dirNorm = normalizeDirection(rawDirection);

  const rawConf =
    verdictObj?.confidence ?? confidence ?? signalObj?.confidence ?? ex?.confidence ?? null;
  const conf01 = normalizeConf01(rawConf);

  // — Maths —
  let maths: MathsRow[] = [];
  let isFallback = false;
  const rawMaths = ex?.maths;
  if (Array.isArray(rawMaths) && rawMaths.length) {
    maths = rawMaths
      .map((m) => {
        const o = getObj(m);
        if (!o) return null;
        const domain = asStr(o.domain) ?? 'factor';
        const score = asNum(o.score);
        const weight = asNum(o.weight);
        let points = asNum(o.points);
        if (points === null && score !== null && weight !== null) points = score * weight;
        return {
          domain,
          score,
          weight,
          points: points ?? score,
          label: asStr(o.label) ?? DOMAIN_LABEL[domain] ?? domain.replace(/_/g, ' '),
        } as MathsRow;
      })
      .filter((r): r is MathsRow => r !== null);
  }
  if (!maths.length) {
    const confluence = ex?.confluence ?? signalObj?.confluence_breakdown;
    const fromConfluence = mathsFromConfluence(confluence);
    if (fromConfluence.length) maths = fromConfluence;
  }
  if (!maths.length) {
    const layerScores =
      (getObj(ex?.layer_scores) as Record<string, number | null> | null) ??
      (getObj(signalObj?.layer_scores) as Record<string, number | null> | null) ??
      fallbackLayerScores ??
      null;
    maths = mathsFromLayerScores(layerScores ?? undefined);
    if (maths.length) isFallback = !Array.isArray(rawMaths) || !rawMaths.length;
  }
  // If the explain payload IS itself a forecast (has layer_scores at top + no wrapper),
  // mathsFromLayerScores already covered it via ex?.layer_scores.

  const penalties: PenaltyRow[] = Array.isArray(ex?.penalties)
    ? (ex?.penalties as unknown[])
        .map((p) => {
          if (typeof p === 'string') {
            const s = p.trim();
            return s ? { rule: s, points: 0 } : null;
          }
          const o = getObj(p);
          if (!o) return null;
          const rule = asStr(o.rule) ?? asStr(o) ?? 'penalty';
          const points = asNum(o.points) ?? 0;
          return { rule, points };
        })
        .filter((r): r is PenaltyRow => r !== null)
    : [];

  // — Text —
  const whyRaw =
    ex?.why_layman ?? signalObj?.rationale ?? (ex as Record<string, unknown> | null)?.rationale ?? [];
  const why = asStrArray(whyRaw, compact ? 3 : 5);
  const changeRaw = ex?.what_would_change_mind ?? [];
  const changeMind = asStrArray(changeRaw, compact ? 3 : 5);

  // — Evidence —
  const snapshotObj = getObj(ex?.inputs_snapshot) ?? {};
  const levelsObj = getObj(ex?.levels) ?? {};
  const evidence: Record<string, unknown> = { ...snapshotObj };
  const pickFirst = (...keys: string[]): unknown => {
    for (const k of keys) {
      const v = (evidence as Record<string, unknown>)[k] ?? (snapshotObj as Record<string, unknown>)[k];
      if (v !== undefined && v !== null) return v;
    }
    return null;
  };
  evidence.spot = pickFirst('spot', 'current_price', 'current_price_alias') ?? (ex?.current_market_price as unknown) ?? signalObj?.spot_price ?? (levelsObj?.entry_range as unknown) ?? null;
  if (Array.isArray(evidence.spot)) evidence.spot = (evidence.spot as unknown[])[0] ?? null;
  evidence.vwap = pickFirst('vwap');
  evidence.rsi = pickFirst('rsi', 'rsi_14');
  evidence.adx = pickFirst('adx', 'adx_14');
  evidence.pcr = pickFirst('pcr', 'pcr_oi');
  evidence.volume = pickFirst('volume', 'relative_volume', 'volume_ratio', 'current_volume');

  // — Gates —
  let gatesPassed = asStrArray(ex?.gates_passed, 20);
  const gatesRejected = asStrArray(ex?.gates_rejected_by_others, 20);
  if (!gatesPassed.length && !gatesRejected.length && Array.isArray(signalObj?.state_history)) {
    gatesPassed = (signalObj?.state_history as unknown[])
      .map((h) => {
        const o = getObj(h);
        const to = asStr(o?.to_state ?? o?.state ?? o?.fsm_state);
        return to ? `FSM → ${to}` : null;
      })
      .filter((s): s is string => s !== null)
      .slice(0, 10);
  }
  if (!gatesPassed.length && !gatesRejected.length && Array.isArray(ex?.fsm_history)) {
    gatesPassed = (ex?.fsm_history as unknown[])
      .map((h) => {
        const o = getObj(h);
        const to = asStr(o?.to_state ?? o?.state ?? o?.fsm_state);
        return to ? `FSM → ${to}` : null;
      })
      .filter((s): s is string => s !== null)
      .slice(0, 10);
  }

  // — Health / meta —
  const healthObj = getObj(ex?.data_health);
  const healthStatus =
    asStr(healthObj?.status) ?? asStr(ex?.data_quality) ?? asStr(signalObj?.data_quality) ?? null;
  const healthUpper = healthStatus ? healthStatus.toUpperCase() : null;
  const healthTone =
    healthUpper === 'LIVE' ? 'bull' : healthUpper === 'DEGRADED' ? 'warn' : healthUpper === 'OFFLINE' ? 'bear' : 'neut';
  const weightsVersion = asStr(ex?.weights_version) ?? asStr(verdictObj?.weights_version) ?? null;
  const thresholdArmed =
    ex?.threshold_armed !== undefined && ex?.threshold_armed !== null
      ? String(ex.threshold_armed)
      : null;
  const strategyRule =
    asStr(ex?.strategy_rule) ?? asStr(signalObj?.strategy) ?? asStr(ex?.strategy) ?? null;

  const inval =
    asNum(invalidationPrice) ??
    asNum(signalObj?.stop_loss) ??
    asNum(levelsObj?.stop_loss) ??
    asNum(snapshotObj?.invalidation_price) ??
    asNum((snapshotObj?.invalidation as unknown)) ??
    null;
  const target =
    asNum(targetPrice) ??
    asNum(signalObj?.target_1) ??
    asNum(levelsObj?.target_1) ??
    asNum(snapshotObj?.target_price) ??
    null;

  // — Stacked bar —
  const totalAbs =
    maths.reduce((s, m) => s + Math.abs(m.points ?? 0), 0) +
    penalties.reduce((s, p) => s + Math.abs(p.points), 0);
  const barSegments: Array<{ key: string; widthPct: number; color: string; title: string }> = [];
  maths.forEach((m, i) => {
    const pts = m.points ?? 0;
    if (!Number.isFinite(pts) || pts === 0 || totalAbs <= 0) return;
    barSegments.push({
      key: `${m.domain}-${i}`,
      widthPct: (Math.abs(pts) / totalAbs) * 100,
      color: pts >= 0 ? 'var(--ds-bull)' : 'var(--ds-bear)',
      title: `${m.domain}: ${fmtSigned(pts, 1)} pts`,
    });
  });
  penalties.forEach((p, i) => {
    if (!Number.isFinite(p.points) || p.points === 0 || totalAbs <= 0) return;
    barSegments.push({
      key: `penalty-${i}`,
      widthPct: (Math.abs(p.points) / totalAbs) * 100,
      color: 'var(--ds-bear-strong)',
      title: `${p.rule}: ${fmtSigned(p.points, 1)} pts`,
    });
  });

  const hasExplain = ex !== null && Object.keys(ex).length > 0;

  function formatEvidence(key: string, v: unknown): string {
    if (v === null || v === undefined) return '—';
    if (key === 'spot' || key === 'vwap') return fmtINR(v);
    if (key === 'pcr' || key === 'rsi' || key === 'adx') return fmtNum(v, key === 'pcr' ? 2 : 1);
    if (key === 'volume') return fmtNum(v, 0);
    if (typeof v === 'number') return fmtNum(v);
    return String(v);
  }

  return (
    <div
      aria-label="Why this forecast"
      style={{
        marginTop: 14,
        border: '1px solid var(--ds-border)',
        borderRadius: 12,
        background: 'var(--ds-inset)',
        padding: compact ? 12 : 16,
        display: 'grid',
        gap: compact ? 10 : 14,
      }}
    >
      {/* a) Verdict row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
        <DirectionBadge direction={dirNorm} />
        <span className="num" style={{ fontSize: 13, fontWeight: 750 }}>
          {conf01 !== null ? fmtPct01(conf01) : '—'}
        </span>
        <span className="faint" style={{ fontSize: 12 }}>
          confidence
        </span>
        {healthUpper ? (
          <span
            className="badge"
            style={{
              fontSize: 11,
              color:
                healthTone === 'bull'
                  ? 'var(--ds-bull-strong)'
                  : healthTone === 'bear'
                    ? 'var(--ds-bear-strong)'
                    : healthTone === 'warn'
                      ? '#92580a'
                      : 'var(--ds-neut)',
              background:
                healthTone === 'bull'
                  ? 'var(--ds-bull-wash)'
                  : healthTone === 'bear'
                    ? 'var(--ds-bear-wash)'
                    : healthTone === 'warn'
                      ? '#fef3c7'
                      : 'var(--ds-neut-wash)',
              border: '1px solid var(--ds-border)',
            }}
            title={
              healthObj?.fno_degraded !== undefined
                ? `F&O degraded: ${String(healthObj.fno_degraded)} · VWAP coverage: ${String(healthObj?.vwap_coverage ?? '—')}`
                : undefined
            }
          >
            {healthUpper}
          </span>
        ) : null}
        <span style={{ flex: 1 }} />
        {weightsVersion ? (
          <span className="faint mono" style={{ fontSize: 11 }}>
            weights {weightsVersion}
          </span>
        ) : null}
      </div>
      {conf01 !== null && !compact ? <Meter value={conf01} /> : null}

      {!hasExplain || isFallback ? (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          Detailed reasoning unavailable for this older forecast — showing layer-score fallback.
        </p>
      ) : null}

      {/* b) Score maths */}
      <div>
        <div className="faint" style={{ fontSize: 11, fontWeight: 750, letterSpacing: '0.08em', marginBottom: 8 }}>
          SCORE MATHS
        </div>
        {barSegments.length > 0 ? (
          <div
            role="img"
            aria-label="Score contribution bar"
            style={{
              display: 'flex',
              height: 10,
              borderRadius: 999,
              overflow: 'hidden',
              border: '1px solid var(--ds-border)',
              background: 'var(--ds-neut-wash)',
            }}
          >
            {barSegments.map((s) => (
              <div key={s.key} title={s.title} style={{ width: `${s.widthPct}%`, background: s.color }} />
            ))}
          </div>
        ) : (
          <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
            No score breakdown available.
          </p>
        )}
        {maths.length > 0 ? (
          <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
            {maths.map((m) => {
              const mtone = m.points === null ? null : toneFor(m.points);
              return (
                <div
                  key={m.domain}
                  style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 4, alignItems: 'baseline' }}
                >
                  <div style={{ fontSize: 12.5 }}>
                    <span style={{ fontWeight: 700 }}>{DOMAIN_SHORT[m.domain] ?? m.domain}</span>{' '}
                    <span className="faint">· {m.label}</span>
                  </div>
                  <div
                    className={`num ${mtone === 'bull' ? 'v-bull' : mtone === 'bear' ? 'v-bear' : ''}`}
                    style={{ fontSize: 12.5, fontWeight: 750 }}
                  >
                    {m.score !== null ? fmtSigned(m.score, 0) : '—'} · {weightPct(m.weight)} ·{' '}
                    {m.points !== null ? `${fmtSigned(m.points, 1)} pts` : '—'}
                  </div>
                </div>
              );
            })}
            {penalties.length > 0 ? (
              <div style={{ display: 'grid', gap: 4, marginTop: 4 }}>
                {penalties.map((p, i) => (
                  <div key={`${p.rule}-${i}`} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="v-bear">Penalty · {p.rule}</span>
                    <span className="num v-bear" style={{ fontWeight: 750 }}>
                      {fmtSigned(p.points, 1)} pts
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* c) Why in plain English */}
      <div>
        <div className="faint" style={{ fontSize: 11, fontWeight: 750, letterSpacing: '0.08em', marginBottom: 6 }}>
          WHY IN PLAIN ENGLISH
        </div>
        {why.length ? (
          <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 4, fontSize: 13 }}>
            {why.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        ) : (
          <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
            {dirNorm === 'BULLISH'
              ? 'Buyers are slightly stronger across the inputs we track — but no single reason dominates.'
              : dirNorm === 'BEARISH'
                ? 'Sellers are slightly stronger across the inputs we track — but no single reason dominates.'
                : 'Bullish and bearish inputs roughly cancel out, so the model stays neutral.'}
          </p>
        )}
      </div>

      {/* d) Evidence grid */}
      {!compact || Object.values(evidence).some((v) => v !== null && v !== undefined) ? (
        <div>
          <div className="faint" style={{ fontSize: 11, fontWeight: 750, letterSpacing: '0.08em', marginBottom: 8 }}>
            EVIDENCE
          </div>
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
            {EVIDENCE_KEYS.map((k) => (
              <div key={k} className="stat" style={{ background: 'var(--ds-inset-2, transparent)' }}>
                <div className="stat-l">{k}</div>
                <div className="stat-v num" style={{ fontSize: 14 }}>
                  {formatEvidence(k, evidence[k])}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* e) What would change mind */}
      <div>
        <div className="faint" style={{ fontSize: 11, fontWeight: 750, letterSpacing: '0.08em', marginBottom: 6 }}>
          WHAT WOULD CHANGE ITS MIND
        </div>
        {changeMind.length ? (
          <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 4, fontSize: 13 }}>
            {changeMind.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        ) : (
          <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
            A move through the invalidation level or a flip in the weakest scoring layer.
          </p>
        )}
        {inval !== null || target !== null ? (
          <p className="num" style={{ margin: '6px 0 0', fontSize: 12.5 }}>
            {inval !== null ? <span>Invalidation {fmtINR(inval)}</span> : null}
            {inval !== null && target !== null ? <span className="faint"> · </span> : null}
            {target !== null ? <span>Target {fmtINR(target)}</span> : null}
          </p>
        ) : null}
      </div>

      {/* f) Gates */}
      {!compact && (gatesPassed.length > 0 || gatesRejected.length > 0) ? (
        <details
          style={{
            border: '1px solid var(--ds-border)',
            borderRadius: 10,
            padding: '8px 12px',
            background: 'var(--ds-inset-2, transparent)',
          }}
        >
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 700 }}>
            Checks ({gatesPassed.length} passed{gatesRejected.length ? ` · ${gatesRejected.length} rejected by others` : ''})
          </summary>
          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            {gatesPassed.length > 0 ? (
              <div style={{ display: 'grid', gap: 4 }}>
                {gatesPassed.map((g, i) => (
                  <div key={i} style={{ fontSize: 12.5 }}>
                    <span style={{ color: 'var(--ds-bull-strong)', fontWeight: 800 }}>✓ </span>
                    {g}
                  </div>
                ))}
              </div>
            ) : null}
            {gatesRejected.length > 0 ? (
              <div style={{ display: 'grid', gap: 4 }}>
                {gatesRejected.map((g, i) => (
                  <div key={i} className="faint" style={{ fontSize: 12.5 }}>
                    <span>○ </span>
                    {g}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </details>
      ) : null}

      {/* g) Strategy rule + threshold + raw JSON */}
      {!compact ? (
        <div style={{ display: 'grid', gap: 8 }}>
          {strategyRule || thresholdArmed ? (
            <p className="muted" style={{ margin: 0, fontSize: 12 }}>
              {strategyRule ? <span>Rule: {strategyRule}</span> : null}
              {strategyRule && thresholdArmed ? <span> · </span> : null}
              {thresholdArmed ? <span>Threshold armed: {thresholdArmed}</span> : null}
            </p>
          ) : null}
          {hasExplain ? (
            <details>
              <summary className="faint" style={{ cursor: 'pointer', fontSize: 12 }}>
                Raw explain JSON
              </summary>
              <pre
                className="mono"
                style={{
                  fontSize: 11,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  border: '1px solid var(--ds-border)',
                  borderRadius: 8,
                  padding: 10,
                  marginTop: 8,
                  maxHeight: 240,
                  overflow: 'auto',
                }}
              >
                {JSON.stringify(explain, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
