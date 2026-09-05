/**
 * Route-level loading UI for the (app) shell.
 * Shows an instant lightweight skeleton on navigation so route transitions
 * never appear frozen while a page chunk + its first data resolve.
 * No overlays, no timers, no data fetching — purely static markup.
 */
export default function AppLoading() {
  return (
    <div className="space-y-4 pb-8" aria-busy="true" aria-label="Loading workspace">
      {/* Top Header / Control Strip Wireframe */}
      <div className="bg-card border border-border rounded-xl p-3 h-12 animate-pulse flex items-center justify-between">
        <div className="h-4 bg-muted rounded w-40" />
        <div className="h-4 bg-muted rounded w-28 hidden sm:block" />
      </div>
      {/* Sub-strip metric wireframe */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="bg-card rounded-xl border border-border p-3.5 h-20 animate-pulse flex flex-col justify-between">
            <div className="h-3 bg-muted rounded w-16" />
            <div className="h-5 bg-muted rounded w-24" />
          </div>
        ))}
      </div>
      {/* Main Workspace Body Wireframe */}
      <div className="bg-card border border-border rounded-xl p-5 h-[520px] animate-pulse" />
    </div>
  );
}
