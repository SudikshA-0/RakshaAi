import { useEffect, useState, useCallback } from 'react'
import { Search, RefreshCw, Plus, Users, Radio } from 'lucide-react'
import { api } from '../lib/api'
import { Segmented, Toggle, Spinner, EmptyState, PageHeader, Card } from '../components/primitives'
import TransactionTable from '../components/TransactionTable'
import TransactionDrawer from '../components/TransactionDrawer'
import { num } from '../lib/format'

const LIMIT = 50

const ACTION_OPTS = [
  { value: '', label: 'All' },
  { value: 'ALLOW', label: 'Allow' },
  { value: 'STEP_UP', label: 'Step-up' },
  { value: 'HOLD', label: 'Hold' },
  { value: 'BLOCK', label: 'Block' },
]

export default function Transactions() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [action, setAction] = useState('')
  const [ringOnly, setRingOnly] = useState(false)
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(null)
  const [simulating, setSimulating] = useState(false)
  const [error, setError] = useState(null)

  const query = useCallback(
    (offset) => api.transactions({ limit: LIMIT, offset, action, ring_only: ringOnly || undefined, q }),
    [action, ringOnly, q]
  )

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const res = await query(0)
      const rows = res.transactions || []
      setItems(rows)
      setHasMore(rows.length === LIMIT)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load transactions')
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => {
    const id = setTimeout(reload, q ? 300 : 0)
    return () => clearTimeout(id)
  }, [reload, q])

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const res = await query(items.length)
      const rows = res.transactions || []
      setItems((prev) => [...prev, ...rows])
      setHasMore(rows.length === LIMIT)
    } finally {
      setLoadingMore(false)
    }
  }

  const simulate = async () => {
    setSimulating(true)
    try {
      await api.simulateBatch(5)
      await reload()
      setError(null)
    } catch (e) {
      setError(e.message || 'Simulation failed')
    } finally {
      setSimulating(false)
    }
  }

  const resolveTxn = async (t, label) => {
    try {
      const updated = await api.resolveCase(t.decision_id, { analyst_label: label, note: '' })
      setSelected((s) => (s && s.id === t.id ? { ...s, ...updated } : s))
      setItems((prev) => prev.map((x) => (x.id === t.id ? { ...x, ...updated } : x)))
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to resolve case')
    }
  }

  return (
    <div>
      <PageHeader
        title="Live Transactions"
        subtitle={`Every decision, fully explained · ${num(items.length)}${hasMore ? '+' : ''} shown`}
        actions={
          <>
            <button className="btn-secondary" onClick={reload}>
              <RefreshCw size={15} /> Refresh
            </button>
            <button className="btn-primary" onClick={simulate} disabled={simulating}>
              {simulating ? <Spinner size={15} /> : <Plus size={16} />} Simulate 5
            </button>
          </>
        }
      >
        {/* filter bar */}
        <div className="flex flex-wrap items-center gap-3 pb-4">
          <div className="relative min-w-[240px] flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search reference, customer, device, email…"
              className="input pl-9"
            />
          </div>
          <Segmented options={ACTION_OPTS} value={action} onChange={setAction} size="sm" />
          <label className="flex items-center gap-2 rounded-md border border-line bg-paper px-3 py-2 text-[13px] text-ink">
            <Users size={14} className="text-faint" /> Rings only
            <Toggle checked={ringOnly} onChange={setRingOnly} />
          </label>
        </div>
      </PageHeader>

      <div className="py-6">
        {error && (
          <div className="mb-4 rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">
            {error}
          </div>
        )}
        <Card>
          {loading ? (
            <div className="flex items-center justify-center gap-3 py-16 text-sm text-muted">
              <Spinner /> Loading transactions…
            </div>
          ) : items.length ? (
            <>
              <TransactionTable items={items} onSelect={setSelected} selectedId={selected?.id} />
              {hasMore && (
                <div className="flex justify-center border-t border-line px-5 py-4">
                  <button className="btn-secondary btn-xs" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? <Spinner size={13} /> : null}
                    Load {LIMIT} more
                  </button>
                </div>
              )}
            </>
          ) : (
            <EmptyState icon={Radio} title="No transactions match" hint="Try clearing filters or simulate some traffic." />
          )}
        </Card>
      </div>

      <TransactionDrawer txn={selected} onClose={() => setSelected(null)} onResolve={resolveTxn} />
    </div>
  )
}
