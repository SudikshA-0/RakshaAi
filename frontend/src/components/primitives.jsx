import { useEffect, useRef, useState } from 'react'
import { actionMeta, riskColor, riskLabel, riskBand } from '../lib/theme'

/* ---------- count-up hook ---------- */
export function useCountUp(target, duration = 600) {
  const [val, setVal] = useState(target || 0)
  const fromRef = useRef(target || 0)
  useEffect(() => {
    const from = fromRef.current
    const to = Number.isFinite(target) ? target : 0
    if (from === to) return
    let raf
    const start = performance.now()
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      const cur = from + (to - from) * eased
      fromRef.current = cur
      setVal(cur)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return val
}

/* ---------- surfaces ---------- */
export function Card({ className = '', children, ...rest }) {
  return (
    <div className={`card ${className}`} {...rest}>
      {children}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions, children }) {
  return (
    <div className="sticky top-0 z-20 -mx-6 border-b border-line bg-canvas px-6 lg:-mx-8 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3 py-5">
        <div className="min-w-0">
          <h1 className="truncate text-[20px] font-semibold leading-tight tracking-tight text-ink">{title}</h1>
          {subtitle && <p className="mt-1 text-[13px] leading-snug text-muted">{subtitle}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

export function SectionHeader({ title, subtitle, right, icon: Icon, className = '' }) {
  return (
    <div className={`flex items-start justify-between gap-4 ${className}`}>
      <div className="flex items-center gap-2">
        {Icon && <Icon size={15} className="shrink-0 text-faint" strokeWidth={2} />}
        <div>
          <h3 className="text-[13.5px] font-semibold leading-tight text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-faint">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  )
}

/* ---------- badges ---------- */
export function RiskBadge({ action, size = 'md' }) {
  const m = actionMeta(action)
  const pad = size === 'sm' ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-[3px] text-xs'
  return (
    <span className={`pill ${pad}`} style={{ backgroundColor: m.soft, color: m.text }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: m.color }} />
      {m.label}
    </span>
  )
}

export function StatusDot({ ok, className = '' }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${className}`}
      style={{ backgroundColor: ok ? '#00B7CD' : '#DF301C' }}
    />
  )
}

export function ScorePill({ score }) {
  const c = riskColor(score)
  return (
    <span className="pill tnum px-1.5 py-0.5 text-[11px]" style={{ backgroundColor: `${c}1a`, color: c }}>
      {(Number.isFinite(Number(score)) ? Number(score) * 100 : 0).toFixed(0)}
    </span>
  )
}

/* ---------- metric (for stat strips) ---------- */
export function Metric({ label, value, format, sub, subTone = 'text-muted', accent, spark, className = '' }) {
  const isNum = typeof value === 'number'
  const animated = useCountUp(isNum ? value : 0)
  const display = isNum ? (format ? format(animated) : Math.round(animated)) : value
  return (
    <div className={`px-5 py-4 ${className}`}>
      <div className="stat-label">{label}</div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div className="tnum text-[25px] font-semibold leading-none tracking-tight" style={accent ? { color: accent } : { color: '#151515' }}>
          {display}
        </div>
        {spark && <div className="h-9 w-24 shrink-0 self-center">{spark}</div>}
      </div>
      {sub && <div className={`mt-2 text-xs ${subTone}`}>{sub}</div>}
    </div>
  )
}

/* ---------- segmented risk meter ---------- */
export function RiskScore({ score = 0, size = 'md' }) {
  const band = riskBand(score)
  const color = riskColor(score)
  const num = size === 'lg' ? 'text-[34px]' : 'text-2xl'
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className={`tnum font-semibold leading-none tracking-tight ${num}`} style={{ color }}>
          {(Number.isFinite(Number(score)) ? Number(score) * 100 : 0).toFixed(0)}
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color }}>
          {riskLabel(score)}
        </span>
        <span className="ml-auto text-[11px] font-medium text-faint">risk score</span>
      </div>
      <div className="mt-2.5 flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className="h-1.5 flex-1 rounded-full transition-colors duration-300"
            style={{ backgroundColor: i <= band ? color : '#E5E5E0' }}
          />
        ))}
      </div>
    </div>
  )
}

/* ---------- horizontal score meter ---------- */
export function ScoreBar({ value = 0, color, height = 6, track = '#EFEFEC' }) {
  const c = color || riskColor(value)
  return (
    <div className="w-full overflow-hidden rounded-full" style={{ height, backgroundColor: track }}>
      <div
        className="h-full rounded-full"
        style={{
          width: `${Math.min(100, Math.max(3, value * 100))}%`,
          backgroundColor: c,
          transition: 'width 0.55s cubic-bezier(0.16,1,0.3,1)',
        }}
      />
    </div>
  )
}

/* ---------- toggle ---------- */
export function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200 disabled:opacity-50 ${
        checked ? 'bg-trust' : 'bg-line-strong'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
          checked ? 'translate-x-[18px]' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

/* ---------- segmented control ---------- */
export function Segmented({ options, value, onChange, size = 'md' }) {
  const pad = size === 'sm' ? 'px-2.5 py-1 text-[12px]' : 'px-3 py-1.5 text-[12.5px]'
  return (
    <div className="inline-flex rounded-md border border-line bg-canvas p-0.5">
      {options.map((o) => {
        const active = value === o.value
        return (
          <button
            key={String(o.value)}
            onClick={() => onChange(o.value)}
            className={`rounded-[5px] font-semibold transition-colors ${pad} ${
              active ? 'bg-paper text-ink shadow-sm' : 'text-faint hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/* ---------- states ---------- */
export function Spinner({ size = 16 }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-line-strong border-t-trust"
      style={{ width: size, height: size }}
    />
  )
}

export function Loader({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-20 text-sm text-muted">
      <Spinner /> {label}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      {Icon && (
        <span className="grid h-11 w-11 place-items-center rounded-lg border border-line bg-canvas text-faint">
          <Icon size={19} strokeWidth={2} />
        </span>
      )}
      <p className="mt-1 text-sm font-semibold text-ink">{title}</p>
      {hint && <p className="max-w-sm text-xs text-muted">{hint}</p>}
    </div>
  )
}
