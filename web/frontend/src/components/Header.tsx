import type { TestState } from '../types'

type View = 'dashboard' | 'reports'

interface Props {
  view: View
  onViewChange: (v: View) => void
  sidebarOpen: boolean
  onToggleSidebar: () => void
  testState: TestState
}

export function Header({ view, onViewChange, sidebarOpen, onToggleSidebar, testState }: Props) {
  return (
    <header className="h-[52px] flex items-center gap-3 px-4 border-b border-line bg-surface shrink-0">
      <button
        onClick={onToggleSidebar}
        className="btn btn-sm w-7 px-0 justify-center"
        aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          {sidebarOpen ? (
            <path d="M3 4h10M3 8h10M3 12h10" strokeLinecap="round" />
          ) : (
            <path d="M3 4h10M3 8h6M3 12h10" strokeLinecap="round" />
          )}
        </svg>
      </button>

      <div className="flex items-center gap-2 mr-4">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-sm font-semibold tracking-tight">iperf-manager</span>
      </div>

      <nav className="flex gap-0.5" role="tablist">
        {(['dashboard', 'reports'] as const).map(tab => (
          <button
            key={tab}
            role="tab"
            aria-selected={view === tab}
            onClick={() => onViewChange(tab)}
            className={`h-8 px-3 text-[13px] rounded-sm transition-colors duration-150
              ${view === tab
                ? 'bg-surface-active text-fg font-medium'
                : 'text-fg-3 hover:text-fg-2 hover:bg-surface-hover'}`}
          >
            {tab === 'dashboard' ? 'Dashboard' : 'Reports'}
          </button>
        ))}
      </nav>

      <div className="flex-1" />

      {testState.status === 'running' && (
        <div className="flex items-center gap-2 text-[13px]">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ok opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-ok" />
          </span>
          <span className="text-ok tabular">Test running</span>
        </div>
      )}
      {testState.status === 'stopping' && (
        <span className="text-[13px] text-warn">Stopping…</span>
      )}
    </header>
  )
}