import { useRef, useState } from 'react'
import { FileText, Lock, Upload } from 'lucide-react'

const ACCEPTED = '.pdf,application/pdf'

function isPdf(file) {
  // Extension as well as MIME: browsers report an empty type for some drags, and
  // the backend checks magic bytes anyway. This exists to give a fast, specific
  // message, not to be the security boundary.
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Drag-and-drop PLUS a real file-picker button. Drag-only is an accessibility
 * failure (docs/ui-patterns.md §4) — it is unreachable by keyboard and by anyone
 * who cannot execute a drag gesture.
 *
 * The selected file is held here and deliberately survives a failed submit.
 * Wiping the form on a validation error is one of the named anti-patterns in
 * design-system.md §8, and it is especially hostile when the user has to go find
 * a contract on disk again.
 */
export default function UploadZone({ onSubmit, busy, error }) {
  const [file, setFile] = useState(null)
  const [localError, setLocalError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  function accept(candidate) {
    if (!candidate) return
    if (!isPdf(candidate)) {
      // Name the accepted format rather than saying "invalid file".
      setLocalError(`${candidate.name} is not a PDF. This tool accepts text-based PDF files only.`)
      return
    }
    setLocalError(null)
    setFile(candidate)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    accept(event.dataTransfer.files?.[0])
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (file && !busy) onSubmit(file)
  }

  const message = localError || error

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`rounded-md border border-dashed p-8 text-center transition ${
          dragging ? 'border-accent bg-brand-subtle' : 'border-border-strong bg-surface'
        }`}
      >
        <Upload size={20} strokeWidth={1.5} aria-hidden="true" className="mx-auto text-ink-subtle" />
        <p className="mt-3 text-sm text-ink-muted">Drag a PDF here, or</p>

        <input
          ref={inputRef}
          id="document-file"
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          onChange={(e) => accept(e.target.files?.[0])}
        />
        <label
          htmlFor="document-file"
          className="mt-2 inline-flex cursor-pointer items-center gap-2 rounded-md border border-border-strong bg-surface px-4 py-2 text-sm font-medium text-ink transition hover:bg-surface-sunken"
          onKeyDown={(e) => {
            // A <label> is not natively keyboard-activatable. The input itself is
            // sr-only, so without this the control is mouse-only.
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              inputRef.current?.click()
            }
          }}
          tabIndex={0}
          role="button"
        >
          Choose a file
        </label>

        <p className="mt-4 text-xs text-ink-subtle">PDF with a text layer, up to 15 MB</p>
      </div>

      {file && (
        <div className="mt-4 flex items-center gap-3 rounded-md border border-border bg-surface px-4 py-3">
          <FileText size={20} strokeWidth={1.5} aria-hidden="true" className="shrink-0 text-ink-subtle" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{file.name}</p>
            <p className="font-mono text-xs text-ink-subtle">{formatBytes(file.size)}</p>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-surface transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? 'Uploading…' : 'Analyze document'}
          </button>
        </div>
      )}

      {message && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-risk-high-border bg-risk-high-bg px-4 py-3 text-sm text-risk-high"
        >
          {message}
        </p>
      )}

      {/* Trust copy belongs at the moment of hesitation, beside the control —
          not buried in a privacy page (docs/ui-patterns.md §5). */}
      <p className="mt-6 flex items-start gap-2 text-xs text-ink-subtle">
        <Lock size={16} strokeWidth={1.5} aria-hidden="true" className="mt-0.5 shrink-0" />
        <span>
          Your document is sent to the Anthropic API for analysis and held in memory for the
          duration of that analysis. It is not written to disk and not stored after the result
          expires.
        </span>
      </p>
    </form>
  )
}
