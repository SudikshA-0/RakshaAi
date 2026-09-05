// Full-screen authentication gate: sign in to an existing merchant, or create
// a new merchant organization. Shown by App whenever there is no valid session.
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Shield, LogIn, UserPlus, AlertCircle } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { Spinner } from './primitives'

const DEMO = { email: 'demo@rakshaai.io', password: 'demo12345' }

export default function AuthScreen() {
  const { login, signup } = useAuth()
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [form, setForm] = useState({ email: '', password: '', org_name: '', name: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isSignup = mode === 'signup'
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const friendlyError = (raw) => {
    const msg = String(raw?.message || raw || '')
    // Surface the backend detail if present, else a clean fallback.
    const m = msg.match(/^\d+:\s*(.*)$/)
    if (m) {
      try {
        const body = JSON.parse(m[1])
        if (body?.detail) return typeof body.detail === 'string' ? body.detail : 'Please check your input.'
      } catch {
        /* not JSON */
      }
    }
    if (msg.startsWith('401')) return 'Invalid email or password.'
    if (msg.startsWith('409')) return 'An account with this email already exists.'
    if (msg.startsWith('422')) return 'Please check your input and try again.'
    return 'Something went wrong. Please try again.'
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (isSignup) {
        await signup({
          email: form.email.trim(),
          password: form.password,
          org_name: form.org_name.trim(),
          name: form.name.trim(),
        })
      } else {
        await login({ email: form.email.trim(), password: form.password })
      }
      // On success the AuthProvider flips to authenticated and App swaps views.
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  const switchMode = () => {
    setMode((m) => (m === 'login' ? 'signup' : 'login'))
    setError('')
  }

  const fillDemo = () => {
    setMode('login')
    setForm((f) => ({ ...f, email: DEMO.email, password: DEMO.password }))
    setError('')
  }

  return (
    <div className="grid min-h-screen place-items-center bg-canvas px-4">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="w-full max-w-[400px]"
      >
        {/* brand */}
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-ink-900 text-trust">
            <Shield size={22} strokeWidth={2.4} />
          </span>
          <h1 className="mt-3 text-[19px] font-semibold tracking-tight text-ink">RakshaAI</h1>
          <p className="mt-1 text-[12.5px] text-muted">Merchant Risk Command Center</p>
        </div>

        <div className="card p-6">
          <h2 className="text-[15px] font-semibold text-ink">
            {isSignup ? 'Create your merchant account' : 'Sign in to your console'}
          </h2>
          <p className="mt-1 text-[12.5px] text-muted">
            {isSignup
              ? 'Spin up a new organization with its own isolated risk data.'
              : 'Enter your credentials to access your risk dashboard.'}
          </p>

          <form onSubmit={submit} className="mt-5 space-y-3.5">
            {isSignup && (
              <Field label="Organization name">
                <input
                  className="input"
                  placeholder="Acme Payments"
                  value={form.org_name}
                  onChange={set('org_name')}
                  required
                  minLength={2}
                  autoComplete="organization"
                />
              </Field>
            )}
            {isSignup && (
              <Field label="Your name" optional>
                <input
                  className="input"
                  placeholder="Jordan Lee"
                  value={form.name}
                  onChange={set('name')}
                  autoComplete="name"
                />
              </Field>
            )}
            <Field label="Email">
              <input
                type="email"
                className="input"
                placeholder="you@company.com"
                value={form.email}
                onChange={set('email')}
                required
                autoComplete="email"
              />
            </Field>
            <Field label="Password" hint={isSignup ? 'At least 8 characters' : undefined}>
              <input
                type="password"
                className="input"
                placeholder="••••••••"
                value={form.password}
                onChange={set('password')}
                required
                minLength={isSignup ? 8 : 1}
                autoComplete={isSignup ? 'new-password' : 'current-password'}
              />
            </Field>

            {error && (
              <div className="flex items-start gap-2 rounded-md border border-signal/25 bg-signal/5 px-3 py-2 text-[12.5px] text-signal-deep">
                <AlertCircle size={15} strokeWidth={2} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={busy}>
              {busy ? (
                <Spinner size={15} />
              ) : isSignup ? (
                <>
                  <UserPlus size={15} strokeWidth={2.2} /> Create account
                </>
              ) : (
                <>
                  <LogIn size={15} strokeWidth={2.2} /> Sign in
                </>
              )}
            </button>
          </form>

          <div className="mt-4 border-t border-line pt-4 text-center text-[12.5px] text-muted">
            {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button type="button" onClick={switchMode} className="font-semibold text-trust hover:underline">
              {isSignup ? 'Sign in' : 'Create one'}
            </button>
          </div>
        </div>

        <button
          type="button"
          onClick={fillDemo}
          className="mt-4 w-full text-center text-[12px] text-faint transition-colors hover:text-muted"
        >
          Use demo credentials
        </button>
      </motion.div>
    </div>
  )
}

function Field({ label, hint, optional, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center justify-between">
        <span className="text-[12px] font-semibold text-ink">{label}</span>
        {optional && <span className="text-[11px] text-faint">optional</span>}
        {hint && <span className="text-[11px] text-faint">{hint}</span>}
      </span>
      {children}
    </label>
  )
}
