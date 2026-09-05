import { Users } from 'lucide-react'
import { RiskBadge } from './primitives'
import { inr, fmtTime, timeAgo, noteTimeline, titleCase } from '../lib/format'
import { riskColor, riskBand } from '../lib/theme'

/* compact "signal-strength" risk meter + score */
function RiskMeter({ score = 0 }) {
  const band = riskBand(score)
  const color = riskColor(score)
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-end gap-0.5">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className="w-1 rounded-[1px]"
            style={{ height: 5 + i * 3, backgroundColor: i <= band ? color : '#E5E5E0' }}
          />
        ))}
      </div>
      <span className="tnum w-6 text-[12px] font-semibold" style={{ color }}>
        {(Number.isFinite(Number(score)) ? Number(score) * 100 : 0).toFixed(0)}
      </span>
    </div>
  )
}

function Row({ t, onSelect, isNew, selected }) {
  const instrument = t.card_last4
    ? `•••• ${t.card_last4}`
    : t.customer_id || '—'
  const instrumentTop = t.card_type ? titleCase(t.card_type) : t.channel ? titleCase(t.channel) : 'Card'
  return (
    <tr
      onClick={() => onSelect?.(t)}
      className={`cursor-pointer border-b border-line/70 transition-colors last:border-0 hover:bg-canvas ${
        selected ? 'bg-trust-soft' : isNew ? 'animate-row-in' : ''
      }`}
    >
      <td className="td tnum whitespace-nowrap text-faint" title={fmtTime(t.ts)}>
        {timeAgo(t.ts)}
      </td>
      <td className="td">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[12px] text-ink">{t.txn_ref}</span>
          {t.ring_flag && (
            <span className="pill bg-signal-soft px-1.5 py-0.5 text-[10px] text-signal-deep" title={`Ring of ${t.ring_size}`}>
              <Users size={10} strokeWidth={2.4} />
              {t.ring_size}
            </span>
          )}
        </div>
      </td>
      <td className="td hidden md:table-cell">
        <div className="flex flex-col leading-tight">
          <span className="text-[12.5px] text-ink">{instrumentTop}</span>
          <span className="tnum text-[11px] text-faint">{instrument}</span>
        </div>
      </td>
      <td className="td hidden lg:table-cell">
        <div className="flex flex-col leading-tight">
          <span className="text-[12.5px] text-ink">{titleCase(t.category || '—')}</span>
          <span className="text-[11px] capitalize text-faint">{(t.channel || '').replace(/_/g, ' ') || '—'}</span>
        </div>
      </td>
      <td className="td tnum whitespace-nowrap text-right font-semibold text-ink">{inr(t.amount)}</td>
      <td className="td">
        <RiskMeter score={t.risk_score} />
      </td>
      <td className="td text-right">
        <RiskBadge action={t.action} size="sm" />
      </td>
    </tr>
  )
}

export default function TransactionTable({ items = [], onSelect, newIds, selectedId }) {
  noteTimeline(...items.map((t) => t.ts))
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-line">
            <th className="th">Time</th>
            <th className="th">Reference</th>
            <th className="th hidden md:table-cell">Instrument</th>
            <th className="th hidden lg:table-cell">Category</th>
            <th className="th text-right">Amount</th>
            <th className="th">Risk</th>
            <th className="th text-right">Decision</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <Row
              key={t.id}
              t={t}
              onSelect={onSelect}
              isNew={newIds?.has(t.id)}
              selected={selectedId === t.id}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
