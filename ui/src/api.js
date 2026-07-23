// Thin fetch wrappers over the FastAPI backend. Requests are same-origin —
// vite.config.js proxies /alert, /cards, /health to 127.0.0.1:8000, so no
// CORS setup was needed on the backend.

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function parseErrorBody(res) {
  try {
    const body = await res.json()
    return body.detail ?? JSON.stringify(body)
  } catch {
    return res.statusText
  }
}

export async function analyzeAlert(alertPayload, generation) {
  const qs = generation === null ? '' : `?generation=${generation}`
  let res
  try {
    res = await fetch(`/alert${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(alertPayload),
    })
  } catch {
    throw new ApiError('Cannot reach the backend — is it running?', 0, null)
  }
  if (!res.ok) {
    const detail = await parseErrorBody(res)
    throw new ApiError(`Analysis failed (${res.status})`, res.status, detail)
  }
  return res.json()
}

export async function submitFeedback(correlationId, payload) {
  let res
  try {
    res = await fetch(`/cards/${correlationId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new ApiError('Cannot reach the backend — is it running?', 0, null)
  }
  if (!res.ok) {
    const detail = await parseErrorBody(res)
    throw new ApiError(`Submission failed (${res.status})`, res.status, detail)
  }
  return res.json()
}

export async function getHealth() {
  const res = await fetch('/health')
  if (!res.ok) throw new ApiError(`Health check failed (${res.status})`, res.status, null)
  return res.json()
}

export { ApiError }
