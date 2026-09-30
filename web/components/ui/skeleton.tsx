export function Skeleton({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-4" style={{ width: `${i === lines - 1 ? 55 : 100 - (i % 3) * 8}%` }} />
      ))}
    </div>
  );
}

/** A panel-shaped placeholder. The parent marks the region aria-busy. */
export function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-hidden="true" className="rounded border border-rule bg-panel">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="border-t border-rule px-3.5 py-4 first:border-t-0">
          <div className="skeleton mb-2 h-3 w-1/4" />
          <div className="skeleton mb-2 h-5 w-2/3" />
          <div className="skeleton h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}
