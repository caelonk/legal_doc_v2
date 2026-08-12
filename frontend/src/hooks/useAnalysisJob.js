import { useEffect, useRef, useState } from 'react'
import { getAnalysis } from '../api/client'

const POLL_MS = 900

// One blip should not kill a running analysis view. A dev server restart or a
// dropped keepalive is momentary, and the job itself is unaffected — it lives in
// the backend process, not in this request.
const TOLERATED_CONSECUTIVE_FAILURES = 2

const isTerminal = (status) => status === 'COMPLETE' || status === 'FAILED'

/**
 * Poll one analysis job until it settles.
 *
 * `seed` is the 202 body from the upload. Using it means filename, page count and
 * chunk count are on screen immediately rather than one round trip later — which
 * is the entire reason the route parses inside the POST instead of in the
 * background.
 *
 * A timeout chain rather than setInterval, so a slow response can never stack up
 * behind the next tick.
 */
export function useAnalysisJob(jobId, seed = null) {
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const seedRef = useRef(seed)
  seedRef.current = seed

  useEffect(() => {
    if (!jobId) return undefined

    // Never show one job's progress under another's id.
    setJob(seedRef.current?.job_id === jobId ? seedRef.current : null)
    setError(null)

    let cancelled = false
    let timer = null
    let consecutiveFailures = 0
    const controller = new AbortController()

    async function tick() {
      try {
        const next = await getAnalysis(jobId, { signal: controller.signal })
        if (cancelled) return
        consecutiveFailures = 0
        setJob(next)
        setError(null)
        if (isTerminal(next.status)) return
      } catch (err) {
        if (cancelled || err.name === 'CanceledError' || err.name === 'AbortError') return
        consecutiveFailures += 1
        // 404 is definitive: the job is gone or expired, not slow. Retrying it
        // just delays telling the user something they need to act on.
        if (err.status === 404 || consecutiveFailures > TOLERATED_CONSECUTIVE_FAILURES) {
          setError(err)
          return
        }
      }
      timer = setTimeout(tick, POLL_MS)
    }

    tick()

    return () => {
      cancelled = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [jobId])

  return {
    job,
    error,
    isPolling: Boolean(job) && !isTerminal(job.status) && !error,
  }
}
