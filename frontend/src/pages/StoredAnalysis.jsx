import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import AnalysisView from '../components/AnalysisView'
import { ResultsSkeleton, SourceSkeleton } from '../components/Skeleton'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { deleteStoredAnalysis, getStoredAnalysis } from '../api/client'

const WIDE = '(min-width: 1024px)'

function Centered({ children }) {
  return <div className="mx-auto max-w-3xl px-4 py-12">{children}</div>
}

function formatDate(iso) {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

/**
 * Actions that belong to the STORED copy rather than to the analysis.
 *
 * Two-step delete, matching the history list: this is irreversible, and the
 * reader is one click from losing a document they came back to read.
 */
function Toolbar({ savedAt, onDelete, busy, error }) {
  const [confirming, setConfirming] = useState(false)
  const saved = formatDate(savedAt)

  return (
    <div className="shrink-0 border-b border-border bg-surface-sunken px-4 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Link
          to="/history"
          className="inline-flex min-h-6 items-center gap-1 rounded-sm text-xs font-medium text-accent underline-offset-2 hover:underline"
        >
          <ChevronLeft size={16} strokeWidth={1.5} aria-hidden="true" />
          Document history
        </Link>

        {saved && (
          <span className="font-mono text-xs text-ink-muted">
            Saved <time dateTime={savedAt}>{saved}</time>
          </span>
        )}

        <span className="ml-auto flex items-center gap-1">
          {confirming ? (
            <>
              <span className="text-xs text-ink-muted">Delete permanently?</span>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="inline-flex min-h-6 items-center rounded-sm px-2 py-1 text-xs font-medium text-ink-muted transition hover:bg-surface hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={onDelete}
                className="inline-flex min-h-6 items-center rounded-sm bg-risk-high-bg px-2 py-1 text-xs font-medium text-risk-high transition hover:bg-risk-high hover:text-surface disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? 'Deleting…' : 'Delete'}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="inline-flex min-h-6 items-center rounded-sm px-2 py-1 text-xs font-medium text-ink-muted transition hover:bg-surface hover:text-ink"
            >
              Delete this analysis
            </button>
          )}
        </span>
      </div>

      {error && (
        <p role="alert" className="mt-2 text-xs text-risk-high">
          {error.message}
        </p>
      )}
    </div>
  )
}

/**
 * A saved analysis, opened from history.
 *
 * Rendered by the same `AnalysisView` a just-finished analysis uses, because the
 * API returns the identical payload from both endpoints. A stored analysis is
 * exactly what a reader returns to in order to check a claim, so it must carry the
 * same citations, the same disclosure, and the same skipped-section reporting —
 * not a read-only summary of them.
 */
export default function StoredAnalysis() {
  const { analysisId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const isWide = useMediaQuery(WIDE)

  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [deleteError, setDeleteError] = useState(null)
  const [deleting, setDeleting] = useState(false)

  // Carried from the list so the page can say when this was saved without adding
  // a field to the analysis payload. Absent on a direct URL load, and the line is
  // simply omitted then rather than guessed at.
  const savedAt = location.state?.createdAt ?? null

  useEffect(() => {
    const controller = new AbortController()
    setResult(null)
    setError(null)
    getStoredAnalysis(analysisId, { signal: controller.signal })
      .then(setResult)
      .catch((err) => {
        if (err.name === 'CanceledError' || err.name === 'AbortError') return
        setError(err)
      })
    return () => controller.abort()
  }, [analysisId])

  async function handleDelete() {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteStoredAnalysis(analysisId)
      navigate('/history', { replace: true })
    } catch (err) {
      // Stay on the page. Navigating away after a failed delete would imply the
      // document is gone when it is not.
      setDeleteError(err)
      setDeleting(false)
    }
  }

  const announcement = error
    ? `Could not open this saved analysis. ${error.message}`
    : result
      ? `Saved analysis loaded. ${result.aggregate.risk_flags.length} risk ` +
        `${result.aggregate.risk_flags.length === 1 ? 'flag' : 'flags'}.`
      : ''

  function content() {
    if (error) {
      return (
        <Centered>
          <h1 className="font-serif text-2xl text-ink">This analysis could not be opened</h1>
          <p className="mt-3 max-w-measure text-base text-ink-muted">{error.message}</p>
          <Link
            to="/history"
            className="mt-6 inline-block rounded-md bg-brand px-4 py-2 text-sm font-medium text-surface transition hover:bg-brand-hover"
          >
            Back to document history
          </Link>
        </Centered>
      )
    }

    if (!result) {
      // Skeletons in the final layout, matching the analysis page: the page does
      // not jump when the payload lands. There is no page count to work from
      // before the response, so SourceSkeleton uses its own default.
      return (
        <div className="flex h-[calc(100vh-3.5rem)] flex-col">
          <div className="shrink-0 border-b border-border bg-surface px-4 py-3">
            <p className="text-sm text-ink-muted">Opening saved analysis…</p>
          </div>
          {isWide ? (
            <div className="flex min-h-0 flex-1">
              <div className="min-h-0 w-3/5 border-r border-border">
                <SourceSkeleton />
              </div>
              <div className="min-h-0 w-2/5 overflow-y-auto bg-surface-sunken p-4 lg:p-6">
                <ResultsSkeleton />
              </div>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto bg-surface-sunken p-4">
              <ResultsSkeleton />
            </div>
          )}
        </div>
      )
    }

    return (
      <AnalysisView
        result={result}
        reviewKey={analysisId}
        toolbar={
          <Toolbar
            savedAt={savedAt}
            onDelete={handleDelete}
            busy={deleting}
            error={deleteError}
          />
        }
      />
    )
  }

  return (
    <>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {content()}
    </>
  )
}
