/**
 * The provenance affordance — the highest-value element in the product.
 *
 * Two states, and the second one matters more than it looks:
 *
 *   number -> a clickable `p. 12` that scrolls the source pane to that page and
 *             highlights it, so a claim can be checked against the text it came
 *             from.
 *   null   -> an explicit, muted "Source not located".
 *
 * The null state is NEVER hidden and NEVER filled in with a guess. A visibly
 * missing citation is honest; a silently absent one looks like the claim was
 * verified when it was not. This is the UI half of the backend's page-reference
 * rules, where analyzer._sanitize_page_references nulls anything the parser did
 * not supply — that null arrives here meaning "we do not know", and it has to
 * still mean that on screen.
 */
export default function PageReference({ page, onNavigate }) {
  if (page === null || page === undefined) {
    return (
      <span className="font-mono text-xs text-ink-subtle" title="No page could be attributed to this finding">
        Source not located
      </span>
    )
  }

  return (
    <button
      type="button"
      onClick={() => onNavigate?.(page)}
      // min-h-6 is 24px: WCAG 2.2 SC 2.5.8 minimum target size, which
      // design-system.md §6 calls a build requirement rather than polish. At the
      // text's natural 17px this control failed that, and it is the one users
      // click most. The negative inline margin keeps the citation visually tight
      // against the text while the hit area stays full size.
      className="-mx-1 inline-flex min-h-6 items-center rounded-sm px-1 font-mono text-xs text-accent underline decoration-transparent underline-offset-2 transition hover:decoration-current"
      aria-label={`Go to page ${page} in the source document`}
    >
      p. {page}
    </button>
  )
}
