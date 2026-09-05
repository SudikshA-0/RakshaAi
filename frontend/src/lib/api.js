// Thin API client for the RakshaAI backend. All calls use VITE_API_URL
// or default to the Vite proxy at /api -> http://127.0.0.1:8000.
//
// Dashboard users authenticate with a Bearer JWT. The token is kept in
// localStorage and attached to every request; a 401 clears it and notifies the
// app so it can drop back to the login screen.
const BASE = (import.meta.env?.VITE_API_URL || '/api').replace(/\/$/, '')
const TOKEN_KEY = 'rakshaai.token'

let _unauthorized = null // callback registered by the auth provider

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || null
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore quota / private mode */
  }
}

export function onUnauthorized(fn) {
  _unauthorized = fn
}

async function req(path, opts = {}) {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(BASE + path, { ...opts, headers })
  if (res.status === 401) {
    // Token missing/expired/invalid — force re-authentication.
    setToken(null)
    if (_unauthorized) _unauthorized()
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`401: ${text}`)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // --- auth ---------------------------------------------------------------
  signup: (body) => req('/auth/signup', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) => req('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => req('/auth/me'),

  // --- developer ----------------------------------------------------------
  apiKeys: () => req('/developer/keys'),
  createApiKey: (body) =>
    req('/developer/keys', { method: 'POST', body: JSON.stringify(body) }),
  revokeApiKey: (id) => req(`/developer/keys/${id}/revoke`, { method: 'POST' }),
  webhooks: () => req('/developer/webhooks'),
  createWebhook: (body) =>
    req('/developer/webhooks', { method: 'POST', body: JSON.stringify(body) }),
  updateWebhook: (id, body) =>
    req(`/developer/webhooks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  disableWebhook: (id) => req(`/developer/webhooks/${id}/disable`, { method: 'POST' }),
  enableWebhook: (id) => req(`/developer/webhooks/${id}/enable`, { method: 'POST' }),
  rotateWebhookSecret: (id) =>
    req(`/developer/webhooks/${id}/rotate-secret`, { method: 'POST' }),
  webhookDeliveries: (id) => req(`/developer/webhooks/${id}/deliveries`),
  testWebhook: (id) => req(`/developer/webhooks/${id}/test`, { method: 'POST' }),

  // --- platform -----------------------------------------------------------
  health: () => req('/health'),
  overview: () => req('/analytics/overview'),
  timeseries: (days = 14) => req(`/analytics/timeseries?days=${days}`),
  drivers: () => req('/analytics/risk-drivers'),
  threats: () => req('/analytics/threat-patterns'),
  model: () => req('/analytics/model'),
  transactions: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== '' && v != null),
    ).toString()
    return req('/transactions' + (qs ? `?${qs}` : ''))
  },
  transaction: (id) => req(`/transactions/${id}`),
  cases: (resolved = false) => req(`/cases?resolved=${resolved}`),
  resolveCase: (id, body) =>
    req(`/cases/${id}/resolve`, { method: 'POST', body: JSON.stringify(body) }),
  feedbackSummary: () => req('/cases/feedback/summary'),
  policy: () => req('/policy'),
  updatePolicy: (body) =>
    req('/policy', { method: 'PUT', body: JSON.stringify(body) }),
  simulateOne: () => req('/simulate/transaction', { method: 'POST' }),
  simulateBatch: (n = 6) => req(`/simulate/batch?n=${n}`, { method: 'POST' }),
  attack: (body) =>
    req('/simulate/attack', { method: 'POST', body: JSON.stringify(body) }),
  aiAnalystQuery: (body) =>
    req('/ai-analyst/query', { method: 'POST', body: JSON.stringify(body) }),
  aiAnalystConversations: () => req('/ai-analyst/conversations'),
  createAIConversation: (body) =>
    req('/ai-analyst/conversations', { method: 'POST', body: JSON.stringify(body || {}) }),
  getAIConversation: (id) => req(`/ai-analyst/conversations/${id}`),
  renameAIConversation: (id, title) =>
    req(`/ai-analyst/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteAIConversation: (id) =>
    req(`/ai-analyst/conversations/${id}`, { method: 'DELETE' }),
  clearAIConversation: (id) =>
    req(`/ai-analyst/conversations/${id}/clear`, { method: 'POST' }),
}

