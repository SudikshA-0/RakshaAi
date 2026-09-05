import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
} from 'recharts'
import { AXIS, GRID } from '../lib/theme'
import { num, compact, inrCompact, pct01 } from '../lib/format'

/* ---------- shared tooltip ---------- */
export function TooltipBox({ title, items = [] }) {
  return (
    <div className="rounded-md border border-line bg-paper px-3 py-2 shadow-menu">
      {title && <div className="mb-1.5 text-[11px] font-semibold text-faint">{title}</div>}
      <div className="space-y-1">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-3 text-xs">
            {it.color && <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: it.color }} />}
            <span className="text-muted">{it.label}</span>
            <span className="tnum ml-auto font-semibold text-ink">{it.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const fmtAxisDate = (d) => {
  if (!d) return ''
  const parts = String(d).split('-')
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : d
}

/* ---------- sparkline (inline SVG, for metric strips) ---------- */
export function Sparkline({ data = [], color = '#00B7CD', width = 96, height = 34 }) {
  const vals = data.map((d) => (typeof d === 'number' ? d : d?.v ?? 0))
  if (vals.length < 2) return null
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const pts = vals.map((v, i) => [
    (i / (vals.length - 1)) * width,
    height - ((v - min) / span) * (height - 5) - 3,
  ])
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L ${width} ${height} L 0 ${height} Z`
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="100%" preserveAspectRatio="none">
      <path d={area} fill={color} opacity="0.10" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

/* ---------- time-series trend ---------- */
const TREND = {
  volume: { label: 'Transactions', color: '#151515', fmt: (v) => num(v) },
  blocked: { label: 'Blocked', color: '#DF301C', fmt: (v) => num(v) },
  fraud: { label: 'Fraud attempts', color: '#E5590C', fmt: (v) => num(v) },
  saved: { label: 'Loss prevented', color: '#00B7CD', fmt: (v) => inrCompact(v) },
}

export function TrendChart({ data = [], metric = 'volume', height = 260 }) {
  const cfg = TREND[metric] || TREND.volume
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis
          dataKey="date"
          tickFormatter={fmtAxisDate}
          tick={{ fill: AXIS, fontSize: 11 }}
          axisLine={{ stroke: GRID }}
          tickLine={false}
          minTickGap={24}
          dy={6}
        />
        <YAxis
          tickFormatter={(v) => (metric === 'saved' ? inrCompact(v) : compact(v))}
          tick={{ fill: AXIS, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={52}
        />
        <Tooltip
          cursor={{ stroke: '#C9C9C2', strokeDasharray: '3 3' }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TooltipBox
                title={fmtAxisDate(label)}
                items={[{ color: cfg.color, label: cfg.label, value: cfg.fmt(payload[0].value) }]}
              />
            ) : null
          }
        />
        <Area
          type="monotone"
          dataKey={metric}
          stroke={cfg.color}
          strokeWidth={2}
          fill={cfg.color}
          fillOpacity={0.08}
          dot={false}
          activeDot={{ r: 3.5, strokeWidth: 0, fill: cfg.color }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ---------- decision-mix stacked bar ---------- */
export function DecisionMixBar({ segments = [] }) {
  const total = segments.reduce((s, x) => s + (x.value || 0), 0) || 1
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-canvas">
        {segments.map((s, i) => (
          <div
            key={i}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color }}
            title={`${s.label}: ${s.value}`}
          />
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4">
        {segments.map((s, i) => (
          <div key={i} className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: s.color }} />
              <span className="truncate text-[11px] font-medium text-muted">{s.label}</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="tnum text-lg font-semibold leading-none text-ink">{num(s.value)}</span>
              <span className="tnum text-[11px] text-faint">{pct01(s.value / total)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------- ranked horizontal bars (threats / drivers / features) ---------- */
export function RankedBars({ data = [], color = '#151515', format = (v) => num(v), max: maxProp }) {
  const max = maxProp || Math.max(...data.map((d) => d.value || 0), 1)
  return (
    <div className="space-y-2.5">
      {data.map((d, i) => (
        <div key={i} className="group grid grid-cols-[1fr_auto] items-center gap-x-3">
          <div className="col-span-2 flex items-baseline justify-between gap-3">
            <span className="truncate text-[12.5px] text-ink" title={d.label}>
              {d.label}
            </span>
            <span className="tnum shrink-0 text-[12.5px] font-semibold text-ink">{format(d.value)}</span>
          </div>
          <div className="col-span-2 mt-1 h-1.5 overflow-hidden rounded-full bg-canvas">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.max(2, ((d.value || 0) / max) * 100)}%`,
                backgroundColor: d.color || color,
                transition: 'width 0.6s cubic-bezier(0.16,1,0.3,1)',
              }}
            />
          </div>
          {d.sub && <span className="col-span-2 mt-0.5 text-[11px] text-faint">{d.sub}</span>}
        </div>
      ))}
    </div>
  )
}

/* ---------- precision–recall curve ---------- */
export function PRChart({ data = [], height = 220, color = '#00B7CD' }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -10 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis
          dataKey="recall"
          type="number"
          domain={[0, 1]}
          tickFormatter={(v) => v.toFixed(1)}
          tick={{ fill: AXIS, fontSize: 11 }}
          axisLine={{ stroke: GRID }}
          tickLine={false}
          dy={4}
        />
        <YAxis
          domain={[0, 1]}
          tickFormatter={(v) => v.toFixed(1)}
          tick={{ fill: AXIS, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={34}
        />
        <Tooltip
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox
                items={[
                  { color, label: 'Precision', value: pct01(payload[0].payload.precision) },
                  { label: 'Recall', value: pct01(payload[0].payload.recall) },
                ]}
              />
            ) : null
          }
        />
        <Line type="monotone" dataKey="precision" stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

/* ---------- cost curve with optimal marker ---------- */
export function CostCurve({ data = [], optimal, height = 220 }) {
  let opt = optimal
  if (opt == null && data.length) {
    opt = data.reduce((m, d) => (d.cost < m.cost ? d : m), data[0]).threshold
  }
  const optPoint = data.find((d) => Math.abs(d.threshold - opt) < 1e-6)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis
          dataKey="threshold"
          type="number"
          domain={[0, 1]}
          tickFormatter={(v) => v.toFixed(1)}
          tick={{ fill: AXIS, fontSize: 11 }}
          axisLine={{ stroke: GRID }}
          tickLine={false}
          dy={4}
        />
        <YAxis
          tickFormatter={(v) => inrCompact(v)}
          tick={{ fill: AXIS, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox
                title={`Threshold ${payload[0].payload.threshold.toFixed(2)}`}
                items={[{ color: '#151515', label: 'Expected cost', value: inrCompact(payload[0].value) }]}
              />
            ) : null
          }
        />
        {opt != null && <ReferenceLine x={opt} stroke="#00B7CD" strokeDasharray="4 4" strokeWidth={1.5} />}
        <Line type="monotone" dataKey="cost" stroke="#151515" strokeWidth={2} dot={false} />
        {optPoint && (
          <ReferenceDot x={optPoint.threshold} y={optPoint.cost} r={4} fill="#00B7CD" stroke="#fff" strokeWidth={1.5} />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}
