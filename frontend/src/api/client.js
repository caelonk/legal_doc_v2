import axios from 'axios'

/**
 * The only place this app talks to the API.
 *
 * Its real job is error translation. The backend already writes every failure as
 * a plain-language `detail` string aimed at a reader — that is the whole point of
 * ParserError.user_message and the HTTPException details in routers/documents.py.
 * This module makes sure that string, and never an axios object, a status code, or
 * a stack, is what a component receives. It is the client half of the
 * no-raw-tracebacks rule in CLAUDE.md.
 */

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  // Generous: the POST parses and chunks the PDF before it answers, which is
  // seconds on a long document. The ANALYSIS is a background job and is not
  // waited on here, so this does not need to cover it.
  timeout: 120000,
})

export class ApiError extends Error {
  constructor(message, { status = null, kind = 'error' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind
  }
}

function toApiError(error) {
  if (!error.response) {
    // No response at all: backend down, wrong port, DNS, or CORS refusal.
    // Deliberately actionable — this is overwhelmingly a local-setup problem.
    return new ApiError(
      'Could not reach the analysis service. Check that the backend is running, then try again.',
      { kind: 'network' },
    )
  }

  const { status, data } = error.response
  const detail = typeof data?.detail === 'string' ? data.detail : null

  if (detail) return new ApiError(detail, { status })

  // A response the API did not author — a proxy error page, an HTML 502. Never
  // render it: it is not written for a user and may leak infrastructure detail.
  return new ApiError('Something went wrong on our end. Please try again.', { status })
}

export async function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  try {
    const { data } = await api.post('/api/documents/analyze', form)
    return data
  } catch (error) {
    throw toApiError(error)
  }
}

export async function getAnalysis(jobId, { signal } = {}) {
  try {
    const { data } = await api.get(`/api/documents/analyze/${jobId}`, { signal })
    return data
  } catch (error) {
    if (axios.isCancel(error)) throw error
    throw toApiError(error)
  }
}

export async function getHealth() {
  try {
    const { data } = await api.get('/api/health')
    return data
  } catch (error) {
    throw toApiError(error)
  }
}

/**
 * Saved analyses, newest first. Summary fields only — the backend deliberately
 * does not put the document text in this payload.
 *
 * A failure here is never rendered as an empty history: the API answers 503 when
 * storage is unreachable rather than returning [], and that distinction only
 * survives if this rethrows instead of defaulting.
 */
export async function getHistory({ signal } = {}) {
  try {
    const { data } = await api.get('/api/documents/history', { signal })
    return data
  } catch (error) {
    if (axios.isCancel(error)) throw error
    throw toApiError(error)
  }
}

/** One stored analysis, in the same shape a completed job's `result` has. */
export async function getStoredAnalysis(id, { signal } = {}) {
  try {
    const { data } = await api.get(`/api/documents/history/${id}`, { signal })
    return data
  } catch (error) {
    if (axios.isCancel(error)) throw error
    throw toApiError(error)
  }
}

export async function deleteStoredAnalysis(id) {
  try {
    await api.delete(`/api/documents/history/${id}`)
  } catch (error) {
    throw toApiError(error)
  }
}
