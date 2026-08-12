import { useRef } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import AnalysisProgress from '../components/AnalysisProgress'
import ResultsPanel from '../components/ResultsPanel'
import SourcePane from '../components/SourcePane'
import { useAnalysisJob } from '../hooks/useAnalysisJob'

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
  const sourceRef = useRef(null)

  const { job, error } = useAnalysisJob(jobId, location.state?.seed ?? null)

  const navigateToPage = (page) => sourceRef.current?.scrollToPage(page)

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
      return (
        <Centered>
          <h1 className="font-serif text-2xl text-ink">{job.document.filename}</h1>
          <p className="mt-2 font-mono text-sm text-ink-subtle">
            {job.document.page_count} pages · {job.document.chunk_count} sections
          </p>
          <div className="mt-8">
            <AnalysisProgress job={job} />
          </div>
        </Centered>
      )
    }

    return (
      // Split pane: source left (~60%), findings right (~40%). The dominant layout
      // in legal review tools, because it lets a reader check a claim against the
      // source without losing their place (design-system.md §3).
      //
      // Below lg it stacks. Pass 2 replaces the stack with proper tabs — two panes
      // on a phone helps nobody.
      <div className="flex h-[calc(100vh-3.5rem)] flex-col lg:flex-row">
        <div className="min-h-0 flex-1 border-border lg:w-3/5 lg:border-r">
          <SourcePane ref={sourceRef} pages={job.result.pages} />
        </div>
        <div className="min-h-0 flex-1 lg:w-2/5">
          <ResultsPanel result={job.result} onNavigate={navigateToPage} />
        </div>
      </div>
    )
  }

  return (
    <>
      <StatusAnnouncer job={job} error={error} />
      {content()}
    </>
  )
}
