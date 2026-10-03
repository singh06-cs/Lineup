// Low-level HTTP client: attaches the JWT, refreshes it when it expires, and turns
// DRF error responses into readable messages. Every API call goes through request().

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const ACCESS_KEY = 'lineup.access'
const REFRESH_KEY = 'lineup.refresh'

// Fired when the refresh token is rejected, so the app can send the user to /login.
export const SESSION_EXPIRED = 'lineup:session-expired'

// Trade-off: localStorage is readable by any JavaScript on the page, so an XSS bug
// could steal tokens. The stronger alternative is an httpOnly cookie set by Django,
// which JavaScript can't read at all, at the cost of needing CSRF protection.
export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  save({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export class ApiError extends Error {
  constructor(status, data) {
    super(messageFrom(data) || `Request failed (${status})`)
    this.status = status
    this.data = data
  }
}

// DRF errors come in a few shapes: {detail: "..."}, {field: ["..."]}, or ["..."].
function messageFrom(data) {
  if (!data) return ''
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.map(messageFrom).join(' ')
  if (data.detail) return messageFrom(data.detail)
  return Object.entries(data)
    .map(([field, value]) => {
      const text = messageFrom(value)
      return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`
    })
    .join(' ')
}

// If several requests hit a 401 at once, they all wait on the SAME refresh call.
// Otherwise the second refresh would use a token the first one just rotated away.
let refreshInFlight = null

function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const response = await fetch(`${API_URL}/api/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: tokens.refresh }),
      })
      if (!response.ok) {
        tokens.clear()
        window.dispatchEvent(new Event(SESSION_EXPIRED))
        throw new ApiError(401, { detail: 'Your session expired. Please log in again.' })
      }
      tokens.save(await response.json())
    })().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

export async function request(path, { method = 'GET', body, auth = true, retry = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`

  // Paginated responses give an absolute "next" URL, so accept either form.
  const url = path.startsWith('http') ? path : `${API_URL}${path}`
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  // Access token expired (they only live 15 minutes): refresh once, then retry.
  if (response.status === 401 && auth && retry && tokens.refresh) {
    await refreshAccessToken()
    return request(path, { method, body, auth, retry: false })
  }

  const hasBody = response.status !== 204 && response.status !== 205
  const data = hasBody ? await response.json().catch(() => null) : null
  if (!response.ok) throw new ApiError(response.status, data)
  return data
}
