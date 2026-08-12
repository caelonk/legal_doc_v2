import { Check } from 'lucide-react'
import RiskBadge from './RiskBadge'
import {
  collectRiskFlags,
  countBySeverity,
  partitionByLocated,
  sortByDocumentPosition,
} from '../lib/severity'

/**
 * The aggregate jump list: every flagged location, in document order
 * (docs/ui-patterns.md §1).
 *
 * Ordered by POSITION, not severity — that is the whole reason it exists
 * alongside the risk table. The table answers "what is the worst thing in here";
 * this answers "where are the problems as I read through". Sorting both the same
 * way would make one of them redundant.
 *
 * Severity still renders as colour + icon + text label on every entry, via
 * RiskBadge. A compact rail is exactly where the temptation is to drop to an icon
 * or a coloured dot, and that is the case the rule exists to forbid.
 */

function NavigatorEntry({ flag, onNavigate, isReviewed }) {
  const located = flag.page_reference !== null && flag.page_reference !== undefined

  const body = (
    <>
      <span className="flex items-center justify-between gap-2">
        <RiskBadge severity={flag.severity} />
        {located ? (
          <span className="font-mono text-xs text-accent">p. {flag.page_reference}</span>
        ) : (
          <span className="font-mono text-xs text-ink-subtle">no page</span>
        )}
      </span>
      <span className="mt-1.5 flex items-center gap-1.5 text-sm text-ink">
        {/* Reviewed state is shared with the findings table rather than tracked
            separately — the two are views of the same findings, and a mark made
            in one that did not show in the other would read as a bug. Shown as
            icon plus text, never the icon alone. */}
        {isReviewed && (
          <span className="inline-flex shrink-0 items-center gap-1 font-mono text-xs text-ink-subtle">
            <Check size={16} strokeWidth={1.5} aria-hidden="true" className="text-accent" />
            Reviewed
          </span>
        )}
        <span className={isReviewed ? 'text-ink-muted' : undefined}>{flag.clause_type}</span>
      </span>
    </>
  )

  if (!located) {
    // Listed, but not offered as a jump — there is nowhere to jump to. Rendering
    // it as a dead button would be worse than rendering it as text.
    return (
      <li className="border-b border-border px-4 py-3 last:border-b-0">
        <span className="block">{body}</span>
      </li>
    )
  }

  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => onNavigate?.(flag.page_reference)}
        className="w-full px-4 py-3 text-left transition hover:bg-brand-subtle"
        aria-label={`${flag.clause_type}, ${flag.severity.toLowerCase()} severity, page ${flag.page_reference}`}
      >
        {body}
      </button>
    </li>
  )
}

export default function ClauseNavigator({ result, onNavigate, reviewed = new Set() }) {
  const flags = collectRiskFlags(result)
  const counts = countBySeverity(flags)
  const { located, unlocated } = partitionByLocated(flags)
  const ordered = sortByDocumentPosition(located)

  return (
    <nav aria-label="Flagged clauses" className="h-full overflow-y-auto bg-surface-sunken">
      <div className="border-b border-border bg-surface px-4 py-3">
        <h2 className="font-serif text-xl text-ink">Clause navigator</h2>
        <p className="mt-1 font-mono text-xs text-ink-muted">
          {counts.HIGH} high · {counts.MEDIUM} medium · {counts.LOW} low
        </p>
        <p className="mt-1 text-xs text-ink-subtle">In document order.</p>
      </div>

      {flags.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-muted">
          No risk-flagged clauses to navigate. That is not a clean bill of health — read the
          document and confirm for yourself.
        </p>
      ) : (
        <>
          <ul className="bg-surface">
            {ordered.map((flag) => (
              <NavigatorEntry
                key={flag.key}
                flag={flag}
                onNavigate={onNavigate}
                isReviewed={reviewed.has(flag.key)}
              />
            ))}
          </ul>

          {unlocated.length > 0 && (
            /* Surfaced under their own heading rather than omitted. A finding the
               parser could not place is still a finding, and dropping it from the
               jump list would quietly shrink the count the header just gave. */
            <>
              <h3 className="border-y border-border bg-surface-sunken px-4 py-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Source not located ({unlocated.length})
              </h3>
              <ul className="bg-surface">
                {unlocated.map((flag) => (
                  <NavigatorEntry
                    key={flag.key}
                    flag={flag}
                    onNavigate={onNavigate}
                    isReviewed={reviewed.has(flag.key)}
                  />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </nav>
  )
}
