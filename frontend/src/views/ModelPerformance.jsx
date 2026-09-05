import { useEffect, useState } from 'react'
import { Brain, Target, TrendingDown, Sparkles, CreditCard, BarChart3 } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHeader, Loader, EmptyState, PageHeader } from '../components/primitives'
import { PRChart, CostCurve, RankedBars } from '../components/charts'
import { inr, inrCompact, pct01, num, fixed } from '../lib/format'

function MetricTile({ label, value, accent = 'text-ink' }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-3.5 py-3">
      <div className="stat-label">{label}</div>
      <div className={`tnum mt-1.5 text-xl font-semibold ${accent}`}>{value}</div>
    </div>
  )
}

function Confusion({ c }) {
  if (!c) return null
  const Cell = ({ v, label, good }) => (
    <div className={`rounded-md px-3 py-3 text-center ${good ? 'bg-trust-soft' : 'bg-signal-soft'}`}>
      <div className={`tnum text-xl font-semibold ${good ? 'text-trust-deep' : 'text-signal-deep'}`}>{num(v)}</div>
      <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">{label}</div>
    </div>
  )
  return (
    <div>
      <div className="mb-2 grid grid-cols-[60px_1fr_1fr] text-[10px] font-semibold uppercase tracking-wide text-faint">
        <span />
        <span className="text-center">Pred fraud</span>
        <span className="text-center">Pred legit</span>
      </div>
      <div className="grid grid-cols-[60px_1fr_1fr] items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">Fraud</span>
        <Cell v={c.tp} label="Caught" good />
        <Cell v={c.fn} label="Missed" />
        <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">Legit</span>
        <Cell v={c.fp} label="False alarm" />
        <Cell v={c.tn} label="Cleared" good />
      </div>
    </div>
  )
}

export default function ModelPerformance() {
  const [model, setModel] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .model()
      .then(setModel)
      .catch((e) => setError(e.message || 'Failed to load model metrics'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Loader label="Loading model metrics…" />
  if (error)
    return (
      <div className="py-6">
        <div className="rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">{error}</div>
      </div>
    )
  if (!model || !model.available)
    return (
      <div className="py-6">
        <Card>
          <EmptyState
            icon={Brain}
            title="Model artifacts not found"
            hint="Train the models first: python -m ml_pipeline.train"
          />
        </Card>
      </div>
    )

  const f = model.fraud || {}
  const cb = model.chargeback || {}
  const fi = (model.feature_importance || [])
    .slice(0, 12)
    .map((d) => ({ label: d.label, value: +fixed(d.importance, 3) }))

  return (
    <div>
      <PageHeader
        title="Model Performance"
        subtitle={`Two gradient-boosted models · ${num(model.n_train)} train / ${num(model.n_test)} test · ${pct01(
          model.fraud_rate_test
        )} fraud base rate`}
        actions={
          <span className="chip">
            <Sparkles size={13} className="text-trust-deep" /> Temporal split · no leakage
          </span>
        }
      />

      <div className="space-y-6 py-6">
        {/* fraud model */}
        <Card className="p-5">
          <SectionHeader title="Fraud detection model" subtitle="XGBoost classifier · cost-tuned threshold" icon={Target} />
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <MetricTile label="Precision" value={pct01(f.precision)} accent="text-trust-deep" />
            <MetricTile label="Recall" value={pct01(f.recall)} accent="text-ink" />
            <MetricTile label="F1 score" value={fixed(f?.f1, 3)} />
            <MetricTile label="PR-AUC" value={fixed(f?.pr_auc, 3)} />
            <MetricTile label="ROC-AUC" value={fixed(f?.roc_auc, 3)} />
          </div>
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.07em] text-faint">
                Precision–recall curve
              </div>
              <PRChart data={f.pr_curve} color="#00B7CD" />
            </div>
            <div>
              <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.07em] text-faint">
                Confusion matrix @ threshold {f.threshold}
              </div>
              <Confusion c={f.confusion} />
            </div>
          </div>
        </Card>

        {/* cost optimization */}
        <Card className="p-5">
          <SectionHeader
            title="Cost-sensitive threshold optimization"
            subtitle="The cutoff is tuned to minimise real rupee loss — not just accuracy"
            icon={TrendingDown}
          />
          <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <CostCurve data={f.cost_curve} optimal={f.threshold} />
            </div>
            <div className="flex flex-col justify-center gap-3">
              <div className="rounded-md border border-trust/30 bg-trust-soft px-4 py-3">
                <div className="stat-label">Optimal threshold</div>
                <div className="tnum mt-1 text-2xl font-semibold text-trust-deep">{f.threshold}</div>
                <div className="mt-0.5 text-xs text-muted">minimises expected loss</div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <MetricTile label="Loss, no model" value={inrCompact(f.baseline_cost)} accent="text-signal-deep" />
                <MetricTile label="Loss, optimised" value={inrCompact(f.optimized_cost)} accent="text-trust-deep" />
              </div>
              <div className="rounded-md border border-line bg-cream-soft px-4 py-3">
                <div className="stat-label">Loss avoided on test set</div>
                <div className="tnum mt-1 text-2xl font-semibold text-ink">{inrCompact(f.savings)}</div>
              </div>
            </div>
          </div>
        </Card>

        {/* chargeback model */}
        <Card className="p-5">
          <SectionHeader
            title="Chargeback prediction model"
            subtitle="Flags friendly-fraud / dispute risk before settlement"
            icon={CreditCard}
          />
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <MetricTile label="Precision" value={pct01(cb.precision)} accent="text-trust-deep" />
            <MetricTile label="Recall" value={pct01(cb.recall)} accent="text-ink" />
            <MetricTile label="F1 score" value={fixed(cb?.f1, 3)} />
            <MetricTile label="PR-AUC" value={fixed(cb?.pr_auc, 3)} />
            <MetricTile label="ROC-AUC" value={fixed(cb?.roc_auc, 3)} />
          </div>
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.07em] text-faint">
                Precision–recall curve
              </div>
              <PRChart data={cb.pr_curve} color="#151515" />
            </div>
            <div>
              <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.07em] text-faint">
                Confusion matrix @ threshold {cb.threshold}
              </div>
              <Confusion c={cb.confusion} />
            </div>
          </div>
        </Card>

        {/* feature importance */}
        <Card className="p-5">
          <SectionHeader title="What the model learned" subtitle="Global feature importance (gain)" icon={BarChart3} />
          <div className="mt-5">
            <RankedBars data={fi} color="#151515" format={(v) => fixed(v, 2)} />
          </div>
        </Card>
      </div>
    </div>
  )
}
