import { useEffect, useState } from 'react'
import { SlidersHorizontal, ShieldCheck, Save, RotateCcw, Check, Info, Scale } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHeader, Toggle, Loader, RiskBadge, PageHeader } from '../components/primitives'
import { actionMeta } from '../lib/theme'

const APPETITE_SHIFT = 0.18
const clamp = (v) => Math.max(0.02, Math.min(0.98, v))

function effective(base, appetite) {
  const shift = (appetite - 0.5) * 2 * APPETITE_SHIFT
  return {
    challenge: clamp(base.challenge - shift),
    review: clamp(base.review - shift),
    block: clamp(base.block - shift),
  }
}

function DecisionBands({ eff }) {
  const segs = [
    { action: 'ALLOW', from: 0, to: eff.challenge },
    { action: 'STEP_UP', from: eff.challenge, to: eff.review },
    { action: 'HOLD', from: eff.review, to: eff.block },
    { action: 'BLOCK', from: eff.block, to: 1 },
  ]
  return (
    <div>
      <div className="flex h-9 w-full overflow-hidden rounded-md border border-line">
        {segs.map((s) => (
          <div
            key={s.action}
            style={{ width: `${(s.to - s.from) * 100}%`, backgroundColor: actionMeta(s.action).color }}
            className="transition-all duration-500"
            title={actionMeta(s.action).label}
          />
        ))}
      </div>
      <div className="relative mt-1 h-4">
        {['challenge', 'review', 'block'].map((k) => (
          <span
            key={k}
            className="tnum absolute -translate-x-1/2 text-[10px] font-semibold text-muted"
            style={{ left: `${eff[k] * 100}%` }}
          >
            {(eff[k] * 100).toFixed(0)}
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <RiskBadge action="ALLOW" size="sm" />
        <RiskBadge action="STEP_UP" size="sm" />
        <RiskBadge action="HOLD" size="sm" />
        <RiskBadge action="BLOCK" size="sm" />
      </div>
    </div>
  )
}

function Slider({ label, hint, value, onChange, leftLabel, rightLabel }) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-ink">{label}</span>
        <span className="tnum text-[13px] font-semibold text-ink">{(value * 100).toFixed(0)}%</span>
      </div>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="rk mt-3 w-full"
      />
      <div className="mt-1.5 flex justify-between text-[10px] font-medium uppercase tracking-wide text-faint">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
    </div>
  )
}

export default function Policy() {
  const [policy, setPolicy] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .policy()
      .then((p) => {
        setPolicy(p)
        setDraft({
          risk_appetite: p.risk_appetite,
          chargeback_weight: p.chargeback_weight,
          auto_block_enabled: p.auto_block_enabled,
        })
      })
      .catch((e) => setError(e.message || 'Failed to load policy'))
  }, [])

  if (error && !policy)
    return (
      <div className="py-6">
        <div className="rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">{error}</div>
      </div>
    )

  if (!policy || !draft) return <Loader label="Loading policy…" />

  const base = {
    challenge: policy.challenge_threshold,
    review: policy.review_threshold,
    block: policy.block_threshold,
  }
  const eff = effective(base, draft.risk_appetite)
  const dirty =
    draft.risk_appetite !== policy.risk_appetite ||
    draft.chargeback_weight !== policy.chargeback_weight ||
    draft.auto_block_enabled !== policy.auto_block_enabled

  const save = async () => {
    setSaving(true)
    try {
      const updated = await api.updatePolicy(draft)
      setPolicy(updated)
      setDraft({
        risk_appetite: updated.risk_appetite,
        chargeback_weight: updated.chargeback_weight,
        auto_block_enabled: updated.auto_block_enabled,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2200)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to apply policy')
    } finally {
      setSaving(false)
    }
  }

  const reset = () =>
    setDraft({ risk_appetite: 0.5, chargeback_weight: 0.35, auto_block_enabled: true })

  return (
    <div>
      <PageHeader
        title="Risk Policy"
        subtitle="Tune the engine to your loss appetite — changes apply to live scoring instantly"
        actions={
          <>
            {dirty && !saved && (
              <span className="hidden items-center gap-1.5 text-xs font-medium text-warn-deep sm:flex">
                <span className="h-1.5 w-1.5 rounded-full bg-warn" /> Unsaved changes
              </span>
            )}
            <button className="btn-secondary" onClick={reset}>
              <RotateCcw size={15} /> Reset
            </button>
            <button className="btn-primary" onClick={save} disabled={!dirty || saving}>
              {saved ? (
                <>
                  <Check size={16} /> Applied
                </>
              ) : (
                <>
                  <Save size={16} /> Apply policy
                </>
              )}
            </button>
          </>
        }
      />

      <div className="py-6">
        {error && (
          <div className="mb-6 rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">
            {error}
          </div>
        )}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* controls */}
          <Card className="space-y-6 p-6">
            <SectionHeader title="Controls" subtitle="Blend risk and set aggressiveness" icon={SlidersHorizontal} />

            <Slider
              label="Risk sensitivity"
              hint="Higher blocks more aggressively; lower protects revenue and conversions"
              value={draft.risk_appetite}
              onChange={(v) => setDraft((d) => ({ ...d, risk_appetite: v }))}
              leftLabel="Revenue-first"
              rightLabel="Protection-first"
            />

            <Slider
              label="Chargeback weight"
              hint="How much dispute/chargeback probability counts toward the blended score"
              value={draft.chargeback_weight}
              onChange={(v) => setDraft((d) => ({ ...d, chargeback_weight: v }))}
              leftLabel="Fraud only"
              rightLabel="Chargeback-heavy"
            />

            <div className="flex items-center justify-between rounded-md border border-line bg-canvas px-4 py-3">
              <div className="flex items-center gap-3">
                <ShieldCheck size={18} className="text-trust-deep" />
                <div>
                  <div className="text-[13px] font-medium text-ink">Auto-block high risk</div>
                  <div className="text-xs text-muted">Decline automatically above the block threshold</div>
                </div>
              </div>
              <Toggle
                checked={draft.auto_block_enabled}
                onChange={(v) => setDraft((d) => ({ ...d, auto_block_enabled: v }))}
              />
            </div>
          </Card>

          {/* preview */}
          <Card className="space-y-5 p-6">
            <SectionHeader title="Decision bands" subtitle="How the blended risk score maps to actions" icon={Scale} />
            <DecisionBands eff={eff} />

            <div className="grid grid-cols-3 gap-3 pt-1">
              {[
                { k: 'challenge', label: 'Step-up ≥', c: 'text-warn-deep' },
                { k: 'review', label: 'Hold ≥', c: 'text-hold-deep' },
                { k: 'block', label: 'Block ≥', c: 'text-signal-deep' },
              ].map((t) => (
                <div key={t.k} className="rounded-md border border-line bg-canvas px-3 py-3">
                  <div className="stat-label">{t.label}</div>
                  <div className={`tnum mt-1 text-xl font-semibold ${t.c}`}>{(eff[t.k] * 100).toFixed(0)}</div>
                </div>
              ))}
            </div>

            <div className="flex items-start gap-2 rounded-md border border-line bg-cream-soft px-3 py-3 text-xs text-muted">
              <Info size={15} className="mt-0.5 shrink-0 text-trust-deep" />
              <span>
                Risk score = <b className="text-ink">(1 − w)</b> × fraud + <b className="text-ink">w</b> × chargeback, with w
                = {(draft.chargeback_weight * 100).toFixed(0)}%. The sensitivity slider shifts all thresholds by up to ±
                {(APPETITE_SHIFT * 100).toFixed(0)} points.
              </span>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
