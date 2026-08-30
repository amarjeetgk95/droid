'use client';

import { StrategyLegModel } from '@/lib/types';
import { Plus, Trash2, Layers } from 'lucide-react';

export function StrategyLegsTable({
  legs,
  onUpdateLeg,
  onAddLeg,
  onRemoveLeg,
  spotPrice,
  expiry,
}: {
  legs: StrategyLegModel[];
  onUpdateLeg: (index: number, updated: Partial<StrategyLegModel>) => void;
  onAddLeg: () => void;
  onRemoveLeg: (index: number) => void;
  spotPrice: number;
  expiry: string;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Strategy Legs ({legs.length})</h3>
        </div>
        <button
          onClick={onAddLeg}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-all cursor-pointer shadow-xs"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Option Leg
        </button>
      </div>

      {legs.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border text-muted-foreground text-xs">
          No legs added yet. Select a pre-built template above or click &quot;Add Option Leg&quot; to build a custom structure.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground font-semibold">
                <th className="py-2 px-2">Side</th>
                <th className="py-2 px-2">Type</th>
                <th className="py-2 px-2">Strike</th>
                <th className="py-2 px-2">Expiry</th>
                <th className="py-2 px-2 text-right">Lots</th>
                <th className="py-2 px-2 text-right">Price (₹)</th>
                <th className="py-2 px-2 text-right">IV (%)</th>
                <th className="py-2 px-2 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 font-mono">
              {legs.map((leg, idx) => (
                <tr key={leg.id || idx} className="hover:bg-accent/30 transition-colors">
                  {/* Side (BUY / SELL) */}
                  <td className="py-2 px-2">
                    <button
                      onClick={() => onUpdateLeg(idx, { side: leg.side === 'BUY' ? 'SELL' : 'BUY' })}
                      className={`px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer transition-all ${
                        leg.side === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                          : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                      }`}
                    >
                      {leg.side}
                    </button>
                  </td>

                  {/* Option Type (CE / PE) */}
                  <td className="py-2 px-2">
                    <button
                      onClick={() => onUpdateLeg(idx, { option_type: leg.option_type === 'CE' ? 'PE' : 'CE' })}
                      className={`px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer transition-all ${
                        leg.option_type === 'CE'
                          ? 'bg-primary/20 text-primary border border-primary/40'
                          : 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                      }`}
                    >
                      {leg.option_type}
                    </button>
                  </td>

                  {/* Strike */}
                  <td className="py-2 px-2">
                    <input
                      type="number"
                      value={leg.strike}
                      onChange={(e) => onUpdateLeg(idx, { strike: parseFloat(e.target.value) || spotPrice })}
                      className="w-24 bg-secondary px-2 py-1 rounded border border-border text-foreground font-bold focus:outline-hidden"
                      step={50}
                    />
                  </td>

                  {/* Expiry */}
                  <td className="py-2 px-2 text-muted-foreground">
                    {leg.expiry || expiry}
                  </td>

                  {/* Lots */}
                  <td className="py-2 px-2 text-right">
                    <input
                      type="number"
                      value={leg.quantity}
                      min={1}
                      max={50}
                      onChange={(e) => onUpdateLeg(idx, { quantity: parseInt(e.target.value) || 1 })}
                      className="w-14 bg-secondary px-2 py-1 rounded border border-border text-right text-foreground font-bold focus:outline-hidden"
                    />
                  </td>

                  {/* Price */}
                  <td className="py-2 px-2 text-right">
                    <input
                      type="number"
                      value={leg.price}
                      min={0.05}
                      step={0.5}
                      onChange={(e) => onUpdateLeg(idx, { price: parseFloat(e.target.value) || 0.0 })}
                      className="w-20 bg-secondary px-2 py-1 rounded border border-border text-right text-foreground font-bold focus:outline-hidden"
                    />
                  </td>

                  {/* IV */}
                  <td className="py-2 px-2 text-right">
                    <input
                      type="number"
                      value={Math.round((leg.iv <= 1 ? leg.iv * 100 : leg.iv) * 10) / 10}
                      min={1}
                      max={200}
                      step={0.5}
                      onChange={(e) => onUpdateLeg(idx, { iv: (parseFloat(e.target.value) || 15) / 100 })}
                      className="w-16 bg-secondary px-2 py-1 rounded border border-border text-right text-muted-foreground font-semibold focus:outline-hidden"
                    />
                  </td>

                  {/* Delete Action */}
                  <td className="py-2 px-2 text-center">
                    <button
                      onClick={() => onRemoveLeg(idx)}
                      className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors cursor-pointer"
                      title="Remove Leg"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
