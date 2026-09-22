'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileText,
  Lock,
  RefreshCw,
  Scale,
  XCircle,
} from 'lucide-react';
import { papApi, type PapGate, type PapStatus, type PapVerdict } from '@/lib/api/pap';

const VERDICT_TONE: Record<PapVerdict, string> = {
  PASS: 'b-bull',
  FAIL: 'b-warn',
  INCONCLUSIVE: 'b-info',
  NOT_RUN: 'b-neut',
};

const VERDICT_LABEL: Record<PapVerdict, string> = {
  PASS: 'PASS',
  FAIL: 'FAIL',
  INCONCLUSIVE: 'INCONCLUSIVE',
  NOT_RUN: 'NOT RUN',
};

function GateRow({ gate }: { gate: PapGate }) {
  const Icon = gate.passed ? CheckCircle2 : gate.name === 'experiment_report' ? Scale : XCircle;
  return (
    <div className="flex items-start gap-2" data-testid={`pap-gate-${gate.name}`}>
      <Icon size={14} className={gate.passed ? 'text-bull' : 'text-bear'} aria-hidden />
      <div>
        <span className="stat-l font-medium">{gate.name}</span>
        <span className="card-meta block">{gate.detail}</span>
      </div>
    </div>
  );
}

function InstrumentRow({ inst }: { inst: PapStatus['instruments'][number] }) {
  return (
    <tr data-testid={`pap-inst-${inst.slug}`}>
      <td className="font-medium">{inst.instrument}</td>
      <td>
        <span className={`badge ${inst.admissible ? 'b-bull' : 'b-warn'}`}>
          {inst.admissible ? 'admissible' : inst.present ? 'refused' : 'missing'}
        </span>
      </td>
      <td className="num">{inst.source ?? '—'}</td>
      <td className="num">{inst.row_count !== null ? inst.row_count.toLocaleString('en-IN') : '—'}</td>
      <td className="card-meta">
        {inst.reasons.length > 0 ? inst.reasons.join('; ') : 'provenance verified'}
      </td>
    </tr>
  );
}

export function PapResearchPanel() {
  const [status, setStatus] = useState<PapStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isRefresh: boolean) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      setStatus(await papApi.getStatus());
    } catch {
      setError('PAP status unavailable — is the local backend running?');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  if (loading) {
    return (
      <section className="card" aria-label="PAP research status">
        <div className="card-hd">
          <h3 className="card-title">Price Action Prediction</h3>
        </div>
        <div className="card-bd">
          <p className="sg-empty">Loading PAP research status…</p>
        </div>
      </section>
    );
  }

  if (error || !status) {
    return (
      <section className="card" aria-label="PAP research status">
        <div className="card-hd">
          <h3 className="card-title">Price Action Prediction</h3>
        </div>
        <div className="card-bd">
          <p className="sg-err">{error ?? 'PAP status unavailable.'}</p>
        </div>
      </section>
    );
  }

  const dataGate = status.gates.find((g) => g.name === 'real_1m_data');

  return (
    <div className="flex flex-col gap-3">
      <section className="card" aria-label="PAP experiment verdict">
        <div className="card-hd">
          <h3 className="card-title">Price Action Prediction — Stage 1</h3>
          <span className={`badge ${VERDICT_TONE[status.verdict]}`} data-testid="pap-verdict">
            {VERDICT_LABEL[status.verdict]}
          </span>
        </div>
        <div className="card-bd">
          <div className="flex flex-wrap items-center gap-2">
            <span className="stat-chip">
              phase <b>{status.phase}</b>
            </span>
            <span className="stat-chip">
              criteria <b>{status.criteria_version}</b>
            </span>
            <span className="stat-chip">
              horizons <b>{status.horizons.join(' / ')}</b>
            </span>
            <button
              type="button"
              className="btn btn-ic"
              disabled={refreshing}
              onClick={() => void load(true)}
            >
              <RefreshCw size={13} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          <p className="sg-note mt-2">
            PAP is shadow-mode research. It predicts 3/5/10-minute direction distributions and never
            places orders or gates signals. The verdict above comes only from the pre-registered,
            leakage-free walk-forward experiment — never from a live display.
          </p>
        </div>
      </section>

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="card" aria-label="PAP phase gates">
          <div className="card-hd">
            <h3 className="card-title">Phase gates</h3>
            <span className="card-meta num">
              {status.gates.filter((g) => g.passed).length}/{status.gates.length}
            </span>
          </div>
          <div className="card-bd flex flex-col gap-3">
            {status.gates.map((g) => (
              <GateRow key={g.name} gate={g} />
            ))}
          </div>
        </section>

        <section className="card" aria-label="PAP data readiness">
          <div className="card-hd">
            <h3 className="card-title">
              <Database size={13} aria-hidden /> 1m data readiness
            </h3>
            <span className="card-meta num">
              {status.instruments.filter((i) => i.admissible).length}/{status.instruments.length} admissible
            </span>
          </div>
          <div className="card-bd">
            {dataGate && !dataGate.passed ? (
              <p className="sg-err" data-testid="pap-data-blocked">
                Experiment blocked: provenance-verified real 1m data required for every instrument.
                Fixtures and unverifiable datasets are refused by the provenance gate.
              </p>
            ) : null}
            <table className="w-full text-left" data-testid="pap-instruments">
              <thead>
                <tr className="card-meta">
                  <th>Instrument</th>
                  <th>Status</th>
                  <th>Source</th>
                  <th>Rows</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {status.instruments.map((inst) => (
                  <InstrumentRow key={inst.slug} inst={inst} />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" aria-label="PAP pre-registered criteria">
          <div className="card-hd">
            <h3 className="card-title">
              <Lock size={13} aria-hidden /> Pre-registered criteria
            </h3>
            <span className="card-meta num">{status.criteria_version}</span>
          </div>
          <div className="card-bd">
            <div className="sg-kvlist" data-testid="pap-criteria">
              {Object.entries(status.pre_registered).map(([key, value]) => (
                <div className="sg-kv" key={key}>
                  <span className="l">{key.replace(/_/g, ' ')}</span>
                  <span className="v">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <section className="card" aria-label="PAP experiment reports">
        <div className="card-hd">
          <h3 className="card-title">
            <FileText size={13} aria-hidden /> Experiment reports
          </h3>
          <span className="card-meta num">{status.reports.length}</span>
        </div>
        <div className="card-bd">
          {status.reports.length === 0 ? (
            <p className="sg-empty" data-testid="pap-no-reports">
              No experiment reports yet — the Stage 1 runner has not been executed against real data.
            </p>
          ) : (
            <ul className="flex flex-col gap-1" data-testid="pap-reports">
              {status.reports.map((r) => (
                <li key={r.file} className="flex items-center gap-2">
                  {r.verdict === 'PASS' ? (
                    <CheckCircle2 size={13} className="text-bull" aria-hidden />
                  ) : r.verdict === 'FAIL' ? (
                    <AlertTriangle size={13} className="text-bear" aria-hidden />
                  ) : (
                    <AlertTriangle size={13} className="text-muted-foreground" aria-hidden />
                  )}
                  <span className="stat-l">{r.file}</span>
                  <span className="card-meta num">
                    {r.verdict ?? 'unreadable'} · {r.created ?? '—'} · {r.criteria_version ?? '—'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
