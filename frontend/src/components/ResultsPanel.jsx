import { FileWarning, ShieldAlert } from 'lucide-react'
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

function RiskFlagTable({ flags, onNavigate }) {
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

  return (
    <section>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-serif text-xl text-ink">Risk flags</h2>
        {/* Counts, never an aggregate "document risk score" — a composite number
            invites reliance on a figure nothing in the pipeline validates. */}
        <p className="font-mono text-xs text-ink-muted">
          {counts.HIGH} high · {counts.MEDIUM} medium · {counts.LOW} low
        </p>
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
            </tr>
          </thead>
          <tbody>
            {sortBySeverity(flags).map((flag) => (
              <tr key={flag.key} className="border-b border-border last:border-b-0 align-top">
                <td className="px-4 py-3">
                  <RiskBadge severity={flag.severity} />
                </td>
                <td className="px-4 py-3 font-medium text-ink">{flag.clause_type}</td>
                {/* The explanation sits in the same visual unit as the conclusion.
                    A bare severity + clause name is a conclusion with nothing to
                    check it against. */}
                <td className="max-w-measure px-4 py-3 text-ink-muted">{flag.explanation}</td>
                <td className="whitespace-nowrap px-4 py-3">
                  <PageReference page={flag.page_reference} onNavigate={onNavigate} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/**
 * Kept in its own section with its own framing, never interleaved with risk
 * flags. A risk flag is grounded in text that exists; a missing clause is an
 * inference about absence, which is a fundamentally weaker claim. Presenting them
 * in one list would imply they carry the same weight.
 */
function MissingClauseList({ clauses }) {
  return (
    <section>
      <h2 className="font-serif text-xl text-ink">Possibly missing provisions</h2>
      <p className="mt-1 max-w-measure text-sm text-ink-muted">
        These are inferences about what is <em>absent</em>, which is a weaker claim than a
        flagged clause. Each section is judged on its own, so a provision listed here may appear
        elsewhere in the document.
      </p>

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

export default function ResultsPanel({ result, onNavigate }) {
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
        <RiskFlagTable flags={flags} onNavigate={onNavigate} />
        <MissingClauseList clauses={missing} />
        <Summaries sections={result.sections} onNavigate={onNavigate} />
      </div>
    </div>
  )
}
