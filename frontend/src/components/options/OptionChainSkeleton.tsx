import { Card } from '@/components/ui/desk';

const CALL_HEADS = ['OI', 'Vol', 'Bid', 'Ask', 'LTP', 'IV%'] as const;
const PUT_HEADS = ['IV%', 'LTP', 'Bid', 'Ask', 'Vol', 'OI'] as const;

/**
 * OptionChainSkeleton
 *
 * Structural skeleton matching the 13-column layout of OptionChainTable
 * (Calls CE | Strike | Puts PE). Uses the sober `.skel` blocks so no
 * layout shift occurs while the chain loads.
 */
export function OptionChainSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: 12 }} aria-busy="true" aria-label="Loading option chain">
      <section className="card" aria-hidden>
        <div className="card-hd">
          <h2 className="card-title">Options desk</h2>
          <span className="card-meta">loading…</span>
        </div>
        <div className="card-bd">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <div className="skel" style={{ height: 30, width: 220 }}>.</div>
            <div className="skel" style={{ height: 30, width: 160 }}>.</div>
          </div>
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginTop: 12 }}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skel" style={{ height: 64 }}>.</div>
            ))}
          </div>
        </div>
      </section>

      <Card title="Option chain" meta="loading…">
        <div
          className="tbl-scroll"
          style={{ maxHeight: 640, border: '1px solid var(--ds-border)', borderRadius: 4 }}
          aria-hidden
        >
          <table className="tbl">
            <thead>
              <tr className="c">
                <th colSpan={6} style={{ background: 'var(--ds-bull-wash)' }}>Calls · CE</th>
                <th rowSpan={2} className="c" style={{ background: 'var(--ds-accent-wash)' }}>Strike</th>
                <th colSpan={6} style={{ background: 'var(--ds-bear-wash)' }}>Puts · PE</th>
              </tr>
              <tr>
                {CALL_HEADS.map((head) => (
                  <th key={`ce-${head}`} className="r">{head}</th>
                ))}
                {PUT_HEADS.map((head) => (
                  <th key={`pe-${head}`}>{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 13 }).map((__, j) => (
                    <td key={j} className={j === 6 ? 'c' : j < 6 ? 'r' : undefined}>
                      <div
                        className="skel"
                        style={j === 6 ? { height: 14, width: 90, margin: '0 auto' } : { height: 12 }}
                      >
                        .
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
