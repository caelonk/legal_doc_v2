/**
 * Loading placeholders shaped like the thing that is coming.
 *
 * docs/ui-patterns.md §4 and design-system.md §5 both ask for skeletons matching
 * the final layout rather than a centered spinner, for anything over ~400ms — and
 * a chunked analysis runs for tens of seconds. The point is not decoration: a
 * placeholder that matches the real shape means the page does not jump when the
 * result lands, and the reader can see what kind of thing they are waiting for.
 *
 * All of this is aria-hidden. The real status is already carried by the
 * determinate progress bar and the page's live region; a screen reader announcing
 * a dozen empty boxes would be noise on top of information that is already there.
 *
 * The pulse is Tailwind's animate-pulse, which globals.css disables wholesale
 * under prefers-reduced-motion.
 */

export function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-sm bg-border ${className}`} />
}

function SkeletonRow() {
  return (
    <div className="border-b border-border px-4 py-3 last:border-b-0">
      <div className="flex items-start gap-4">
        <Skeleton className="h-5 w-16 shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
        <Skeleton className="h-3 w-10 shrink-0" />
      </div>
    </div>
  )
}

/** Mirrors ResultsPanel: disclosure bar, a section heading, then finding rows. */
export function ResultsSkeleton({ rows = 5 }) {
  return (
    <div aria-hidden="true" className="space-y-6">
      <Skeleton className="h-12 w-full" />
      <div>
        <Skeleton className="h-6 w-32" />
        <div className="mt-3 rounded-md border border-border bg-surface">
          {Array.from({ length: rows }, (_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      </div>
    </div>
  )
}

/**
 * Mirrors SourcePane. The page COUNT is real — it arrives with the 202, before
 * any analysis has run — so the placeholder is the right length even though the
 * text itself only arrives with the finished result.
 */
export function SourceSkeleton({ pageCount = 3 }) {
  // A long document should not render two hundred placeholder cards; a few
  // establish the shape and the rest would never be scrolled to during loading.
  const shown = Math.min(pageCount, 4)

  return (
    <div aria-hidden="true" className="h-full overflow-hidden bg-surface-sunken p-4 lg:p-6">
      <div className="mx-auto max-w-measure space-y-4">
        {Array.from({ length: shown }, (_, i) => (
          <div key={i} className="rounded-md border border-border bg-surface-paper px-6 py-6 md:px-8">
            <Skeleton className="mb-4 h-3 w-16" />
            <div className="space-y-2.5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
