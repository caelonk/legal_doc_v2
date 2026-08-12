import { Link, useLocation, useParams } from 'react-router-dom'
import AnalysisProgress from '../components/AnalysisProgress'
import AnalysisView from '../components/AnalysisView'
import DocumentHeader from '../components/DocumentHeader'
import { ResultsSkeleton, SourceSkeleton } from '../components/Skeleton'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { useMediaQuery } from '../hooks/useMediaQuery'

// Matches Tailwind's `lg`. Below this the two-pane split stops being useful —
// design-system.md §3 says explicitly not to keep two panes on a phone.
const WIDE = '(min-width: 1024px)'

function Centered({ children }) {
  return <div className="mx-auto max-w-3xl px-4 py-12">{children}</div>
}

/**
 * Announces the outcome to a screen reader.
 *
 * Kept mounted across EVERY branch of this page on purpose. A live region that
 * appears at the same moment as its text is unreliably announced — the region has
 * to already exist for the change to be noticed. AnalysisProgress has its own
 * aria-live for the running stages, but it unmounts on completion, so without
 * this the single most important moment in the flow was silent
 * (design-system.md §6: a screen reader user should not have to poll the page).
 */
function StatusAnnouncer({ job, error }) {
  let message = ''
  if (error) message = `Could not load this analysis. ${error.message}`
  else if (job?.status === 'FAILED') message = `Analysis failed. ${job.error ?? ''}`
  else if (job?.status === 'COMPLETE') {
    const flags = job.result.sections.reduce((n, s) => n + s.analysis.risk_flags.length, 0)
    const skipped = job.result.skipped.length
    message =
      `Analysis complete. ${flags} risk ${flags === 1 ? 'flag' : 'flags'} found` +
      (skipped > 0
        ? `, and ${skipped} ${skipped === 1 ? 'section' : 'sections'} could not be analyzed.`
        : '.')
  }
  return (
    <p aria-live="polite" className="sr-only">
      {message}
    </p>
  )
}

function ErrorState({ title, message }) {
  return (
    <Centered>
      <h1 className="font-serif text-2xl text-ink">{title}</h1>
      <p className="mt-3 max-w-measure text-base text-ink-muted">{message}</p>
      <Link
        to="/"
        className="mt-6 inline-block rounded-md bg-brand px-4 py-2 text-sm font-medium text-surface transition hover:bg-brand-hover"
      >
        Upload a document
      </Link>
    </Centered>
  )
}

export default function Analysis() {
  const { jobId } = useParams()
  const location = useLocation()
  const isWide = useMediaQuery(WIDE)

  const { job, error } = useAnalysisJob(jobId, location.state?.seed ?? null)

  function content() {
    if (error) {
      return <ErrorState title="This analysis could not be loaded" message={error.message} />
    }

    if (!job) {
      return (
        <Centered>
          <p className="text-sm text-ink-muted">Loading analysis…</p>
        </Centered>
      )
    }

    if (job.status === 'FAILED') {
      // A failed run is NOT rendered as an empty result. The backend reports a run
      // where every section failed as FAILED for exactly this reason: "no risks
      // found" is the most dangerous thing this product can say, and it must never
      // be said by accident.
      return <ErrorState title="Analysis failed" message={job.error} />
    }

    if (job.status !== 'COMPLETE') {
      // Skeletons in the final layout rather than a centred card, per
      // ui-patterns.md §4 and design-system.md §5. Two things make this worth it:
      // the page does not jump when the result lands, and the reader can see what
      // kind of thing is coming. The document header is REAL data — it arrives
      // with the 202, before any analysis has run.
      const progress = <AnalysisProgress job={job} />
      const pending = (
        <div className="h-full overflow-y-auto bg-surface-sunken p-4 lg:p-6">
          <div className="space-y-6">
            {progress}
            <ResultsSkeleton />
          </div>
        </div>
      )

      return (
        <div className="flex h-[calc(100vh-3.5rem)] flex-col">
          <DocumentHeader document={job.document} documentType={null} />
          {isWide ? (
            <div className="flex min-h-0 flex-1">
              <div className="min-h-0 w-3/5 border-r border-border">
                <SourceSkeleton pageCount={job.document.page_count} />
              </div>
              <div className="min-h-0 w-2/5">{pending}</div>
            </div>
          ) : (
            <div className="min-h-0 flex-1">{pending}</div>
          )}
        </div>
      )
    }

    // The finished view is shared with the stored-analysis page — same payload
    // shape from both endpoints, so the same component renders both.
    return <AnalysisView result={job.result} reviewKey={jobId} />
  }

  return (
    <>
      <StatusAnnouncer job={job} error={error} />
      {content()}
    </>
  )
}
