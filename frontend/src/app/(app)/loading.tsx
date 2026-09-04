/**
 * Route-level loading UI for the (app) shell.
 * Shows an instant lightweight skeleton on navigation so route transitions
 * never appear frozen while a page chunk + its first data resolve.
 * No overlays, no timers, no data fetching — purely static markup.
 */
export default function AppLoading() {
  return (
    <div className="space-y-4 pb-8" aria-busy="true" aria-label="Loading page">
      <div className="bg-card border border-border rounded-2xl p-5 h-24 animate-pulse" />
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3.5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="bg-card rounded-xl border border-border p-4 h-44 animate-pulse"
          />
        ))}
      </div>
      <div className="bg-card border border-border rounded-xl p-5 h-72 animate-pulse" />
    </div>
  );
}
