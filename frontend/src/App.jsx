import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import Sidebar from './components/Sidebar'
import AuthScreen from './components/AuthScreen'
import Dashboard from './views/Dashboard'
import Transactions from './views/Transactions'
import Cases from './views/Cases'
import ModelPerformance from './views/ModelPerformance'
import Policy from './views/Policy'
import Developer from './views/Developer'
import AIAnalyst from './views/AIAnalyst'
import { Loader } from './components/primitives'
import { useAuth } from './lib/auth'
import { api } from './lib/api'

const SIDEBAR_KEY = 'rakshaai.sidebarCollapsed'

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

export default function App() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-canvas">
        <Loader label="Restoring your session…" />
      </div>
    )
  }
  if (!isAuthenticated) return <AuthScreen />
  return <Console />
}

function Console() {
  const { user, org, logout } = useAuth()
  const [view, setView] = useState('dashboard')
  const [health, setHealth] = useState(true)
  const [pending, setPending] = useState(0)
  const [collapsed, setCollapsed] = useState(readCollapsed)

  const onHealth = useCallback((h) => setHealth(h), [])
  const onPending = useCallback((p) => setPending(p), [])
  const onToggleSidebar = useCallback(() => {
    setCollapsed((c) => {
      const next = !c
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0')
      } catch {
        /* ignore quota / private mode */
      }
      return next
    })
  }, [])

  useEffect(() => {
    let alive = true
    const check = () =>
      api
        .health()
        .then(() => alive && setHealth(true))
        .catch(() => alive && setHealth(false))
    check()
    const id = setInterval(check, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const views = {
    dashboard: <Dashboard onHealth={onHealth} onPending={onPending} />,
    transactions: <Transactions />,
    cases: <Cases onPending={onPending} />,
    'ai-analyst': <AIAnalyst />,
    model: <ModelPerformance />,
    policy: <Policy />,
    developer: <Developer />,
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas">
      <Sidebar
        active={view}
        onNavigate={setView}
        health={health}
        pending={pending}
        collapsed={collapsed}
        onToggle={onToggleSidebar}
        org={org}
        user={user}
        onLogout={logout}
      />
      <main className={`min-h-screen transition-[padding] duration-200 ease-out ${collapsed ? 'pl-[72px]' : 'pl-60'}`}>
        <div className="mx-auto max-w-[1440px] px-6 lg:px-8">
          {/* opacity-only transition: a transform here would create a containing block
              and break the sticky PageHeader inside each view */}
          <motion.div key={view} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
            {views[view]}
          </motion.div>
        </div>
      </main>
    </div>
  )
}
