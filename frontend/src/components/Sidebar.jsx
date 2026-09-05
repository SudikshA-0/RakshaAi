import {
  LayoutDashboard,
  Radio,
  ClipboardList,
  Sparkles,
  Brain,
  SlidersHorizontal,
  KeyRound,
  Shield,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Building2,
} from 'lucide-react'

export const NAV = [
  { id: 'dashboard', label: 'Command Center', icon: LayoutDashboard },
  { id: 'transactions', label: 'Live Transactions', icon: Radio },
  { id: 'cases', label: 'Case Queue', icon: ClipboardList },
  { id: 'ai-analyst', label: 'AI Analyst', icon: Sparkles },
  { id: 'model', label: 'Model Performance', icon: Brain },
  { id: 'policy', label: 'Risk Policy', icon: SlidersHorizontal },
  { id: 'developer', label: 'Developer', icon: KeyRound },
]

const SECTIONS = [
  { title: 'Monitor', ids: ['dashboard', 'transactions'] },
  { title: 'Investigate', ids: ['cases', 'ai-analyst'] },
  { title: 'System', ids: ['model', 'policy', 'developer'] },
]

const byId = Object.fromEntries(NAV.map((n) => [n.id, n]))

function Tip({ label, show }) {
  if (!show) return null
  return (
    <span
      role="tooltip"
      className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 hidden -translate-y-1/2 whitespace-nowrap rounded-md border border-line bg-paper px-2 py-1 text-[12px] font-medium text-ink shadow-menu group-hover:block"
    >
      {label}
    </span>
  )
}

export default function Sidebar({ active, onNavigate, health, pending = 0, collapsed, onToggle, org, user, onLogout }) {
  const online = !!health
  const statusLabel = online ? 'Scoring engine online' : 'Engine offline'
  const orgName = org?.name || 'Organization'
  const initial = (orgName.trim()[0] || 'R').toUpperCase()

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-ink-900 text-white transition-[width] duration-200 ease-out ${
        collapsed ? 'w-[72px] overflow-visible' : 'w-60'
      }`}
    >
      {/* brand */}
      <div className={`flex items-center pb-5 pt-6 ${collapsed ? 'flex-col gap-3 px-0' : 'gap-2.5 px-5'}`}>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-trust text-ink-900">
          <Shield size={18} strokeWidth={2.4} />
        </span>
        {!collapsed && (
          <div className="min-w-0 flex-1 leading-none">
            <div className="text-[14.5px] font-semibold tracking-tight text-white">RakshaAI</div>
            <div className="mt-1 text-[10.5px] font-medium uppercase tracking-[0.14em] text-white/40">
              Risk Console
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          className={`grid h-7 w-7 shrink-0 place-items-center rounded-md text-white/45 transition-colors hover:bg-white/[0.06] hover:text-white/85 ${
            collapsed ? '' : 'ml-auto'
          }`}
        >
          {collapsed ? <ChevronRight size={16} strokeWidth={2} /> : <ChevronLeft size={16} strokeWidth={2} />}
        </button>
      </div>

      {/* nav */}
      <nav className={`flex-1 pb-4 ${collapsed ? 'overflow-visible px-2' : 'overflow-y-auto px-3'}`}>
        {SECTIONS.map((sec) => (
          <div key={sec.title} className="mb-5">
            {!collapsed && (
              <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-white/30">
                {sec.title}
              </div>
            )}
            <div className="space-y-0.5">
              {sec.ids.map((id) => {
                const item = byId[id]
                const Icon = item.icon
                const isActive = active === id
                return (
                  <button
                    key={id}
                    onClick={() => onNavigate(id)}
                    title={collapsed ? item.label : undefined}
                    className={`group relative flex items-center rounded-md text-[13px] font-medium transition-colors ${
                      collapsed
                        ? 'h-10 w-full justify-center px-0'
                        : 'w-full gap-3 px-3 py-2'
                    } ${
                      isActive ? 'bg-white/[0.07] text-white' : 'text-white/55 hover:bg-white/[0.04] hover:text-white/90'
                    }`}
                  >
                    {isActive && (
                      <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-trust" />
                    )}
                    <span className="relative">
                      <Icon
                        size={17}
                        strokeWidth={2}
                        className={isActive ? 'text-trust' : 'text-white/45 group-hover:text-white/70'}
                      />
                      {collapsed && id === 'cases' && pending > 0 && (
                        <span className="absolute -right-2 -top-1.5 tnum min-w-[16px] rounded-full bg-signal px-1 text-center text-[9px] font-semibold leading-[16px] text-white">
                          {pending > 9 ? '9+' : pending}
                        </span>
                      )}
                    </span>
                    {!collapsed && <span className="flex-1 text-left">{item.label}</span>}
                    {!collapsed && id === 'cases' && pending > 0 && (
                      <span className="tnum min-w-[20px] rounded-full bg-signal px-1.5 py-0.5 text-center text-[10.5px] font-semibold text-white">
                        {pending}
                      </span>
                    )}
                    <Tip label={item.label} show={collapsed} />
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* account / tenant */}
      <div className={`border-t border-white/[0.08] py-3 ${collapsed ? 'px-2' : 'px-3'}`}>
        {collapsed ? (
          <div className="flex flex-col items-center gap-2">
            <span
              className="group relative grid h-8 w-8 place-items-center rounded-md bg-trust text-[13px] font-semibold text-ink-900"
              title={orgName}
            >
              {initial}
              <Tip label={orgName} show />
            </span>
            <button
              type="button"
              onClick={onLogout}
              aria-label="Sign out"
              className="group relative grid h-8 w-8 place-items-center rounded-md text-white/45 transition-colors hover:bg-white/[0.06] hover:text-white/85"
            >
              <LogOut size={15} strokeWidth={2} />
              <Tip label="Sign out" show />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-trust text-[13px] font-semibold text-ink-900">
              {initial}
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="flex items-center gap-1 truncate text-[12.5px] font-semibold text-white">
                <Building2 size={11} strokeWidth={2} className="shrink-0 text-white/40" />
                <span className="truncate">{orgName}</span>
              </div>
              {user?.email && <div className="truncate text-[10.5px] text-white/40">{user.email}</div>}
            </div>
            <button
              type="button"
              onClick={onLogout}
              aria-label="Sign out"
              title="Sign out"
              className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-white/45 transition-colors hover:bg-white/[0.06] hover:text-white/85"
            >
              <LogOut size={15} strokeWidth={2} />
            </button>
          </div>
        )}
      </div>

      {/* footer / status */}
      <div className={`border-t border-white/[0.08] py-3.5 ${collapsed ? 'px-0' : 'px-4'}`}>
        <div className={`group relative flex items-center ${collapsed ? 'justify-center' : 'gap-2'}`}>
          <span className="relative flex h-2 w-2" title={collapsed ? statusLabel : undefined}>
            {online && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-trust opacity-60" />
            )}
            <span
              className="relative inline-flex h-2 w-2 rounded-full"
              style={{ backgroundColor: online ? '#00B7CD' : '#DF301C' }}
            />
          </span>
          {!collapsed && <span className="text-[12px] font-medium text-white/70">{statusLabel}</span>}
          <Tip label={statusLabel} show={collapsed} />
        </div>
        {!collapsed && (
          <div className="mt-2 flex items-center gap-1.5 text-[10.5px] text-white/35">
            <Shield size={11} strokeWidth={2} />
            Defensive-only · monitors &amp; blocks
          </div>
        )}
      </div>
    </aside>
  )
}
