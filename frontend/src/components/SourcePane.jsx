import { forwardRef, useImperativeHandle, useRef } from 'react'

/**
 * The extracted document text — the thing a citation is checked against.
 *
 * MVP renders parser output rather than the PDF itself, so this is a typography
 * problem, not a viewer problem (design-system.md §7): prose at 18px/1.6 on a
 * ~70ch measure over the warm paper surface.
 *
 * Exposes `scrollToPage` so PageReference can drive it. Pages carry stable ids so
 * the lookup cannot drift out of sync with the array index — page numbers are
 * 1-indexed and a page with no text layer still occupies a slot.
 */
// Breathing room above the page a citation lands on, so it does not sit flush
// against the top edge and read as clipped.
const SCROLL_MARGIN = 12

const SourcePane = forwardRef(function SourcePane({ pages }, ref) {
  const containerRef = useRef(null)

  useImperativeHandle(ref, () => ({
    scrollToPage(pageNumber) {
      const container = containerRef.current
      const target = container?.querySelector(`[data-page="${pageNumber}"]`)
      if (!container || !target) return

      // Positioned directly rather than via scrollIntoView({behavior:'smooth'}).
      // Two reasons, and the first is the important one:
      //
      // 1. Following a citation must never silently do nothing. A smooth scroll is
      //    an animation, and an animation that does not run leaves the reader
      //    looking at the wrong page with no feedback. Assigning the offset always
      //    lands, whatever the browser is doing about motion. Measured, not
      //    assumed: smooth scrolling was observed making no progress at all in a
      //    non-compositing viewport, while this path moved correctly.
      // 2. A long animated scroll across several pages is slower and more
      //    disorienting than an instant jump, and design-system.md §5 asks for
      //    restraint and speed over transition theatrics.
      //
      // The temporary highlight below is what orients the reader on arrival, and
      // it does that job better than watching the page fly past.
      const offset =
        target.getBoundingClientRect().top -
        container.getBoundingClientRect().top +
        container.scrollTop
      container.scrollTo({ top: Math.max(offset - SCROLL_MARGIN, 0), behavior: 'auto' })

      // Re-trigger the highlight even when this is the same page as last time —
      // without the reflow the animation would not replay and a repeat click
      // would look like it did nothing.
      target.classList.remove('source-page-hit')
      void target.offsetWidth
      target.classList.add('source-page-hit')
    },
  }))

  return (
    <div ref={containerRef} className="h-full overflow-y-auto bg-surface-sunken p-4 lg:p-6">
      <div className="mx-auto max-w-measure space-y-4">
        {pages.map((page) => (
          <section
            key={page.page_number}
            data-page={page.page_number}
            aria-label={`Page ${page.page_number}`}
            className="scroll-mt-4 rounded-md border border-border bg-surface-paper px-6 py-6 shadow-sm md:px-8"
          >
            <p className="mb-4 font-mono text-xs uppercase tracking-wide text-ink-subtle">
              Page {page.page_number}
            </p>

            {page.text.trim() ? (
              <div className="whitespace-pre-wrap text-lg text-ink">{page.text}</div>
            ) : (
              /* A page that rendered but carried no text layer — a scanned
                 exhibit or a full-page diagram. Said plainly, because this is
                 also why no finding can ever cite this page. */
              <p className="text-sm italic text-ink-subtle">
                No text could be extracted from this page. It is likely a scanned image or a
                diagram, and nothing in the analysis can be attributed to it.
              </p>
            )}
          </section>
        ))}
      </div>
    </div>
  )
})

export default SourcePane
