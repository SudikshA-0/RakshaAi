// Central design tokens: action semantics + chart palette.
// Kept in JS (not just Tailwind) so charts / inline SVG can read raw hex.
// Colour communicates RISK & STATUS only — never decoration.

export const ACTIONS = {
  ALLOW: {
    label: 'Allow',
    color: '#00B7CD', // Electric Cyan — trusted
    soft: '#DFF5F8',
    text: '#0A7080',
    desc: 'Approved — cleared for settlement',
  },
  STEP_UP: {
    label: 'Step-up',
    color: '#FF9100', // Action Orange — verification
    soft: '#FFEFD6',
    text: '#A85E00',
    desc: 'Challenged with OTP / 3-D Secure',
  },
  HOLD: {
    label: 'Hold',
    color: '#E5590C', // burnt orange — manual review
    soft: '#FBE6D8',
    text: '#9E3D06',
    desc: 'Routed to the manual review queue',
  },
  BLOCK: {
    label: 'Block',
    color: '#DF301C', // Signal Red — declined
    soft: '#FBE3DE',
    text: '#A81F0F',
    desc: 'Declined — high fraud risk',
  },
}

export const actionMeta = (action) =>
  ACTIONS[action] || {
    label: action || 'Unknown',
    color: '#8A8B85',
    soft: '#F0F0EC',
    text: '#4B5563',
    desc: '',
  }

// Risk score (0..1) -> colour band
export const riskColor = (score) => {
  if (score >= 0.82) return '#DF301C' // critical
  if (score >= 0.55) return '#E5590C' // high
  if (score >= 0.35) return '#FF9100' // elevated
  return '#00B7CD' // low / trusted
}

export const riskLabel = (score) => {
  if (score >= 0.82) return 'Critical'
  if (score >= 0.55) return 'High'
  if (score >= 0.35) return 'Elevated'
  return 'Low'
}

// 0..3 band index for segmented risk meters
export const riskBand = (score) => {
  if (score >= 0.82) return 3
  if (score >= 0.55) return 2
  if (score >= 0.35) return 1
  return 0
}

// Restrained categorical palette for ranked/business charts.
// Anchored on ink + cyan with warm accents — no rainbow.
export const CHART = [
  '#151515',
  '#00B7CD',
  '#FF9100',
  '#DF301C',
  '#4B5563',
  '#0A7080',
  '#E5590C',
  '#8A8B85',
]

// chart chrome (light)
export const AXIS = '#9A9B94'
export const GRID = '#ECECE7'
export const INK = '#151515'
export const TRUST = '#00B7CD'
export const SIGNAL = '#DF301C'
export const WARN = '#FF9100'

// Human labels for the planted fraud patterns
export const PATTERN_LABELS = {
  card_testing: 'Card testing',
  stolen_card: 'Stolen card',
  account_takeover: 'Account takeover',
  ring: 'Fraud ring / bust-out',
  friendly_fraud: 'Friendly fraud',
  legit: 'Legitimate',
  none: 'Legitimate',
}

export const patternLabel = (p) =>
  PATTERN_LABELS[p] ||
  (p || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
