/**
 * Persistent document identity, above the tabs.
 *
 * This lives outside the tab panels on purpose. When the document title was a
 * heading inside ResultsPanel, opening the Clause navigator unmounted it and the
 * page was left with no `h1` at all — headings started at h2, which is the exact
 * defect fixed one pass earlier, reintroduced by tabs. A heading that describes
 * the whole page cannot sit inside one of its panels.
 *
 * It is also the better reading: which document you are looking at should not
 * depend on which view is open.
 */
export default function DocumentHeader({ document, documentTypeHint }) {
  const partial = document.pages_with_text < document.page_count

  return (
    <header className="shrink-0 border-b border-border bg-surface px-4 py-3">
      <h1 className="truncate font-serif text-xl text-ink">{document.filename}</h1>
      <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-muted">
        <span>{document.page_count} pages</span>
        {partial && (
          /* A part-scanned document analyzed silently is the failure this
             prevents — say how much of it was actually readable. */
          <span className="text-ink-subtle">{document.pages_with_text} with readable text</span>
        )}
        <span aria-hidden="true">·</span>
        <span>{document.chunk_count} sections</span>
        {documentTypeHint && (
          <>
            <span aria-hidden="true">·</span>
            <span className="font-sans text-ink">{documentTypeHint}</span>
          </>
        )}
        <span aria-hidden="true">·</span>
        <span className="text-ink-subtle">{document.extraction_method}</span>
      </p>
    </header>
  )
}
