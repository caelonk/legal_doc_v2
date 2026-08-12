import { useState } from 'react'
import { Check, FileWarning, ShieldAlert } from 'lucide-react'
import PageReference from './PageReference'
import RiskBadge from './RiskBadge'
import {
  collectMissingClauses,
  collectRiskFlags,
  countBySeverity,
  sortBySeverity,
} from '../lib/severity'

/**
 * Persistent framing. Not dismissible at all in this pass, which satisfies "may be
 * collapsible but never permanently dismissible" (docs/ui-patterns.md §5) without
 * needing state that could be persisted by accident.
 */
function Disclosure() {
  return (
    <p className="flex items-start gap-2 rounded-md border border-risk-info-border bg-risk-info-bg px-4 py-3 text-sm text-risk-info">
      <ShieldAlert size={16} strokeWidth={1.5} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span>
        AI-generated analysis. Verify against the source document. This is not legal advice.
      </span>
    </p>
  )
}

/**
 * Sections that could not be analyzed. Disclosed, never swallowed — silent partial
 * results are a correctness failure, not a cosmetic one
 * (.claude/rules/ai-output.md).
 */
function SkippedSections({ skipped }) {
  if (skipped.length === 0) return null
  return (
    <section className="rounded-md border border-risk-medium-border bg-risk-medium-bg p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-risk-medium">
        <FileWarning size={16} strokeWidth={1.5} aria-hidden="true" />
        {skipped.length} {skipped.length === 1 ? 'section' : 'sections'} could not be analyzed
      </h2>
      <ul className="mt-2 space-y-1 text-sm text-risk-medium">
        {skipped.map((section) => (
          <li key={section.chunk_index}>
            {section.pages.length > 0 &&
              `${section.pages.length === 1 ? 'Page' : 'Pages'} ${section.pages.join(', ')}: `}
            {section.message}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-risk-medium">
        Anything in those pages is missing from the findings below.
      </p>
    </section>
  )
}

function RiskFlagTable({ flags, onNavigate, reviewed, onToggleReviewed, mergedCount = 0 }) {
  const [hideReviewed, setHideReviewed] = useState(false)
  const counts = countBySeverity(flags)

  if (flags.length === 0) {
    // A clean result is the most dangerous moment for over-reliance, so it is
    // stated explicitly and followed immediately by the verification reminder
    // (docs/ui-patterns.md §4).
    return (
      <section>
        <h2 className="font-serif text-xl text-ink">Risk flags</h2>
        <div className="mt-3 rounded-md border border-border bg-surface p-6">
          <p className="text-sm font-medium text-ink">
            No risk-flagged clauses were identified in this document.
          </p>
          <p className="mt-2 text-sm text-ink-muted">
            That is not a clean bill of health. It means this tool did not flag anything — read
            the document and confirm for yourself.
          </p>
        </div>
      </section>
    )
  }

  const reviewedCount = flags.filter((flag) => reviewed.has(flag.key)).length
  const visible = hideReviewed ? flags.filter((flag) => !reviewed.has(flag.key)) : flags
  const hiddenCount = flags.length - visible.length

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-serif text-xl text-ink">Risk flags</h2>
        {/* Counts, never an aggregate "document risk score" — a composite number
            invites reliance on a figure nothing in the pipeline validates. */}
        <p className="font-mono text-xs text-ink-muted">
          {counts.HIGH} high · {counts.MEDIUM} medium · {counts.LOW} low
        </p>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p className="text-xs text-ink-subtle">
          {reviewedCount} of {flags.length} reviewed
        </p>
        {reviewedCount > 0 && (
          <button
            type="button"
            onClick={() => setHideReviewed((value) => !value)}
            className="rounded-sm px-1 py-0.5 text-xs text-accent underline decoration-transparent underline-offset-2 transition hover:decoration-current"
          >
            {hideReviewed ? 'Show reviewed' : 'Hide reviewed'}
          </button>
        )}
      </div>

      <div className="mt-3 overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border-strong text-left">
              <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                Severity
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                Clause
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                What it means
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                Source
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                Reviewed
              </th>
            </tr>
          </thead>
          <tbody>
            {sortBySeverity(visible).map((flag) => {
              const isReviewed = reviewed.has(flag.key)
              return (
                <tr
                  key={flag.key}
                  className={`border-b border-border last:border-b-0 align-top ${
                    isReviewed ? 'bg-surface-sunken' : ''
                  }`}
                >
                  <td className="px-4 py-3">
                    <RiskBadge severity={flag.severity} />
                  </td>
                  <td className="px-4 py-3 font-medium text-ink">{flag.clause_type}</td>
                  {/* The explanation sits in the same visual unit as the conclusion,
                      reviewed or not. A bare severity + clause name is a conclusion
                      with nothing to check it against, so marking a finding read
                      must not collapse the one field that supports it. */}
                  <td className="max-w-measure px-4 py-3 text-ink-muted">
                    {flag.explanation}
                    {flag.severity_disagreement && (
                      /* Surfaced, not smoothed over. The merged severity is the
                         highest any section gave, so the reader should know the
                         model was not consistent about this clause. */
                      <span className="mt-1 block text-xs text-ink-subtle">
                        Sections disagreed on severity; the higher one is shown.
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <PageReference page={flag.page_reference} onNavigate={onNavigate} />
                  </td>
                  <td className="px-4 py-3">
                    <ReviewToggle
                      flag={flag}
                      isReviewed={isReviewed}
                      onToggle={() => onToggleReviewed?.(flag.key)}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {hiddenCount > 0 && (
        /* Findings are never silently absent. If the reader has filtered some
           away, the count says so and the control to bring them back is above. */
        <p className="mt-2 text-xs text-ink-subtle">
          {hiddenCount} reviewed {hiddenCount === 1 ? 'finding' : 'findings'} hidden.
        </p>
      )}

      {mergedCount > 0 && (
        /* Explains why the finding count is smaller than the sum of the section
           counts. Without this a reader comparing the two would be left guessing
           whether something was lost. */
        <p className="mt-2 text-xs text-ink-subtle">
          {mergedCount} duplicate {mergedCount === 1 ? 'report' : 'reports'} merged, where
          overlapping sections raised the same clause.
        </p>
      )}
    </section>
  )
}

/**
 * "The tool proposes, the reader decides" (docs/ui-patterns.md §2).
 *
 * A toggle button with aria-pressed rather than a checkbox: this is a two-state
 * control acting on the row, not a form field being submitted anywhere. Marking a
 * finding reviewed changes nothing about the finding — it is not dismissed, its
 * explanation stays visible, and its severity badge is untouched.
 */
function ReviewToggle({ flag, isReviewed, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={isReviewed}
      aria-label={`Mark ${flag.clause_type} as reviewed`}
      className={`inline-flex min-h-6 items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs transition ${
        isReviewed
          ? 'border-border-strong bg-surface text-ink-muted'
          : 'border-border text-ink-subtle hover:text-ink'
      }`}
    >
      <Check
        size={16}
        strokeWidth={1.5}
        aria-hidden="true"
        className={isReviewed ? 'text-accent' : 'text-ink-subtle'}
      />
      {isReviewed ? 'Reviewed' : 'Mark'}
    </button>
  )
}

/**
 * Kept in its own section with its own framing, never interleaved with risk
 * flags. A risk flag is grounded in text that exists; a missing clause is an
 * inference about absence, which is a fundamentally weaker claim. Presenting them
 * in one list would imply they carry the same weight.
 */
function MissingClauseList({ clauses, contradicted = [] }) {
  return (
    <section>
      <h2 className="font-serif text-xl text-ink">Possibly missing provisions</h2>
      <p className="mt-1 max-w-measure text-sm text-ink-muted">
        These are inferences about what is <em>absent</em>, which is a weaker claim than a
        flagged clause. Each section is judged on its own, so a provision listed here may appear
        elsewhere in the document.
      </p>

      {contradicted.length > 0 && (
        /* Withheld, and said so. A section claimed these were absent while another
           section raised a risk flag about that same clause type — so the text
           exists somewhere in the document and the absence claim was wrong. A risk
           flag is grounded in text that exists; absence is only an inference, so
           the stronger claim wins. Naming them beats quietly showing a shorter
           list. */
        <p className="mt-3 rounded-md border border-border bg-surface px-4 py-3 text-xs text-ink-muted">
          {contradicted.length} {contradicted.length === 1 ? 'provision was' : 'provisions were'}{' '}
          reported missing by one section but flagged as present elsewhere in the document, so
          {contradicted.length === 1 ? ' it is' : ' they are'} not listed here:{' '}
          <span className="text-ink">{contradicted.join(', ')}</span>.
        </p>
      )}

      {clauses.length === 0 ? (
        <div className="mt-3 rounded-md border border-border bg-surface p-6">
          <p className="text-sm text-ink-muted">No standard provisions were reported as absent.</p>
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-md border border-border bg-surface">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-strong text-left">
                <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                  Importance
                </th>
                <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                  Provision
                </th>
                <th scope="col" className="px-4 py-3 font-medium text-ink-muted">
                  Why it matters
                </th>
              </tr>
            </thead>
            <tbody>
              {clauses.map((clause) => (
                <tr key={clause.key} className="border-b border-border last:border-b-0 align-top">
                  <td className="px-4 py-3">
                    <RiskBadge severity={clause.importance} />
                  </td>
                  <td className="px-4 py-3 font-medium text-ink">{clause.clause_name}</td>
                  <td className="max-w-measure px-4 py-3 text-ink-muted">{clause.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Summaries({ sections, onNavigate }) {
  return (
    <section>
      <h2 className="font-serif text-xl text-ink">Section summaries</h2>
      <div className="mt-3 space-y-4">
        {sections.map((section) => (
          <article key={section.chunk_index} className="rounded-md border border-border bg-surface p-4">
            <p className="mb-2 flex flex-wrap items-center gap-2 font-mono text-xs text-ink-subtle">
              <span>Section {section.chunk_index + 1}</span>
              {section.pages.map((page) => (
                <PageReference key={page} page={page} onNavigate={onNavigate} />
              ))}
            </p>
            <p className="max-w-measure text-base text-ink">{section.analysis.summary}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

export default function ResultsPanel({
  result,
  onNavigate,
  reviewed = new Set(),
  onToggleReviewed,
}) {
  const flags = collectRiskFlags(result)
  const missing = collectMissingClauses(result)

  return (
    <div className="h-full overflow-y-auto bg-surface-sunken p-4 lg:p-6">
      <div className="space-y-6">
        {/* Document identity lives in DocumentHeader, outside the tabs — see the
            note there. This panel is one view among several and must not own the
            page's h1. */}
        <Disclosure />
        <SkippedSections skipped={result.skipped} />
        <RiskFlagTable
          flags={flags}
          onNavigate={onNavigate}
          reviewed={reviewed}
          onToggleReviewed={onToggleReviewed}
          mergedCount={result.aggregate?.merged_duplicate_count ?? 0}
        />
        <MissingClauseList
          clauses={missing}
          contradicted={result.aggregate?.contradicted_missing_clauses ?? []}
        />
        <Summaries sections={result.sections} onNavigate={onNavigate} />
      </div>
    </div>
  )
}
