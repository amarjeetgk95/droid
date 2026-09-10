import { Card } from '@/components/ui/desk';

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
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th colSpan={6} className="c">Calls (CE)</th>
                <th className="c">Strike</th>
                <th colSpan={6} className="c">Puts (PE)</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }).map((_, i) => (
                <tr key={i}>
                  <td colSpan={6} className="r"><div className="skel" style={{ height: 12 }}>.</div></td>
                  <td className="c"><div className="skel" style={{ height: 14, width: 90, margin: '0 auto' }}>.</div></td>
                  <td colSpan={6}><div className="skel" style={{ height: 12 }}>.</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
