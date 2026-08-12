import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import AnalysisProgress from '../components/AnalysisProgress'
import ClauseNavigator from '../components/ClauseNavigator'
import DocumentHeader from '../components/DocumentHeader'
import ResultsPanel from '../components/ResultsPanel'
import SourcePane from '../components/SourcePane'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/Tabs'
import { useAnalysisJob } from '../hooks/useAnalysisJob'
import { useMediaQuery } from '../hooks/useMediaQuery'

// Matches Tailwind's `lg`. Below this the two-pane split stops being useful —
// design-system.md §3 says explicitly not to keep two panes on a phone.
const WIDE = '(min-width: 1024px)'

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
  const isWide = useMediaQuery(WIDE)
  const [tab, setTab] = useState('findings')
  const pendingPage = useRef(null)

  const { job, error } = useAnalysisJob(jobId, location.state?.seed ?? null)

  // On a narrow viewport the source lives behind a tab, so Radix has it
  // unmounted and sourceRef is null. Following a citation therefore has to switch
  // tabs FIRST and scroll once the pane exists. Without this the single most
  // important interaction silently does nothing on a phone — the same failure the
  // desktop scroll was hardened against.
  const navigateToPage = (page) => {
    if (isWide) {
      sourceRef.current?.scrollToPage(page)
      return
    }
    pendingPage.current = page
    setTab('document')
  }

  useEffect(() => {
    if (tab !== 'document' || pendingPage.current == null) return
    const page = pendingPage.current
    pendingPage.current = null
    // After paint: a pane that was display:none has no geometry to scroll to,
    // and SourcePane positions by measured offset.
    const frame = requestAnimationFrame(() => sourceRef.current?.scrollToPage(page))
    return () => cancelAnimationFrame(frame)
  }, [tab])

  // 'document' only exists as a tab on narrow viewports. If the window is
  // widened while it is selected, the wide layout has no panel with that value
  // and the pane would render empty.
  const activeTab = isWide && tab === 'document' ? 'findings' : tab

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

    const findings = <ResultsPanel result={job.result} onNavigate={navigateToPage} />
    const navigator = <ClauseNavigator result={job.result} onNavigate={navigateToPage} />
    const source = <SourcePane ref={sourceRef} pages={job.result.pages} />

    return (
      <div className="flex h-[calc(100vh-3.5rem)] flex-col">
        {/* Outside the tabs: it names the page, and the page keeps its h1
            whichever view is open. */}
        <DocumentHeader
          document={job.document}
          documentTypeHint={job.result.document_type_hint}
        />

        {isWide ? (
          // Split pane: source left (~60%), findings right (~40%). The dominant
          // layout in legal review tools, because it lets a reader check a claim
          // against the source without losing their place (design-system.md §3).
          // The navigator is a tab beside the findings rather than a third column
          // — at 1280px a third pane squeezes the document below a comfortable
          // measure, and the two are alternate readings of the same findings.
          <div className="flex min-h-0 flex-1">
            <div className="min-h-0 w-3/5 border-r border-border">{source}</div>
            <div className="min-h-0 w-2/5">
              <Tabs
                value={activeTab}
                onValueChange={setTab}
                className="flex h-full min-h-0 flex-col"
              >
                <TabsList label="Analysis views">
                  <TabsTrigger value="findings">Findings</TabsTrigger>
                  <TabsTrigger value="navigator">Clause navigator</TabsTrigger>
                </TabsList>
                <TabsContent value="findings">{findings}</TabsContent>
                <TabsContent value="navigator">{navigator}</TabsContent>
              </Tabs>
            </div>
          </div>
        ) : (
          // Narrow: one pane at a time. Document last, because the reader arrives
          // for the findings and reaches the source by following a citation.
          <Tabs
            value={activeTab}
            onValueChange={setTab}
            className="flex min-h-0 flex-1 flex-col"
          >
            <TabsList label="Analysis views">
              <TabsTrigger value="findings">Findings</TabsTrigger>
              <TabsTrigger value="navigator">Navigator</TabsTrigger>
              <TabsTrigger value="document">Document</TabsTrigger>
            </TabsList>
            <TabsContent value="findings">{findings}</TabsContent>
            <TabsContent value="navigator">{navigator}</TabsContent>
            <TabsContent value="document">{source}</TabsContent>
          </Tabs>
        )}
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
