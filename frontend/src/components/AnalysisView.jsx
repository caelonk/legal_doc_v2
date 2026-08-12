import { useEffect, useRef, useState } from 'react'
import ClauseNavigator from './ClauseNavigator'
import DocumentHeader from './DocumentHeader'
import ResultsPanel from './ResultsPanel'
import SourcePane from './SourcePane'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './Tabs'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useReviewState } from '../hooks/useReviewState'

// Matches Tailwind's `lg`. Below this the two-pane split stops being useful —
// design-system.md §3 says explicitly not to keep two panes on a phone.
const WIDE = '(min-width: 1024px)'

/**
 * A finished analysis, however it was obtained.
 *
 * Extracted from the Analysis page when document history arrived, because a
 * stored analysis and a just-finished one are the same thing: the API returns the
 * identical `AnalysisResult` shape from both endpoints. Rendering them through two
 * components would mean two places for the provenance affordance, the disclosure,
 * and the citation-follow behaviour to drift apart — and the stored copy is
 * exactly the one a reader comes back to when they want to check a claim.
 *
 * `reviewKey` scopes the in-memory "reviewed" marks. It changes when the reader
 * moves to a different document, so marks never carry over.
 *
 * `toolbar` renders directly under the header, inside the same fixed-height
 * column, for actions that belong to how the analysis was obtained rather than to
 * the analysis itself.
 */
export default function AnalysisView({ result, reviewKey, toolbar = null }) {
  const sourceRef = useRef(null)
  const isWide = useMediaQuery(WIDE)
  const [tab, setTab] = useState('findings')
  const pendingPage = useRef(null)
  const { reviewed, toggle: toggleReviewed } = useReviewState(reviewKey)

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

  // Review state is owned here and shared by both views: the findings table and
  // the navigator are readings of the same findings, so a mark made in one that
  // did not show in the other would read as a bug.
  const findings = (
    <ResultsPanel
      result={result}
      onNavigate={navigateToPage}
      reviewed={reviewed}
      onToggleReviewed={toggleReviewed}
    />
  )
  const navigator = (
    <ClauseNavigator result={result} onNavigate={navigateToPage} reviewed={reviewed} />
  )
  const source = <SourcePane ref={sourceRef} pages={result.pages} />

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Outside the tabs: it names the page, and the page keeps its h1
          whichever view is open. */}
      <DocumentHeader
        document={result.document}
        documentType={result.aggregate.document_type}
        typeAgreement={{
          agreeing: result.aggregate.document_type_agreement,
          total: result.aggregate.sections_analyzed,
        }}
      />
      {toolbar}

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
            <Tabs value={activeTab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
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
        <Tabs value={activeTab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
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
