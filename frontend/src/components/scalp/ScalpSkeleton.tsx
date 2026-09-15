'use client';

import React from 'react';

export function ScalpChartSkeleton() {
  return (
    <div className="flex flex-col h-full bg-[#0a0c10] border border-border/80 rounded-lg overflow-hidden animate-pulse">
      <div className="flex items-center justify-between p-2 border-b border-border/60 bg-card/60">
        <div className="h-4 w-40 bg-secondary rounded" />
        <div className="flex gap-2">
          <div className="h-4 w-16 bg-secondary rounded" />
          <div className="h-4 w-12 bg-secondary rounded" />
        </div>
      </div>
      <div className="flex-1 p-4 flex flex-col justify-around opacity-30">
        <div className="h-1 bg-border/40 w-full" />
        <div className="h-1 bg-border/40 w-full" />
        <div className="h-1 bg-border/40 w-full" />
        <div className="h-1 bg-border/40 w-full" />
      </div>
    </div>
  );
}

export function ScalpTicketSkeleton() {
  return (
    <div className="flex flex-col bg-card border border-border rounded-lg p-2.5 animate-pulse gap-2.5">
      <div className="flex justify-between items-center pb-2 border-b border-border/60">
        <div className="h-4 w-28 bg-secondary rounded" />
        <div className="h-4 w-24 bg-secondary rounded" />
      </div>
      <div className="h-10 bg-secondary/50 rounded" />
      <div className="h-8 bg-secondary/30 rounded" />
      <div className="h-12 bg-secondary/40 rounded" />
      <div className="h-12 bg-secondary/40 rounded" />
      <div className="grid grid-cols-2 gap-2 mt-2">
        <div className="h-10 bg-emerald-500/20 rounded-lg" />
        <div className="h-10 bg-rose-500/20 rounded-lg" />
      </div>
    </div>
  );
}

export function ScalpPositionsSkeleton() {
  return (
    <div className="flex flex-col gap-2 p-2 animate-pulse">
      <div className="flex justify-between items-center pb-1 border-b border-border/40">
        <div className="h-4 w-32 bg-secondary rounded" />
        <div className="h-4 w-16 bg-secondary rounded" />
      </div>
      <div className="space-y-1.5 pt-1">
        <div className="h-7 bg-secondary/40 rounded" />
        <div className="h-7 bg-secondary/30 rounded" />
      </div>
    </div>
  );
}
