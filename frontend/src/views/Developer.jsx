import { Fragment, useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Check,
  Clipboard,
  Code2,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldCheck,
  Webhook,
  X,
} from 'lucide-react'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { Card, EmptyState, Loader, PageHeader, SectionHeader, Segmented, Spinner } from '../components/primitives'

function EnvironmentBadge({ environment }) {
  const sandbox = environment === 'sandbox'
  return (
    <span className={`pill px-2 py-0.5 text-[11px] ${sandbox ? 'bg-cream-soft text-warn-deep' : 'bg-trust-soft text-trust-deep'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${sandbox ? 'bg-warn' : 'bg-trust'}`} />
      {sandbox ? 'Sandbox' : 'Live'}
    </span>
  )
}

function KeyStatus({ revokedAt }) {
  return revokedAt ? (
    <span className="pill bg-signal-soft px-2 py-0.5 text-[11px] text-signal-deep">
      <span className="h-1.5 w-1.5 rounded-full bg-signal" /> Revoked
    </span>
  ) : (
    <span className="pill bg-trust-soft px-2 py-0.5 text-[11px] text-trust-deep">
      <span className="h-1.5 w-1.5 rounded-full bg-trust" /> Active
    </span>
  )
}

function SecretNotice({ secret, onDismiss }) {
  const [copied, setCopied] = useState(false)
  const value = secret.api_key || secret.signing_secret
  const kind = secret.signing_secret ? 'signing secret' : 'API key'
  const envHint = secret.signing_secret
    ? 'Use it to verify X-RakshaAI-Signature (HMAC-SHA256 of the exact request body).'
    : `This ${secret.environment === 'sandbox' ? 'sandbox' : 'live'} key is shown only once. Store it in your server-side secret manager; it cannot be recovered after dismissal.`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Card className="border-trust/35 bg-trust-soft p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-trust text-ink-900">
            <ShieldCheck size={18} strokeWidth={2.2} />
          </span>
          <div className="min-w-0">
            <h2 className="text-[14px] font-semibold text-ink">Copy your {kind} now</h2>
            <p className="mt-1 text-xs text-muted">{envHint}</p>
          </div>
        </div>
        <button type="button" onClick={onDismiss} className="btn-ghost btn-xs shrink-0" aria-label={`Dismiss ${kind}`}>
          <X size={15} />
        </button>
      </div>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-md border border-trust/30 bg-paper px-3 py-2.5 font-mono text-[12px] text-ink">
          {value}
        </code>
        <button type="button" className="btn-secondary shrink-0" onClick={copy}>
          {copied ? <><Check size={15} className="text-trust-deep" /> Copied</> : <><Clipboard size={15} /> Copy</>}
        </button>
      </div>
    </Card>
  )
}

function CreateKeyForm({ onCreate, creating, onCancel }) {
  const [name, setName] = useState('')
  const [environment, setEnvironment] = useState('sandbox')

  const submit = (event) => {
    event.preventDefault()
    onCreate({ name: name.trim(), environment })
  }

  return (
    <Card className="p-5">
      <SectionHeader title="Create API key" subtitle="Choose the environment for this server-side integration" icon={KeyRound} />
      <form className="mt-5 space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="mb-1.5 block text-[12px] font-semibold text-ink">Key name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Production checkout" minLength={2} maxLength={120} required autoFocus />
        </label>
        <div>
          <span className="mb-1.5 block text-[12px] font-semibold text-ink">Environment</span>
          <Segmented
            value={environment}
            onChange={setEnvironment}
            options={[{ value: 'sandbox', label: 'Sandbox' }, { value: 'live', label: 'Live' }]}
          />
          <p className="mt-2 text-xs text-muted">Sandbox keys are for testing. Live keys are for production merchant traffic.</p>
        </div>
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={creating}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={creating || name.trim().length < 2}>
            {creating ? <><Spinner size={15} /> Creating</> : <><KeyRound size={15} /> Create key</>}
          </button>
        </div>
      </form>
    </Card>
  )
}

function CreateWebhookForm({ onCreate, creating, onCancel }) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  const submit = (event) => {
    event.preventDefault()
    onCreate({ name: name.trim(), url: url.trim() })
  }

  return (
    <Card className="p-5">
      <SectionHeader title="Create webhook" subtitle="RakshaAI will POST signed decision events to this HTTPS endpoint" icon={Webhook} />
      <form className="mt-5 space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="mb-1.5 block text-[12px] font-semibold text-ink">Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Production decisions" minLength={2} maxLength={120} required autoFocus />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[12px] font-semibold text-ink">Endpoint URL</span>
          <input className="input font-mono text-[13px]" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://merchant.example.com/webhooks/rakshaai" required />
        </label>
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={creating}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={creating || name.trim().length < 2 || !url.trim()}>
            {creating ? <><Spinner size={15} /> Creating</> : <><Webhook size={15} /> Create webhook</>}
          </button>
        </div>
      </form>
    </Card>
  )
}

