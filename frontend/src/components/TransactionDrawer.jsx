import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  CreditCard,
  Smartphone,
  Globe,
  Mail,
  ArrowUp,
  ArrowDown,
  CheckCircle2,
  AlertTriangle,
  Users,
  Clock,
  ShieldCheck,
} from 'lucide-react'
import { RiskBadge, RiskScore, ScoreBar, Spinner } from './primitives'
import { inr, fmtTime, timeAgo, noteTimeline, titleCase, fixed } from '../lib/format'
import { patternLabel, actionMeta } from '../lib/theme'

function KV({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-[13px]">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium text-ink">{value}</span>
    </div>
  )
}

function Entity({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-line bg-canvas px-3 py-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-paper text-muted">
        <Icon size={14} strokeWidth={2} />
      </span>
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-faint">{label}</div>
        <div className="truncate font-mono text-[12px] text-ink">{value || '—'}</div>
      </div>
    </div>
  )
}

function SectionLabel({ icon: Icon, children, right }) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      {Icon && <Icon size={13} className="text-faint" strokeWidth={2} />}
      <span className="text-[11px] font-semibold uppercase tracking-[0.07em] text-faint">{children}</span>
      {right && <span className="ml-auto">{right}</span>}
    </div>
  )
}

export default function TransactionDrawer({ txn, onClose, onResolve }) {
  const open = !!txn
  const [busy, setBusy] = useState(null)
  if (txn?.ts) noteTimeline(txn.ts)

  const resolve = async (label) => {
    if (!onResolve) return
    setBusy(label)
    try {
      await onResolve(txn, label)
    } finally {
      setBusy(null)
    }
  }

  const reviewed = txn && txn.analyst_label != null
  const correct =
    txn &&
    ((txn.is_fraud && ['BLOCK', 'HOLD'].includes(txn.original_model_action || txn.action)) ||
      (!txn.is_fraud && ['ALLOW', 'STEP_UP'].includes(txn.original_model_action || txn.action)))
  const maxImpact = txn ? Math.max(...(txn.reason_codes || []).map((x) => Math.abs(x.impact)), 0.01) : 1

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-ink/40"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 34, stiffness: 340 }}
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[460px] flex-col border-l border-line bg-paper shadow-drawer"
          >
            {/* header */}
            <div className="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">
                    Transaction
                  </span>
                  {txn.ring_flag && (
                    <span className="pill bg-signal-soft px-1.5 py-0.5 text-[10px] text-signal-deep">
                      <Users size={10} strokeWidth={2.4} /> Ring ×{txn.ring_size}
                    </span>
                  )}
                </div>
                <h3 className="mt-1 font-mono text-[15px] font-medium text-ink">{txn.txn_ref}</h3>
                <p className="mt-0.5 text-xs text-faint">
                  {timeAgo(txn.ts)} · {fmtTime(txn.ts)} · {titleCase(txn.category)} · {titleCase(txn.channel)}
                </p>
              </div>
              <button
                onClick={onClose}
                className="-mr-1.5 rounded-md p-1.5 text-faint transition-colors hover:bg-canvas hover:text-ink"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* summary: amount + risk */}
              <div className="grid grid-cols-2 gap-px border-b border-line bg-line">
                <div className="bg-paper px-6 py-4">
                  <div className="stat-label">Amount</div>
                  <div className="tnum mt-1.5 text-[22px] font-semibold leading-none text-ink">{inr(txn.amount)}</div>
                </div>
                <div className="bg-paper px-6 py-4">
                  <RiskScore score={txn.risk_score} />
                </div>
              </div>

              <div className="flex items-center gap-2 border-b border-line px-6 py-3">
                <RiskBadge action={txn.final_action || txn.action} />
                <span className="text-xs text-muted">{actionMeta(txn.final_action || txn.action).desc}</span>
              </div>
              {txn.analyst_override && (
                <div className="border-b border-line bg-canvas px-6 py-2 text-xs text-muted">
                  Model originally decided <span className="font-semibold text-ink">{txn.original_model_action}</span>
                  {' · '}analyst final <span className="font-semibold text-ink">{txn.final_action}</span>
                </div>
              )}

              <div className="space-y-6 px-6 py-5">
                {/* score breakdown */}
                <div className="space-y-3">
                  <div>
                    <div className="mb-1.5 flex justify-between text-xs">
                      <span className="text-muted">Fraud probability</span>
                      <span className="tnum font-semibold text-ink">{fixed(txn.fraud_score * 100, 1)}%</span>
                    </div>
                    <ScoreBar value={txn.fraud_score} />
                  </div>
                  <div>
                    <div className="mb-1.5 flex justify-between text-xs">
                      <span className="text-muted">Chargeback probability</span>
                      <span className="tnum font-semibold text-ink">{fixed(txn.chargeback_score * 100, 1)}%</span>
                    </div>
                    <ScoreBar value={txn.chargeback_score} />
                  </div>
                </div>

                {/* reason codes */}
                <div>
                  <SectionLabel icon={ShieldCheck}>Why this decision</SectionLabel>
                  <div className="space-y-3">
                    {(txn.reason_codes || []).map((r, i) => {
                      const up = r.direction === 'increases'
                      return (
                        <div key={i}>
                          <div className="flex items-center justify-between text-[12.5px]">
                            <span className="flex items-center gap-1.5 text-ink">
                              {up ? (
                                <ArrowUp size={13} className="text-signal" strokeWidth={2.4} />
                              ) : (
                                <ArrowDown size={13} className="text-trust-deep" strokeWidth={2.4} />
                              )}
                              {r.label}
                            </span>
                            <span className="tnum text-faint">
                              {r.impact > 0 ? '+' : ''}
                              {fixed(r.impact, 2)}
                            </span>
                          </div>
                          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-canvas">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${(Math.abs(r.impact) / maxImpact) * 100}%`,
                                backgroundColor: up ? '#DF301C' : '#00B7CD',
                              }}
                            />
                          </div>
                        </div>
                      )
                    })}
                    {(!txn.reason_codes || !txn.reason_codes.length) && (
                      <p className="text-xs text-muted">No strong risk drivers — clean transaction.</p>
                    )}
                  </div>
                </div>

                {/* linked entities */}
                <div>
                  <SectionLabel>Linked entities</SectionLabel>
                  <div className="grid grid-cols-2 gap-2">
                    <Entity
                      icon={CreditCard}
                      label={`${titleCase(txn.card_type)} card`}
                      value={`${txn.card_bin}··${txn.card_last4}`}
                    />
                    <Entity icon={Smartphone} label="Device" value={txn.device_id} />
                    <Entity icon={Globe} label={`${txn.billing_country}→${txn.shipping_country}`} value={txn.ip} />
                    <Entity icon={Mail} label="Email" value={txn.email_domain} />
                  </div>
                </div>

                {/* details */}
                <div>
                  <SectionLabel>Details</SectionLabel>
                  <div className="divide-y divide-line rounded-md border border-line px-3">
                    <KV label="Customer" value={<span className="font-mono text-xs">{txn.customer_id}</span>} />
                    <KV label="Account age" value={`${txn.account_age_days} days`} />
                    <KV
                      label="Expected loss prevented"
                      value={<span className="tnum text-trust-deep">{inr(txn.expected_loss_prevented)}</span>}
                    />
                    <KV
                      label="Scoring latency"
                      value={
                        <span className="tnum inline-flex items-center gap-1">
                          <Clock size={12} className="text-faint" />
                          {fixed(txn.latency_ms, 0)} ms
                        </span>
                      }
                    />
                  </div>
                </div>

                {/* ground truth */}
                <div className="rounded-md border border-line bg-canvas px-4 py-3">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-faint">
                    Ground truth · demo labels
                  </div>
                  <div className="flex items-center gap-2 text-[13px]">
                    {txn.is_fraud ? (
                      <span className="inline-flex items-center gap-1.5 font-medium text-signal">
                        <AlertTriangle size={15} /> Fraud · {patternLabel(txn.fraud_pattern)}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 font-medium text-trust-deep">
                        <CheckCircle2 size={15} /> Legitimate
                      </span>
                    )}
                    <span
                      className={`ml-auto text-[11px] font-semibold ${correct ? 'text-trust-deep' : 'text-signal'}`}
                    >
                      {correct ? 'Model correct' : 'Model miss'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* resolve footer */}
            {onResolve && (
              <div className="border-t border-line px-6 py-4">
                {reviewed ? (
                  <div className="flex items-center justify-center gap-2 text-[13px] font-medium text-muted">
                    <CheckCircle2 size={15} className="text-trust" />
                    Reviewed · marked {txn.analyst_label === 1 ? 'fraud' : 'legitimate'}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2.5">
                    <button
                      onClick={() => resolve(0)}
                      disabled={busy !== null}
                      className="btn-secondary"
                    >
                      {busy === 0 ? <Spinner size={14} /> : <CheckCircle2 size={15} />}
                      Release as legit
                    </button>
                    <button
                      onClick={() => resolve(1)}
                      disabled={busy !== null}
                      className="btn-danger"
                    >
                      {busy === 1 ? <Spinner size={14} /> : <AlertTriangle size={15} />}
                      Confirm fraud
                    </button>
                  </div>
                )}
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
