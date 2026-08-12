import { useCallback, useEffect, useState } from 'react'

/**
 * Which findings the reader has marked as reviewed.
 *
 * docs/ui-patterns.md §2 asks for this even in MVP, and the reason is the mental
 * model rather than the feature: "the tool proposes, the reader decides", not
 * "the tool decided". A list of AI conclusions with no way to register that a
 * human has looked at one invites the opposite reading.
 *
 * Local state, deliberately. It is not sent to the API and not persisted across a
 * reload: there are no user accounts, the analysis itself only survives an hour
 * in the job store, and writing review decisions to storage would outlive the
 * findings they refer to. Reviewing is a within-session activity here.
 *
 * Keyed by the flag keys built in lib/severity.js::collectRiskFlags, which are
 * unique per section and stable for a given result.
 */
export function useReviewState(jobId) {
  const [reviewed, setReviewed] = useState(() => new Set())

  // A different document must never inherit the previous one's review marks.
  useEffect(() => setReviewed(new Set()), [jobId])

  const toggle = useCallback((key) => {
    setReviewed((previous) => {
      const next = new Set(previous)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  return { reviewed, toggle }
}
