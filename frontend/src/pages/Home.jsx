import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import UploadZone from '../components/UploadZone'
import { getHealth, uploadDocument } from '../api/client'

export default function Home() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [health, setHealth] = useState(null)
  const navigate = useNavigate()

  // Surfaced before the user picks a file, not after they upload one. A server
  // with no API key parses and chunks fine and then refuses at the last step,
  // which is a wasted round trip and a confusing failure.
  useEffect(() => {
    let active = true
    getHealth()
      .then((data) => active && setHealth(data))
      .catch(() => active && setHealth(null))
    return () => {
      active = false
    }
  }, [])

  async function handleSubmit(file) {
    setBusy(true)
    setError(null)
    try {
      const job = await uploadDocument(file)
      // The 202 body goes along so Analysis can show filename and page count
      // immediately instead of waiting a poll interval for its first response.
      navigate(`/analysis/${job.job_id}`, { state: { seed: job } })
    } catch (err) {
      // UploadZone keeps the chosen file, so the user retries with one click.
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-serif text-2xl text-ink">Read a contract before you sign it</h1>
      <p className="mt-3 max-w-measure text-base text-ink-muted">
        Upload a lease, NDA, or services agreement. This tool extracts the text, reads it section
        by section, and reports clauses that carry risk, provisions that appear to be missing, and
        a plain-English summary — each finding linked back to the page it came from.
      </p>

      {health && !health.analysis_available && (
        <p
          role="alert"
          className="mt-6 rounded-md border border-risk-medium-border bg-risk-medium-bg px-4 py-3 text-sm text-risk-medium"
        >
          Analysis is not configured on the server, so uploads will be refused. {health.detail}
        </p>
      )}

      <div className="mt-8">
        <UploadZone
          onSubmit={handleSubmit}
          busy={busy}
          error={error}
          // Undefined until health resolves. UploadZone treats that as "stored",
          // which is the safe direction for a claim about confidential text.
          storage={
            health && {
              available: health.history_available,
              retentionDays: health.history_retention_days,
            }
          }
        />
      </div>

      <p className="mt-10 max-w-measure text-xs text-ink-subtle">
        This tool identifies and describes. It does not recommend, approve, or advise, and it is
        not a substitute for a lawyer.
      </p>
    </div>
  )
}
