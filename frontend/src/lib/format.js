// Number / currency / time formatting helpers (Indian locale).

export const inr = (n, opts = {}) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
    ...opts,
  }).format(Number.isFinite(n) ? n : 0)

// ₹8.6L, ₹1.2Cr — compact Indian grouping
export const inrCompact = (n) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Number.isFinite(n) ? n : 0)

export const num = (n) =>
  new Intl.NumberFormat('en-IN').format(Number.isFinite(n) ? n : 0)

export const compact = (n) =>
  new Intl.NumberFormat('en-IN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Number.isFinite(n) ? n : 0)

export const pct = (n, d = 1) =>
  `${fixed(n, d)}%`

// value in 0..1 -> percentage string
export const pct01 = (n, d = 1) =>
  `${fixed((Number.isFinite(n) ? n : 0) * 100, d)}%`

export const fixed = (n, d = 0) =>
  (Number.isFinite(Number(n)) ? Number(n) : 0).toFixed(d)

export const fmtTime = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export const fmtDate = (iso) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
  })
}

// Simulation-timeline "now": the newest transaction timestamp we have rendered.
// Seeded/demo rows often sit far from wall-clock time; relative labels must
// follow this frontier so the live demo never reads "2 months ago".
let timelineNowMs = 0

export const noteTimeline = (...isos) => {
  for (const iso of isos) {
    if (!iso) continue
    const t = new Date(iso).getTime()
    if (Number.isFinite(t) && t > timelineNowMs) timelineNowMs = t
  }
  return timelineNowMs
}

export const timeAgo = (iso) => {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return '—'
  const now = timelineNowMs > 0 ? timelineNowMs : then
  const secs = Math.max(0, (now - then) / 1000)
  if (secs < 5) return 'just now'
  if (secs < 60) return `${Math.floor(secs)}s ago`
  const mins = secs / 60
  if (mins < 60) return `${Math.floor(mins)}m ago`
  const hrs = mins / 60
  if (hrs < 24) return `${Math.floor(hrs)}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export const titleCase = (s) =>
  (s || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
