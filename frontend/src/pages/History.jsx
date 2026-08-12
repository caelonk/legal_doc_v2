import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, FileText } from 'lucide-react'
import { HistorySkeleton } from '../components/Skeleton'
import { deleteStoredAnalysis, getHistory } from '../api/client'

/**
 * Saved analyses.
 *
 * The list deliberately carries no findings text — the API returns summary
 * columns only, so this page cannot render a conclusion, only a pointer to one.
 * That is why there is no risk badge here: a severity shown without its
 * explanation and its page reference would be a bare conclusion, which
 * .claude/rules/ai-output.md forbids. Counts are safe; claims are not.
 */

function formatDate(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

/**
 * Two-step confirmation, in place of a modal.
 *
 * Deletion here is irreversible and the row is the thing being deleted, so the
 * confirmation belongs on the row. A dialog would also mean a new dependency and
 * a focus trap to get right; this is keyboard-operable with no new machinery, and
 * the destructive verb is never a single stray click.
 */
function DeleteControl({ entry, onDelete, busy }) {
  const [confirming, setConfirming] = useState(false)

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="inline-flex min-h-6 shrink-0 items-center rounded-sm px-2 py-1 text-xs font-medium text-ink-muted transition hover:bg-surface-sunken hover:text-ink"
      >
        Delete
      </button>
    )
  }

  return (
    <span className="flex shrink-0 items-center gap-1">
      {/* Names what is being deleted, so the confirmation is answerable without
          looking back up the row. */}
      <span className="text-xs text-ink-muted">Delete permanently?</span>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="inline-flex min-h-6 items-center rounded-sm px-2 py-1 text-xs font-medium text-ink-muted transition hover:bg-surface-sunken hover:text-ink"
      >
        Cancel
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => onDelete(entry)}
        className="inline-flex min-h-6 items-center rounded-sm bg-risk-high-bg px-2 py-1 text-xs font-medium text-risk-high transition hover:bg-risk-high hover:text-surface disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? 'Deleting…' : 'Delete'}
      </button>
    </span>
  )
}

function Entry({ entry, onDelete, busy }) {
  const saved = formatDate(entry.created_at)
  const partial = entry.skipped_count > 0

  return (
    <li className="flex items-start gap-4 px-4 py-4">
      <FileText size={20} strokeWidth={1.5} aria-hidden="true" className="mt-0.5 shrink-0 text-ink-subtle" />

      <div className="min-w-0 flex-1">
        <h2 className="text-sm font-medium">
          {/* inline-flex + min-h-6 because this is the row's primary target, not a
              link inside a sentence — SC 2.5.8's inline exception does not cover
              it, and the text's own line box is 17px. Same treatment as
              PageReference, for the same reason. */}
          <Link
            to={`/history/${entry.id}`}
            state={{ createdAt: entry.created_at }}
            className="inline-flex min-h-6 items-center rounded-sm text-ink underline-offset-2 hover:underline"
          >
            <span className="break-all">{entry.filename}</span>
          </Link>
        </h2>

        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-muted">
          {saved && <time dateTime={entry.created_at}>{saved}</time>}
          {entry.document_type && (
            <>
              <span aria-hidden="true">·</span>
              <span className="font-sans text-ink">{entry.document_type}</span>
            </>
          )}
          <span aria-hidden="true">·</span>
          <span>
            {entry.risk_flag_count} risk {entry.risk_flag_count === 1 ? 'flag' : 'flags'}
          </span>
          <span aria-hidden="true">·</span>
          <span>{entry.missing_clause_count} missing</span>
          <span aria-hidden="true">·</span>
          <span className="text-ink-subtle">
            {entry.pages_with_text < entry.page_count
              ? `${entry.pages_with_text} of ${entry.page_count} pages readable`
              : `${entry.page_count} pages`}
          </span>
        </p>

        {partial && (
          /* Disclosed in the LIST, not only after opening. A finding count is
             misleading while part of the document was never analyzed, and that is
             most misleading when the count is low. */
          <p className="mt-2 flex items-center gap-1.5 text-xs text-risk-medium">
            <AlertTriangle size={16} strokeWidth={1.5} aria-hidden="true" className="shrink-0" />
            {entry.skipped_count} {entry.skipped_count === 1 ? 'section' : 'sections'} could not be
            analyzed
          </p>
        )}
      </div>

      <DeleteControl entry={entry} onDelete={onDelete} busy={busy} />
    </li>
  )
}

export default function History() {
  const [entries, setEntries] = useState(null)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getHistory({ signal: controller.signal })
      .then((page) => setEntries(page.entries))
      .catch((err) => {
        if (err.name === 'CanceledError' || err.name === 'AbortError') return
        setError(err)
      })
    return () => controller.abort()
  }, [])

  async function handleDelete(entry) {
    setDeleting(entry.id)
    try {
      await deleteStoredAnalysis(entry.id)
      setEntries((current) => current.filter((row) => row.id !== entry.id))
      setAnnouncement(`Deleted the saved analysis of ${entry.filename}.`)
    } catch (err) {
      // Left in the list on failure. Removing a row whose delete did not happen
      // would tell the reader their document is gone when it is not — the one
      // thing a deletion control must never get wrong.
      setError(err)
      setAnnouncement(`Could not delete ${entry.filename}. ${err.message}`)
    } finally {
      setDeleting(null)
    }
  }

  function body() {
    if (error && entries === null) {
      // Storage unreachable. The API answers 503 rather than an empty list
      // precisely so this is not rendered as "you have no documents".
      return (
        <p
          role="alert"
          className="rounded-md border border-risk-medium-border bg-risk-medium-bg px-4 py-3 text-sm text-risk-medium"
        >
          {error.message}
        </p>
      )
    }

    if (entries === null) return <HistorySkeleton />

    if (entries.length === 0) {
      return (
        <div className="rounded-md border border-border bg-surface px-4 py-8 text-center">
          <p className="text-sm text-ink-muted">No saved analyses yet.</p>
          <Link
            to="/"
            className="mt-4 inline-block rounded-md bg-brand px-4 py-2 text-sm font-medium text-surface transition hover:bg-brand-hover"
          >
            Analyze a document
          </Link>
        </div>
      )
    }

    return (
      <ul className="divide-y divide-border rounded-md border border-border bg-surface">
        {entries.map((entry) => (
          <Entry
            key={entry.id}
            entry={entry}
            onDelete={handleDelete}
            busy={deleting === entry.id}
          />
        ))}
      </ul>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      {/* Mounted in every branch, not only once there is something to say — a
          live region created at the same moment as its text is unreliably
          announced. */}
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <h1 className="font-serif text-2xl text-ink">Document history</h1>
      <p className="mt-3 max-w-measure text-base text-ink-muted">
        Analyses you have run. The extracted text and findings are stored; the original PDF is
        not. Entries are deleted automatically once they reach the retention period, and you can
        delete any of them now.
      </p>

      {error && entries !== null && (
        <p
          role="alert"
          className="mt-6 rounded-md border border-risk-high-border bg-risk-high-bg px-4 py-3 text-sm text-risk-high"
        >
          {error.message}
        </p>
      )}

      <div className="mt-8">{body()}</div>
    </div>
  )
}
