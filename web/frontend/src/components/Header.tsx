import { useEffect, useRef, useState } from 'react'

interface Props {
  connected: boolean
  sidebarOpen: boolean
  onToggleSidebar: () => void
  activeTab: string
  onTabChange: (tab: 'test' | 'results' | 'reports') => void
  authUser?: string
  onLogout?: () => void
}

const TABS = [
  { id: 'test' as const, label: 'Test' },
  { id: 'reports' as const, label: 'Reports' },
] as const

export function Header({ connected, sidebarOpen, onToggleSidebar, activeTab, onTabChange, authUser, onLogout }: Props) {
  const navRef = useRef<HTMLElement | null>(null)
  const tabRefs = useRef<Array<HTMLSpanElement | null>>([])
  const [indicator, setIndicator] = useState({ left: 0, width: 0, opacity: 0 })

  useEffect(() => {
    const updateIndicator = () => {
      const activeIndex = TABS.findIndex(tab => tab.id === activeTab)
      const nav = navRef.current
      const activeEl = tabRefs.current[activeIndex]
      if (!nav || !activeEl) return

      const navRect = nav.getBoundingClientRect()
      const activeRect = activeEl.getBoundingClientRect()
      setIndicator({
        left: activeRect.left - navRect.left,
        width: activeRect.width,
        opacity: 1,
      })
    }

    updateIndicator()

    const nav = navRef.current
    if (!nav) return

    const observer = new ResizeObserver(updateIndicator)
    observer.observe(nav)

    return () => observer.disconnect()
  }, [activeTab])

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

      <nav ref={navRef} className="relative flex gap-1 ml-4 self-stretch">
        {TABS.map((tab, index) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`h-full px-1 transition-colors ${
              activeTab === tab.id ? 'text-fg' : 'text-fg-3 hover:text-fg'
            }`}
          >
            <span
              ref={el => { tabRefs.current[index] = el }}
              className="inline-flex h-full items-center px-4 pt-0.5 text-[14px] font-semibold"
            >
              {tab.label}
            </span>
          </button>
        ))}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-0 h-0.5 rounded-full bg-tab-active transition-[transform,width,opacity] duration-200 ease-out"
          style={{
            width: `${indicator.width}px`,
            transform: `translateX(${indicator.left}px)`,
            opacity: indicator.opacity,
          }}
        />
      </nav>

      <div className="flex-1" />

      {authUser && onLogout && (
        <>
          <span className="text-[11px] text-fg-3 mr-1">{authUser}</span>
          <button onClick={onLogout} className="btn btn-sm">
            Sign out
          </button>
        </>
      )}

      <span className={`w-2 h-2 rounded-full ${connected ? 'bg-ok' : 'bg-err'}`} />
      <span className="text-[11px] text-fg-3">
        {connected ? 'Connected' : 'Disconnected'}
      </span>
    </header>
  )
}