function ApiKeysPanel() {
  const [keys, setKeys] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [revokingId, setRevokingId] = useState(null)
  const [secret, setSecret] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.apiKeys()
      setKeys(result.keys || [])
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load API keys')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const create = async (payload) => {
    setCreating(true)
    try {
      const created = await api.createApiKey(payload)
      setSecret({ api_key: created.api_key, environment: created.environment })
      setShowCreate(false)
      await load()
    } catch (e) {
      setError(e.message || 'Failed to create API key')
    } finally {
      setCreating(false)
    }
  }

  const revoke = async (key) => {
    if (!window.confirm(`Revoke “${key.name}”? This key will stop working immediately and cannot be reactivated.`)) return
    setRevokingId(key.id)
    try {
      await api.revokeApiKey(key.id)
      await load()
    } catch (e) {
      setError(e.message || 'Failed to revoke API key')
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" /> <span>{error}</span>
        </div>
      )}
      {secret && <SecretNotice secret={secret} onDismiss={() => setSecret(null)} />}
      {showCreate && <CreateKeyForm onCreate={create} creating={creating} onCancel={() => setShowCreate(false)} />}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <SectionHeader title="API keys" subtitle="Keys are scoped to this merchant organization" icon={KeyRound} />
          <div className="flex gap-2">
            <button type="button" className="btn-secondary btn-xs" onClick={load} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
            <button type="button" className="btn-primary btn-xs" onClick={() => { setSecret(null); setShowCreate(true) }} disabled={showCreate}>
              <Plus size={14} /> Create API key
            </button>
          </div>
        </div>
        {loading ? <Loader label="Loading API keys…" /> : keys.length === 0 ? (
          <EmptyState icon={KeyRound} title="No API keys yet" hint="Create a sandbox key to test the risk-scoring integration." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="border-b border-line bg-canvas">
                <tr>
                  <th className="th">Name</th>
                  <th className="th">Mode</th>
                  <th className="th">Key prefix</th>
                  <th className="th">Created</th>
                  <th className="th">Status</th>
                  <th className="th text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id} className="border-b border-line last:border-0 hover:bg-canvas">
                    <td className="td font-medium">{key.name}</td>
                    <td className="td"><EnvironmentBadge environment={key.environment} /></td>
                    <td className="td"><code className="font-mono text-[12px] text-muted">{key.key_prefix}…</code></td>
                    <td className="td text-muted">{fmtDate(key.created_at)}</td>
                    <td className="td"><KeyStatus revokedAt={key.revoked_at} /></td>
                    <td className="td text-right">
                      {key.revoked_at ? <span className="text-xs text-faint">Unavailable</span> : (
                        <button type="button" className="btn-danger btn-xs" onClick={() => revoke(key)} disabled={revokingId === key.id}>
                          {revokingId === key.id ? <Spinner size={13} /> : 'Revoke'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

function WebhooksPanel() {
  const [hooks, setHooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [secret, setSecret] = useState(null)
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [deliveries, setDeliveries] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.webhooks()
      setHooks(result.webhooks || [])
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load webhooks')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const loadDeliveries = async (id) => {
    try {
      const result = await api.webhookDeliveries(id)
      setDeliveries(result.deliveries || [])
    } catch (e) {
      setError(e.message || 'Failed to load deliveries')
    }
  }

  const create = async (payload) => {
    setCreating(true)
    try {
      const created = await api.createWebhook(payload)
      setSecret({ signing_secret: created.signing_secret })
      setShowCreate(false)
      await load()
    } catch (e) {
      setError(e.message || 'Failed to create webhook')
    } finally {
      setCreating(false)
    }
  }

  const run = async (id, fn) => {
    setBusyId(id)
    try {
      const result = await fn()
      if (result?.signing_secret) setSecret({ signing_secret: result.signing_secret })
      await load()
      if (openId === id) await loadDeliveries(id)
    } catch (e) {
      setError(e.message || 'Webhook action failed')
    } finally {
      setBusyId(null)
    }
  }

  const toggleHistory = async (id) => {
    if (openId === id) {
      setOpenId(null)
      setDeliveries([])
      return
    }
    setOpenId(id)
    await loadDeliveries(id)
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-signal/30 bg-signal-soft px-4 py-3 text-sm text-signal-deep">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" /> <span>{error}</span>
        </div>
      )}
      {secret && <SecretNotice secret={secret} onDismiss={() => setSecret(null)} />}
      {showCreate && <CreateWebhookForm onCreate={create} creating={creating} onCancel={() => setShowCreate(false)} />}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <SectionHeader title="Webhooks" subtitle="Signed risk-decision events for this organization" icon={Webhook} />
          <div className="flex gap-2">
            <button type="button" className="btn-secondary btn-xs" onClick={load} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
            <button type="button" className="btn-primary btn-xs" onClick={() => { setSecret(null); setShowCreate(true) }} disabled={showCreate}>
              <Plus size={14} /> Add webhook
            </button>
          </div>
        </div>
        {loading ? <Loader label="Loading webhooks…" /> : hooks.length === 0 ? (
          <EmptyState icon={Webhook} title="No webhooks yet" hint="Add an HTTPS endpoint to receive risk.decision.created events." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="border-b border-line bg-canvas">
                <tr>
                  <th className="th">Name</th>
                  <th className="th">URL</th>
                  <th className="th">Status</th>
                  <th className="th text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {hooks.map((hook) => (
                  <Fragment key={hook.id}>
                    <tr className="border-b border-line last:border-0 hover:bg-canvas">
                      <td className="td font-medium">{hook.name}</td>
                      <td className="td"><code className="break-all font-mono text-[12px] text-muted">{hook.url}</code></td>
                      <td className="td">
                        {hook.enabled ? (
                          <span className="pill bg-trust-soft px-2 py-0.5 text-[11px] text-trust-deep">
                            <span className="h-1.5 w-1.5 rounded-full bg-trust" /> Enabled
                          </span>
                        ) : (
                          <span className="pill bg-signal-soft px-2 py-0.5 text-[11px] text-signal-deep">
                            <span className="h-1.5 w-1.5 rounded-full bg-signal" /> Disabled
                          </span>
                        )}
                      </td>
                      <td className="td">
                        <div className="flex flex-wrap justify-end gap-1.5">
                          <button type="button" className="btn-secondary btn-xs" onClick={() => toggleHistory(hook.id)}>
                            {openId === hook.id ? 'Hide deliveries' : 'Deliveries'}
                          </button>
                          <button type="button" className="btn-secondary btn-xs" disabled={busyId === hook.id || !hook.enabled} onClick={() => run(hook.id, () => api.testWebhook(hook.id))}>
                            Send test
                          </button>
                          <button type="button" className="btn-secondary btn-xs" disabled={busyId === hook.id} onClick={() => {
                            if (!window.confirm('Rotate this webhook signing secret? The previous secret stops working immediately.')) return
                            run(hook.id, () => api.rotateWebhookSecret(hook.id))
                          }}>
                            Rotate secret
                          </button>
                          {hook.enabled ? (
                            <button type="button" className="btn-danger btn-xs" disabled={busyId === hook.id} onClick={() => run(hook.id, () => api.disableWebhook(hook.id))}>
                              Disable
                            </button>
                          ) : (
                            <button type="button" className="btn-secondary btn-xs" disabled={busyId === hook.id} onClick={() => run(hook.id, () => api.enableWebhook(hook.id))}>
                              Enable
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {openId === hook.id && (
                      <tr className="border-b border-line bg-canvas">
                        <td className="td" colSpan={4}>
                          {deliveries.length === 0 ? (
                            <p className="text-xs text-muted">No deliveries yet.</p>
                          ) : (
                            <table className="w-full">
                              <thead>
                                <tr>
                                  <th className="th">Event</th>
                                  <th className="th">Status</th>
                                  <th className="th">Attempts</th>
                                  <th className="th">HTTP</th>
                                  <th className="th">Error</th>
                                </tr>
                              </thead>
                              <tbody>
                                {deliveries.map((d) => (
                                  <tr key={d.id}>
                                    <td className="td font-mono text-[12px]">{d.event_type}<div className="text-[11px] text-faint">{d.event_id}</div></td>
                                    <td className="td">{d.status}</td>
                                    <td className="td">{d.attempts}</td>
                                    <td className="td">{d.response_status ?? '—'}</td>
                                    <td className="td text-xs text-muted">{d.last_error || '—'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

export default function Developer() {
  return (
    <div>
      <PageHeader
        title="Developer"
        subtitle="Create and manage server-side credentials and webhooks for the RakshaAI Risk API"
      />

      <div className="space-y-6 py-6">
        <ApiKeysPanel />
        <WebhooksPanel />

        <Card className="p-5">
          <SectionHeader title="Integrate the Risk API & Webhooks" subtitle="Send transactions from your merchant backend — receive real-time signed risk notifications" icon={Code2} />
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted mb-2">Ingestion Endpoint</h4>
              <div className="overflow-x-auto rounded-md border border-line bg-ink-900 p-4 font-mono text-[12px] leading-6 text-white/85">
                <div><span className="text-trust">POST</span> /api/v1/risk/score</div>
                <div><span className="text-white/45">X-API-Key:</span> &lt;your API key&gt;</div>
              </div>
            </div>
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted mb-2">Webhook Signature Verification</h4>
              <div className="overflow-x-auto rounded-md border border-line bg-ink-900 p-4 font-mono text-[12px] leading-6 text-white/85">
                <div><span className="text-white/45">Header:</span> X-RakshaAI-Signature</div>
                <div><span className="text-white/45">HMAC-SHA256:</span> hex(hmac(secret, body))</div>
              </div>
            </div>
          </div>
          <p className="mt-3 text-xs text-muted">Keep API keys and webhook signing secrets in your server-side secret manager. Do not embed them in client applications or version control.</p>
        </Card>
      </div>
    </div>
  )
}
