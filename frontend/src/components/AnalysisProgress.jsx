/**
 * Determinate progress for a running analysis.
 *
 * `stage_message` is rendered VERBATIM from the API. The backend composes it in
 * services/jobs.py::_stage_message specifically so the count and the wording
 * cannot drift apart, and so a status added later cannot silently render as a
 * blank line. Re-deriving the sentence here would reintroduce exactly that.
 *
 * A bare spinner is not acceptable for an operation this long (docs/ui-patterns.md
 * §4): the user needs stage and count, not motion.
 */
export default function AnalysisProgress({ job }) {
  const { stage_message: stageMessage, completed_chunks: completed, total_chunks: total } = job
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <div className="rounded-md border border-border bg-surface p-6">
      <div className="flex items-baseline justify-between gap-4">
        {/* aria-live so a screen reader user learns the stage changed without
            having to poll the page themselves (design-system.md §6). */}
        <p className="text-sm font-medium text-ink" aria-live="polite">
          {stageMessage}
        </p>
        <p className="font-mono text-xs text-ink-subtle">{pct}%</p>
      </div>

      <div
        className="mt-4 h-1.5 w-full overflow-hidden rounded-sm bg-surface-sunken"
        role="progressbar"
        aria-valuenow={completed}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label="Analysis progress"
      >
        {/* The one inline style in the app, and a deliberate exception to
            "Tailwind classes only". Tailwind generates classes by scanning source
            statically, so a width computed at runtime cannot be one — the
            alternatives are a class per percentage step or a transform, both of
            which are worse. This carries DATA, not styling: every colour, radius
            and duration around it still comes from the token system. */}
        <div
          className="h-full rounded-sm bg-accent transition-[width] duration-150 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="mt-4 text-xs text-ink-subtle">
        Sections are analyzed in parallel, so they do not finish in document order. The count is
        meaningful; the position is not.
      </p>
    </div>
  )
}
