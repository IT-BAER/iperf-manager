interface Props {
  connected: boolean
  sidebarOpen: boolean
  onToggleSidebar: () => void
  activeTab: string
  onTabChange: (tab: 'test' | 'results' | 'reports') => void
}

const TABS = [
  { id: 'test' as const, label: 'Test' },
  { id: 'reports' as const, label: 'Reports' },
] as const

export function Header({ connected, sidebarOpen, onToggleSidebar, activeTab, onTabChange }: Props) {
  return (
    <header className="h-11 shrink-0 border-b border-line bg-surface flex items-center px-3 gap-3">
      <button
        onClick={onToggleSidebar}
        className="btn btn-sm w-7 px-0 justify-center text-xs"
        aria-label="Toggle sidebar"
      >
        <i className={`fa-solid ${sidebarOpen ? 'fa-chevron-left' : 'fa-chevron-right'} text-[10px]`} />
      </button>

      <h1 className="text-sm font-semibold text-fg tracking-tight select-none">
        iperf-manager
      </h1>

      <nav className="flex gap-1 ml-4">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
              activeTab === tab.id
                ? 'bg-accent/15 text-accent'
                : 'text-fg-3 hover:text-fg hover:bg-surface-hover'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="flex-1" />

      <span className={`w-2 h-2 rounded-full ${connected ? 'bg-ok' : 'bg-err'}`} />
      <span className="text-[11px] text-fg-3">
        {connected ? 'Connected' : 'Disconnected'}
      </span>
    </header>
  )
}
