import { useEffect, useState, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Play, Pause, Zap, ChevronDown, Crosshair, X, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { Card, Metric, SectionHeader, Segmented, RiskBadge, Loader, PageHeader } from '../components/primitives'
import { TrendChart, DecisionMixBar, RankedBars, Sparkline } from '../components/charts'
import TransactionTable from '../components/TransactionTable'
import TransactionDrawer from '../components/TransactionDrawer'
import { num, inrCompact, inr, pct, fixed } from '../lib/format'
import { actionMeta, patternLabel } from '../lib/theme'

const ATTACKS = [
  { kind: 'card_testing', label: 'Card-testing ring', hint: '14 rapid low-value probes from one device', count: 14 },
  { kind: 'account_takeover', label: 'Account takeover', hint: '8 high-spend orders on a hijacked account', count: 8 },
  { kind: 'high_value', label: 'High-value bust-out', hint: '10 stolen-card cash-out attempts', count: 10 },
]

const ACTION_ORDER = ['ALLOW', 'STEP_UP', 'HOLD', 'BLOCK']

function AttackMenu({ onAttack, running }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button className="btn-danger" onClick={() => setOpen((o) => !o)} disabled={running}>
        <Zap size={15} /> Simulate attack
        <ChevronDown size={14} className={open ? 'rotate-180 transition' : 'transition'} />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.14 }}
              className="absolute right-0 z-20 mt-2 w-72 overflow-hidden rounded-lg border border-line bg-paper p-1.5 shadow-menu"
            >
              {ATTACKS.map((a) => (
                <button
                  key={a.kind}
                  onClick={() => {
                    setOpen(false)
                    onAttack(a)
                  }}
                  className="flex w-full items-start gap-3 rounded-md px-2.5 py-2.5 text-left transition-colors hover:bg-canvas"
                >
                  <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-signal-soft text-signal">
                    <Crosshair size={14} strokeWidth={2} />
                  </span>
                  <span>
                    <span className="block text-[13px] font-semibold text-ink">{a.label}</span>
                    <span className="block text-xs text-muted">{a.hint}</span>
                  </span>
                </button>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function Dashboard({ onHealth, onPending }) {
  const [overview, setOverview] = useState(null)
  const [series, setSeries] = useState([])
  const [threats, setThreats] = useState([])
  const [drivers, setDrivers] = useState([])
  const [feed, setFeed] = useState([])
  const [newIds, setNewIds] = useState(new Set())
  const [selected, setSelected] = useState(null)
  const [live, setLive] = useState(false)
  const [metric, setMetric] = useState('volume')
  const [range, setRange] = useState(7)
  const [attackRunning, setAttackRunning] = useState(false)
  const [attackResult, setAttackResult] = useState(null)
  const [error, setError] = useState(null)
  const liveRef = useRef(live)
  liveRef.current = live

  const loadStats = useCallback(
    async (r = range) => {
      const [ov, ts, th, dr] = await Promise.all([api.overview(), api.timeseries(r), api.threats(), api.drivers()])
      setOverview(ov)
      setSeries(ts.series || [])
      setThreats(th.patterns || [])
      setDrivers(dr.drivers || [])
      setError(null)
      onHealth?.(true)
      onPending?.(ov.pending_review || 0)
    },
    [range, onHealth, onPending]
  )

  useEffect(() => {
    ;(async () => {
      try {
        const tx = await api.transactions({ limit: 40 })
        setFeed(tx.transactions || [])
        await loadStats()
      } catch (e) {
        onHealth?.(false)
        setError(e.message || 'Failed to load dashboard')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    api
      .timeseries(range)
      .then((ts) => setSeries(ts.series || []))
      .catch((e) => setError(e.message || 'Failed to load timeseries'))
  }, [range])

  const mergeFeed = useCallback((incoming) => {
    const ids = new Set(incoming.map((t) => t.id))
    setNewIds(ids)
    setFeed((prev) => {
      const map = new Map()
      ;[...incoming, ...prev].forEach((t) => map.set(t.id, t))
      return [...map.values()].sort((a, b) => b.id - a.id).slice(0, 40)
    })
    setTimeout(() => setNewIds(new Set()), 1400)
  }, [])

  useEffect(() => {
    if (!live) return
    let timer
    const tick = async () => {
      if (!liveRef.current) return
      try {
        const n = 2 + Math.floor(Math.random() * 4)
        const res = await api.simulateBatch(n)
        mergeFeed(res.transactions || [])
        await loadStats()
      } catch (e) {
        onHealth?.(false)
        setError(e.message || 'Live feed failed')
      }
      timer = setTimeout(tick, 2600)
    }
    timer = setTimeout(tick, 800)
    return () => clearTimeout(timer)
  }, [live, mergeFeed, loadStats])

  const runAttack = async (a) => {
    setAttackRunning(true)
    setAttackResult(null)
    try {
      const res = await api.attack({ kind: a.kind, count: a.count })
      mergeFeed(res.transactions || [])
      setAttackResult({ ...res, label: a.label })
      await loadStats()
    } catch (e) {
      setError(e.message || 'Attack simulation failed')
    } finally {
      setAttackRunning(false)
    }
  }

  const resolveTxn = async (t, label) => {
    try {
      const updated = await api.resolveCase(t.decision_id, { analyst_label: label, note: '' })
      setSelected((s) => (s && s.id === t.id ? { ...s, ...updated } : s))
      setFeed((prev) => prev.map((x) => (x.id === t.id ? { ...x, ...updated } : x)))
      loadStats().catch((e) => setError(e.message || 'Failed to refresh stats'))
    } catch (e) {
      setError(e.message || 'Failed to resolve case')
    }
  }

  if (!overview) {
    return error ? (
      <div className="py-6">
        <div className="rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">{error}</div>
      </div>
    ) : (
      <Loader label="Booting risk engine…" />
    )
  }

  const segments = ACTION_ORDER.map((k) => ({
    label: actionMeta(k).label,
    value: overview.action_counts?.[k] || 0,
    color: actionMeta(k).color,
  }))

  const threatData = threats
    .filter((t) => t.pattern !== 'legit' && t.pattern !== 'none')
    .map((t) => ({ label: patternLabel(t.pattern), value: t.count, sub: `${inrCompact(t.value_at_risk)} at risk` }))

  const driverData = drivers.slice(0, 7).map((d) => ({ label: d.label, value: d.count }))

  return (
    <div>
      <PageHeader
        title="Command Center"
        subtitle={`${num(overview.total_transactions)} decisions scored · ${fixed(overview.avg_latency_ms, 0)} ms median latency`}
        actions={
          <>
            <button className="btn-secondary" onClick={() => setLive((l) => !l)}>
              {live ? <Pause size={15} /> : <Play size={15} />}
              {live ? 'Pause feed' : 'Go live'}
            </button>
            <AttackMenu onAttack={runAttack} running={attackRunning} />
          </>
        }
      />

      <div className="space-y-6 py-6">
        {error && (
          <div className="rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">
            {error}
          </div>
        )}
        {/* attack result banner */}
        <AnimatePresence>
          {attackResult && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-lg border border-signal/30 bg-signal-soft px-4 py-3.5">
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-md border border-signal/30 bg-paper text-signal">
                    <ShieldCheck size={18} />
                  </span>
                  <div>
                    <div className="text-[13px] font-semibold text-ink">{attackResult.label} neutralized</div>
                    <div className="text-xs text-muted">
                      {attackResult.count} attempts ·{' '}
                      {attackResult.ring_detected ? `ring of ${attackResult.ring_size} detected` : 'no ring'}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-8">
                  <div>
                    <div className="tnum text-lg font-semibold text-trust-deep">{attackResult.stop_rate}%</div>
                    <div className="stat-label">Stopped</div>
                  </div>
                  <div>
                    <div className="tnum text-lg font-semibold text-ink">{inr(attackResult.loss_prevented)}</div>
                    <div className="stat-label">Loss prevented</div>
                  </div>
                  <div className="hidden gap-1.5 sm:flex">
                    {attackResult.blocked > 0 && <RiskBadge action="BLOCK" size="sm" />}
                    {attackResult.held > 0 && <RiskBadge action="HOLD" size="sm" />}
                    {attackResult.stepped_up > 0 && <RiskBadge action="STEP_UP" size="sm" />}
                  </div>
                </div>
                <button
                  onClick={() => setAttackResult(null)}
                  className="ml-auto rounded-md p-1.5 text-faint transition-colors hover:bg-paper hover:text-ink"
                >
                  <X size={16} />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* metric strip */}
        <Card className="grid grid-cols-2 divide-line lg:grid-cols-4 lg:divide-x">
          <Metric
            label="Transactions scored"
            value={overview.total_transactions}
            format={(v) => num(Math.round(v))}
            sub={`${pct(overview.flag_rate)} flagged for action`}
            spark={<Sparkline data={series.map((s) => s.volume)} color="#151515" />}
            className="border-b border-line lg:border-b-0"
          />
          <Metric
            label="Fraud blocked"
            value={overview.fraud_caught}
            format={(v) => num(Math.round(v))}
            sub={`${pct(overview.detection_rate)} of fraud caught`}
            spark={<Sparkline data={series.map((s) => s.blocked)} color="#DF301C" />}
            className="border-b border-l border-line lg:border-b-0 lg:border-l-0"
          />
          <Metric
            label="Net loss prevented"
            value={overview.net_benefit}
            format={(v) => inrCompact(v)}
            accent="#0A7080"
            sub={`${inrCompact(overview.money_saved)} gross saved`}
            spark={<Sparkline data={series.map((s) => s.saved)} color="#00B7CD" />}
          />
          <Metric
            label="Model precision"
            value={overview.precision}
            format={(v) => pct(v)}
            sub={`${pct(overview.false_positive_rate)} false-positive rate`}
            className="border-l border-line lg:border-l-0"
          />
        </Card>

        {/* trend + decision mix */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="p-5 lg:col-span-2">
            <SectionHeader
              title="Transaction flow"
              subtitle="Decision volume over time"
              right={
                <div className="flex flex-wrap items-center gap-2">
                  <Segmented
                    size="sm"
                    options={[
                      { value: 'volume', label: 'Volume' },
                      { value: 'blocked', label: 'Blocked' },
                      { value: 'saved', label: 'Saved' },
                    ]}
                    value={metric}
                    onChange={setMetric}
                  />
                  <Segmented
                    size="sm"
                    options={[
                      { value: 7, label: '7D' },
                      { value: 14, label: '14D' },
                      { value: 30, label: '30D' },
                    ]}
                    value={range}
                    onChange={setRange}
                  />
                </div>
              }
            />
            <div className="mt-4">
              <TrendChart data={series} metric={metric} />
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader title="Decision mix" subtitle="How the engine acted" />
            <div className="mt-5">
              <DecisionMixBar segments={segments} />
            </div>
          </Card>
        </div>

        {/* threats + drivers */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card className="p-5">
            <SectionHeader title="Threat patterns" subtitle="Fraud typologies caught, by count" />
            <div className="mt-5">
              {threatData.length ? (
                <RankedBars data={threatData} color="#151515" />
              ) : (
                <p className="py-6 text-sm text-muted">No fraud typologies detected yet.</p>
              )}
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader title="Top risk drivers" subtitle="Most frequent decision factors" />
            <div className="mt-5">
              {driverData.length ? (
                <RankedBars data={driverData} color="#4B5563" />
              ) : (
                <p className="py-6 text-sm text-muted">No risk drivers recorded yet.</p>
              )}
            </div>
          </Card>
        </div>

        {/* live stream */}
        <Card>
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <SectionHeader title="Live transaction stream" subtitle="Newest decisions first — click a row to investigate" />
            {live && (
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-trust-deep">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-trust" /> Live
              </span>
            )}
          </div>
          {feed.length ? (
            <TransactionTable
              items={feed.slice(0, 12)}
              onSelect={setSelected}
              newIds={newIds}
              selectedId={selected?.id}
            />
          ) : (
            <p className="px-5 py-12 text-center text-sm text-muted">No transactions yet — press “Go live”.</p>
          )}
        </Card>
      </div>

      <TransactionDrawer txn={selected} onClose={() => setSelected(null)} onResolve={resolveTxn} />
    </div>
  )
}
