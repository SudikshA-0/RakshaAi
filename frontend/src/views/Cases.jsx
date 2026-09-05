import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldCheck,
  ShieldX,
  Inbox,
  GraduationCap,
  CheckCircle2,
  AlertTriangle,
  ArrowUp,
} from 'lucide-react'
import { api } from '../lib/api'
import { Segmented, Loader, EmptyState, Card, PageHeader } from '../components/primitives'
import TransactionDrawer from '../components/TransactionDrawer'
import { inr, fmtTime, timeAgo, noteTimeline, num } from '../lib/format'
import { patternLabel, riskColor, riskLabel } from '../lib/theme'

function LoopStat({ icon: Icon, label, value, iconClass }) {
  return (
    <div className="flex items-center gap-3">
      <span className={`grid h-9 w-9 place-items-center rounded-md ${iconClass}`}>
        <Icon size={16} strokeWidth={2} />
      </span>
      <div>
        <div className="tnum text-lg font-semibold leading-none text-ink">{num(value)}</div>
        <div className="stat-label mt-1">{label}</div>
      </div>
    </div>
  )
}

function CaseRow({ c, onResolve, onOpen, busy }) {
  const top = (c.reason_codes || []).slice(0, 3)
  const color = riskColor(c.risk_score)
  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, height: 0 }}
      className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-5 py-4 last:border-0 hover:bg-canvas"
    >
      <button onClick={() => onOpen(c)} className="min-w-0 flex-1 space-y-1.5 text-left">
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip">{patternLabel(c.fraud_pattern)}</span>
          {c.ring_flag && (
            <span className="pill bg-signal-soft px-2 py-0.5 text-[11px] text-signal-deep">Ring ×{c.ring_size}</span>
          )}
        </div>
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="tnum text-[17px] font-semibold text-ink">{inr(c.amount)}</span>
          <span className="font-mono text-xs text-muted">{c.txn_ref}</span>
          <span className="text-xs text-faint" title={fmtTime(c.ts)}>
            {timeAgo(c.ts)}
          </span>
        </div>
        {top.length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {top.map((r, i) => (
              <span key={i} className="inline-flex items-center gap-1 text-xs text-muted">
                <ArrowUp size={12} className="text-signal" strokeWidth={2.4} /> {r.label}
              </span>
            ))}
          </div>
        )}
      </button>

      <div className="flex items-center gap-5">
        <div className="text-right">
          <div className="tnum text-lg font-semibold leading-none" style={{ color }}>
            {(Number.isFinite(Number(c.risk_score)) ? Number(c.risk_score) * 100 : 0).toFixed(0)}
          </div>
          <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color }}>
            {riskLabel(c.risk_score)}
          </div>
        </div>

        {c.status === 'resolved' ? (
          <span
            className={`pill px-2.5 py-1 text-xs ${
              c.analyst_label === 1 ? 'bg-signal-soft text-signal-deep' : 'bg-trust-soft text-trust-deep'
            }`}
          >
            {c.analyst_label === 1 ? (
              <>
                <AlertTriangle size={12} /> Confirmed fraud
              </>
            ) : (
              <>
                <CheckCircle2 size={12} /> Released
              </>
            )}
          </span>
        ) : (
          <div className="flex gap-2">
            <button className="btn-secondary btn-xs" onClick={() => onResolve(c, 0)} disabled={busy}>
              <ShieldCheck size={14} className="text-trust-deep" /> Legit
            </button>
            <button className="btn-danger btn-xs" onClick={() => onResolve(c, 1)} disabled={busy}>
              <ShieldX size={14} /> Confirm fraud
            </button>
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default function Cases({ onPending }) {
  const [tab, setTab] = useState('pending')
  const [cases, setCases] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [cs, sm] = await Promise.all([api.cases(tab === 'resolved'), api.feedbackSummary()])
      setCases(cs.cases || [])
      setSummary(sm)
      setError(null)
      if (tab === 'pending') onPending?.((cs.cases || []).length)
    } catch (e) {
      setError(e.message || 'Failed to load cases')
    } finally {
      setLoading(false)
    }
  }, [tab, onPending])

  noteTimeline(...cases.map((c) => c.ts))

  useEffect(() => {
    load()
  }, [load])

  const resolve = async (c, label) => {
    setBusyId(c.id)
    try {
      const updated = await api.resolveCase(c.decision_id, { analyst_label: label, note: '' })
      setCases((prev) => prev.filter((x) => x.id !== c.id))
      const sm = await api.feedbackSummary()
      setSummary(sm)
      onPending?.(Math.max(0, cases.length - 1))
      setSelected((s) => (s && s.id === c.id ? { ...s, ...updated } : s))
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to resolve case')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <PageHeader
        title="Case Queue"
        subtitle="Human-in-the-loop review · every override becomes labeled training data"
        actions={
          <Segmented
            options={[
              { value: 'pending', label: 'Pending' },
              { value: 'resolved', label: 'Resolved' },
            ]}
            value={tab}
            onChange={setTab}
          />
        }
      />

      <div className="space-y-6 py-6">
        {error && (
          <div className="rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">{error}</div>
        )}
        {/* learning loop */}
        {summary && (
          <Card className="flex flex-wrap items-center gap-x-10 gap-y-5 p-5">
            <div className="flex items-center gap-3 pr-2">
              <span className="grid h-10 w-10 place-items-center rounded-md bg-canvas text-ink">
                <GraduationCap size={18} strokeWidth={2} />
              </span>
              <div>
                <div className="text-[13px] font-semibold text-ink">Learning loop</div>
                <div className="text-xs text-muted">Analyst decisions retrain the model</div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
              <LoopStat icon={Inbox} label="Total reviews" value={summary.total_feedback} iconClass="bg-canvas text-muted" />
              <LoopStat
                icon={AlertTriangle}
                label="Confirmed fraud"
                value={summary.confirmed_fraud}
                iconClass="bg-signal-soft text-signal"
              />
              <LoopStat
                icon={CheckCircle2}
                label="Released as legit"
                value={summary.confirmed_legit_released}
                iconClass="bg-trust-soft text-trust-deep"
              />
              <LoopStat
                icon={ArrowUp}
                label="Action overrides"
                value={summary.analyst_overrides || 0}
                iconClass="bg-canvas text-muted"
              />
            </div>
          </Card>
        )}

        {loading ? (
          <Loader label="Loading cases…" />
        ) : cases.length ? (
          <Card className="overflow-hidden">
            <AnimatePresence initial={false}>
              {cases.map((c) => (
                <CaseRow key={c.id} c={c} onResolve={resolve} onOpen={setSelected} busy={busyId === c.id} />
              ))}
            </AnimatePresence>
          </Card>
        ) : (
          <Card>
            <EmptyState
              icon={Inbox}
              title={tab === 'pending' ? 'Queue is clear' : 'No resolved cases yet'}
              hint={
                tab === 'pending'
                  ? 'No transactions are awaiting manual review.'
                  : 'Resolve pending cases to see them here.'
              }
            />
          </Card>
        )}
      </div>

      <TransactionDrawer txn={selected} onClose={() => setSelected(null)} onResolve={resolve} />
    </div>
  )
}
