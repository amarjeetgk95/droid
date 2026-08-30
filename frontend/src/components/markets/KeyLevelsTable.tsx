'use client';

import { KeyLevelsModel } from '@/lib/types';
import { Layers } from 'lucide-react';

export function KeyLevelsTable({
  keyLevels,
  spotPrice,
}: {
  keyLevels: KeyLevelsModel | null;
  spotPrice: number;
}) {
  if (!keyLevels) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
        No key levels or pivot points available.
      </div>
    );
  }

  const cp = keyLevels.classic_pivots;
  const fp = keyLevels.fibonacci_pivots;
  const cam = keyLevels.camarilla_pivots;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Support & Resistance Multi-Model Ladder</h3>
        </div>
        <div className="text-xs font-mono text-muted-foreground">
          Current Spot: <strong className="text-foreground font-bold">₹{spotPrice.toLocaleString('en-IN')}</strong>
        </div>
      </div>

      {/* Pivots Comparison Matrix */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="py-2 px-3">Level Tier</th>
              <th className="py-2 px-3 text-right">Classic Floor</th>
              <th className="py-2 px-3 text-right">Fibonacci</th>
              <th className="py-2 px-3 text-right">Camarilla</th>
              <th className="py-2 px-3 text-right">Proximity to Spot</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono">
            {/* R4 */}
            {cam.r4 && (
              <tr className="hover:bg-accent/40 text-destructive/90">
                <td className="py-2 px-3 font-sans font-bold">Resistance 4 (R4 - Breakout)</td>
                <td className="py-2 px-3 text-right">---</td>
                <td className="py-2 px-3 text-right">---</td>
                <td className="py-2 px-3 text-right font-bold">₹{cam.r4}</td>
                <td className="py-2 px-3 text-right text-muted-foreground">
                  +{(cam.r4 - spotPrice).toFixed(1)} pts
                </td>
              </tr>
            )}

            {/* R3 */}
            <tr className="hover:bg-accent/40 text-destructive">
              <td className="py-2 px-3 font-sans font-bold">Resistance 3 (R3)</td>
              <td className="py-2 px-3 text-right">₹{cp.r3}</td>
              <td className="py-2 px-3 text-right">₹{fp.r3}</td>
              <td className="py-2 px-3 text-right font-bold">₹{cam.r3}</td>
              <td className="py-2 px-3 text-right text-muted-foreground">
                +{(cp.r3 - spotPrice).toFixed(1)} pts
              </td>
            </tr>

            {/* R2 */}
            <tr className="hover:bg-accent/40 text-destructive/80">
              <td className="py-2 px-3 font-sans font-medium">Resistance 2 (R2)</td>
              <td className="py-2 px-3 text-right">₹{cp.r2}</td>
              <td className="py-2 px-3 text-right">₹{fp.r2}</td>
              <td className="py-2 px-3 text-right">₹{cam.r2}</td>
              <td className="py-2 px-3 text-right text-muted-foreground">
                +{(cp.r2 - spotPrice).toFixed(1)} pts
              </td>
            </tr>

            {/* R1 */}
            <tr className="hover:bg-accent/40 text-destructive/70">
              <td className="py-2 px-3 font-sans font-medium">Resistance 1 (R1)</td>
              <td className="py-2 px-3 text-right">₹{cp.r1}</td>
              <td className="py-2 px-3 text-right">₹{fp.r1}</td>
              <td className="py-2 px-3 text-right">₹{cam.r1}</td>
              <td className="py-2 px-3 text-right text-muted-foreground">
                +{(cp.r1 - spotPrice).toFixed(1)} pts
              </td>
            </tr>

            {/* Central Pivot */}
            <tr className="bg-primary/10 hover:bg-primary/15 font-bold text-foreground">
              <td className="py-2.5 px-3 font-sans flex items-center gap-1.5 text-primary">
                ★ Central Pivot Point (P)
              </td>
              <td className="py-2.5 px-3 text-right font-extrabold text-primary">₹{cp.pivot}</td>
              <td className="py-2.5 px-3 text-right font-extrabold text-primary">₹{fp.pivot}</td>
              <td className="py-2.5 px-3 text-right font-extrabold text-primary">₹{cam.pivot}</td>
              <td className="py-2.5 px-3 text-right font-sans text-xs">
                {(spotPrice - cp.pivot) >= 0 ? `+${(spotPrice - cp.pivot).toFixed(1)} above P` : `${(spotPrice - cp.pivot).toFixed(1)} below P`}
              </td>
            </tr>

            {/* S1 */}
            <tr className="hover:bg-accent/40 text-success/70">
              <td className="py-2 px-3 font-sans font-medium">Support 1 (S1)</td>
              <td className="py-2 px-3 text-right">₹{cp.s1}</td>
              <td className="py-2 px-3 text-right">₹{fp.s1}</td>
              <td className="py-2 px-3 text-right">₹{cam.s1}</td>
              <td className="py-2 px-3 text-right text-muted-foreground">
                -{(spotPrice - cp.s1).toFixed(1)} pts
              </td>
            </tr>

            {/* S2 */}
            <tr className="hover:bg-accent/40 text-success/80">
              <td className="py-2 px-3 font-sans font-medium">Support 2 (S2)</td>
              <td className="py-2 px-3 text-right">₹{cp.s2}</td>
              <td className="py-2 px-3 text-right">₹{fp.s2}</td>
              <td className="py-2 px-3 text-right">₹{cam.s2}</td>
              <td className="py-2 px-3 text-right text-muted-foreground">
                -{(spotPrice - cp.s2).toFixed(1)} pts
              </td>
            </tr>

            {/* S3 */}
            <tr className="hover:bg-accent/40 text-success">
              <td className="py-2 px-3 font-sans font-bold">Support 3 (S3)</td>
              <td className="py-2 px-3 text-right">₹{cp.s3}</td>
              <td className="py-2 px-3 text-right">₹{fp.s3}</td>
              <td className="py-2 px-3 text-right font-bold">₹{cam.s3}</td>
              <td className="py-2 px-3 text-right text-muted-foreground">
                -{(spotPrice - cp.s3).toFixed(1)} pts
              </td>
            </tr>

            {/* S4 */}
            {cam.s4 && (
              <tr className="hover:bg-accent/40 text-success/90">
                <td className="py-2 px-3 font-sans font-bold">Support 4 (S4 - Breakdown)</td>
                <td className="py-2 px-3 text-right">---</td>
                <td className="py-2 px-3 text-right">---</td>
                <td className="py-2 px-3 text-right font-bold">₹{cam.s4}</td>
                <td className="py-2 px-3 text-right text-muted-foreground">
                  -{(spotPrice - cam.s4).toFixed(1)} pts
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Volume Profile Value Area & Reference Levels */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-border text-xs">
        <div className="bg-secondary/40 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">POC (Point of Control)</span>
          <span className="font-bold font-mono text-primary text-sm">₹{keyLevels.poc}</span>
          <span className="text-[10px] text-muted-foreground block">Max Executed Volume</span>
        </div>

        <div className="bg-secondary/40 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Value Area High (VAH)</span>
          <span className="font-bold font-mono text-foreground text-sm">₹{keyLevels.vah}</span>
          <span className="text-[10px] text-muted-foreground block">70% Volume Cutoff Upper</span>
        </div>

        <div className="bg-secondary/40 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Value Area Low (VAL)</span>
          <span className="font-bold font-mono text-foreground text-sm">₹{keyLevels.val}</span>
          <span className="text-[10px] text-muted-foreground block">70% Volume Cutoff Lower</span>
        </div>

        <div className="bg-secondary/40 p-2.5 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Prior Day High / Low</span>
          <span className="font-bold font-mono text-foreground text-sm">
            ₹{keyLevels.prior_day_high} / ₹{keyLevels.prior_day_low}
          </span>
          <span className="text-[10px] text-muted-foreground block">Close: ₹{keyLevels.prior_day_close}</span>
        </div>
      </div>
    </div>
  );
}
