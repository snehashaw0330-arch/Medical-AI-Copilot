import clsx from 'clsx'

/** Conditional className join. */
export function cn(...args) {
  return clsx(...args)
}

/** Map a 0..100 confidence to a semantic color token. */
export function confidenceColor(pct) {
  if (pct >= 70) return 'var(--success)'
  if (pct >= 40) return 'var(--warning)'
  return 'var(--danger)'
}

/** Title-case a snake_case / lowercase string for display. */
export function titleCase(str = '') {
  return str
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

/** True when the request was aborted by the user (AbortController). */
export function isCanceled(err) {
  return err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError'
}

/** Extract a friendly, human message from an axios error. */
export function errorMessage(err, fallback = 'Something went wrong') {
  // Prefer the backend's own message (FastAPI returns {detail: ...}).
  const backend = err?.response?.data?.detail || err?.response?.data?.error
  if (backend) return typeof backend === 'string' ? backend : JSON.stringify(backend)

  if (isCanceled(err)) return 'Request canceled.'
  if (err?.code === 'ECONNABORTED' || err?.code === 'ETIMEDOUT') {
    return 'The analysis is taking longer than expected. Please try again, or use a smaller / clearer image.'
  }
  if (err?.code === 'ERR_NETWORK') {
    return 'Cannot reach the server. Make sure the backend is running.'
  }
  return err?.message || fallback
}
