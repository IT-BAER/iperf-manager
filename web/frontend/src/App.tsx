import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { useSocket } from './hooks/useSocket'
import { api } from './api'
import type { Agent, AuthSession, TestState, TestConfig, Metrics, LogEntry, Profile } from './types'

import { AuthPanel } from './components/AuthPanel'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { KPIBar } from './components/KPIBar'
import TestConfigPanel from './components/TestConfig'
import LiveResults from './components/LiveResults'
import { LogPanel } from './components/LogPanel'
import ReportViewer from './components/ReportViewer'
import { Toast } from './components/Toast'

interface MetricPoint { ts: number; up: number; dn: number }

interface ReportFile {
  name: string
  size: number
  modified: number
  protocol?: string | null
  server?: string | null
  clients?: string[]
  duration_s?: number | null
  rows?: number
  peak_up?: number | null
  peak_dn?: number | null
}

function fmtDuration(s: number | null | undefined): string {
  if (!s) return '—'
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function fmtMbps(mbps: number | null | undefined): string {
  if (mbps == null) return '—'
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  return `${mbps.toFixed(1)} Mbps`
}

function fmtDateTime(name: string): string {
  // test_20260318_095111.csv → 2026-03-18 09:51:11
  const m = name.match(/test_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/)
  if (!m) return name
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}`
}

function ReportList({ onSelect }: { onSelect: (name: string) => void }) {
  const [files, setFiles] = useState<ReportFile[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(() => {
    api<ReportFile[]>('/api/reports').then(d => {
      if (d) setFiles(d)
    })
  }, [])

  useEffect(() => { load() }, [load])

  const toggleSelect = (name: string, e: ReactMouseEvent) => {
    e.stopPropagation()
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
      } else {
        next.add(name)
      }
      return next
    })
  }

  const toggleAll = () => {
    setSelected(prev => prev.size === files.length ? new Set() : new Set(files.map(f => f.name)))
  }

  const deleteSelected = async () => {
    if (selected.size === 0) return
    setDeleting(true)
    try {
      const data = await api<{ deleted: string[] }>('/api/reports', {
        method: 'DELETE',
        body: JSON.stringify({ files: [...selected] }),
      })
      if (!data) return
      window.dispatchEvent(new CustomEvent('toast', { detail: { msg: `Deleted ${selected.size} report${selected.size > 1 ? 's' : ''}`, type: 'ok' } }))
      setSelected(new Set())
      load()
    } finally {
      setDeleting(false)
    }
  }

  const deleteSingle = async (name: string, e: ReactMouseEvent) => {
    e.stopPropagation()
    const data = await api<{ deleted: string }>(`/api/reports/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (!data) return
    window.dispatchEvent(new CustomEvent('toast', { detail: { msg: `Deleted ${name}`, type: 'ok' } }))
    setFiles(prev => prev.filter(f => f.name !== name))
    setSelected(prev => { const s = new Set(prev); s.delete(name); return s })
  }

  if (files.length === 0) {
    return <div className="panel p-6 text-center text-fg-3 text-sm">No reports yet. Run a test first.</div>
  }

  const allSelected = selected.size === files.length && files.length > 0
  const someSelected = selected.size > 0

  return (
    <div className="panel">
      <div className="px-4 py-3 border-b border-line flex items-center gap-3">
        <h3 className="text-sm font-semibold flex-1">Reports <span className="text-fg-3 font-normal">({files.length})</span></h3>
        {someSelected && (
          <button
            className="btn btn-danger"
            disabled={deleting}
            onClick={deleteSelected}
          >
            <i className="fa-solid fa-trash-can text-[11px]" />
            {deleting ? 'Deleting…' : `Delete selected (${selected.size})`}
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-line text-fg-3 text-left">
              <th className="pl-3 pr-1 py-2 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="accent-accent cursor-pointer w-3.5 h-3.5"
                />
              </th>
              <th className="px-3 py-2 font-medium">Date / Time</th>
              <th className="px-3 py-2 font-medium">Protocol</th>
              <th className="px-3 py-2 font-medium">Server</th>
              <th className="px-3 py-2 font-medium">Clients</th>
              <th className="px-3 py-2 font-medium">Duration</th>
              <th className="px-3 py-2 font-medium">Peak ↑</th>
              <th className="px-3 py-2 font-medium">Peak ↓</th>
              <th className="px-3 py-2 font-medium text-right">Size</th>
              <th className="px-2 py-2 w-8"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {files.map(f => (
              <tr
                key={f.name}
                className={`hover:bg-surface-hover transition-colors cursor-pointer ${selected.has(f.name) ? 'bg-surface-raised' : ''}`}
                onClick={() => onSelect(f.name)}
              >
                <td className="pl-3 pr-1 py-2.5" onClick={e => toggleSelect(f.name, e)}>
                  <input
                    type="checkbox"
                    checked={selected.has(f.name)}
                    onChange={() => {}}
                    className="accent-accent cursor-pointer w-3.5 h-3.5"
                  />
                </td>
                <td className="px-3 py-2.5 font-mono whitespace-nowrap">{fmtDateTime(f.name)}</td>
                <td className="px-3 py-2.5">
                  {f.protocol
                    ? <span className="px-1.5 py-0.5 rounded text-[11px] font-medium bg-surface-raised border border-line">{f.protocol}</span>
                    : <span className="text-fg-3">—</span>
                  }
                </td>
                <td className="px-3 py-2.5">
                  {f.server
                    ? <span className="text-fg-2">{f.server}</span>
                    : <span className="text-fg-3">—</span>
                  }
                </td>
                <td className="px-3 py-2.5 max-w-[180px]">
                  {f.clients && f.clients.length > 0
                    ? <span className="text-fg-2">{f.clients.join(', ')}</span>
                    : <span className="text-fg-3">—</span>
                  }
                </td>
                <td className="px-3 py-2.5 tabular-nums">{fmtDuration(f.duration_s)}</td>
                <td className="px-3 py-2.5 tabular-nums text-ok">{fmtMbps(f.peak_up)}</td>
                <td className="px-3 py-2.5 tabular-nums text-accent">{fmtMbps(f.peak_dn)}</td>
                <td className="px-3 py-2.5 text-right text-fg-3 tabular-nums">{(f.size / 1024).toFixed(1)} KB</td>
                <td className="px-2 py-2.5" onClick={e => e.stopPropagation()}>
                  <button
                    className="w-6 h-6 flex items-center justify-center rounded hover:bg-err-subtle hover:text-err text-fg-3 transition-colors"
                    title="Delete"
                    onClick={e => deleteSingle(f.name, e)}
                  >
                    <i className="fa-solid fa-trash-can text-[11px]" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

type Tab = 'test' | 'results' | 'reports'

export function App() {
  const didInitializeAgents = useRef(false)
  const profileLoadSeq = useRef(0)

  // ── State ─────────────────────────────────────────────────────
  const [auth, setAuth] = useState<AuthSession | null>(null)
  const [authBusy, setAuthBusy] = useState(false)
  const [agents, setAgents] = useState<Agent[]>([])
  const [testState, setTestState] = useState<TestState>({ status: 'idle' })
  const [latestMetrics, setLatestMetrics] = useState<Metrics | null>(null)
  const [metricsHistory, setMetricsHistory] = useState<MetricPoint[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('test')
  const [selectedReport, setSelectedReport] = useState<string | null>(null)
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [activeProfile, setActiveProfile] = useState('')
  const [draftConfig, setDraftConfig] = useState<TestConfig | null>(null)

  const authEnabled = auth?.enabled ?? false
  const isAuthenticated = auth ? (!auth.enabled || auth.authenticated) : false
  const { on, connected } = useSocket(auth !== null && isAuthenticated)

  const agentsMap = useMemo(() => {
    const m: Record<string, Agent> = {}
    agents.forEach(a => { m[a.id] = a })
    return m
  }, [agents])

  const resetRuntimeState = useCallback(() => {
    setAgents([])
    setTestState({ status: 'idle' })
    setLatestMetrics(null)
    setMetricsHistory([])
    setLogs([])
    setSelectedReport(null)
    setProfiles([])
    setActiveProfile('')
    setDraftConfig(null)
  }, [])

  const loadAuth = useCallback(async () => {
    const data = await api<AuthSession>('/api/auth/session', { onUnauthorized: 'error' })
    if (data) setAuth(data)
  }, [])

  // ── Socket.IO listeners ───────────────────────────────────────
  useEffect(() => {
    const unsubs = [
      on('status', (data: unknown) => {
        const d = data as { test: TestState }
        if (d?.test) setTestState(d.test)
      }),
      on('metrics', (data: unknown) => {
        const m = data as Metrics
        setLatestMetrics(m)
        setMetricsHistory(prev => {
          const next = [...prev, { ts: m.timestamp, up: m.total_up, dn: m.total_dn }]
          return next.length > 300 ? next.slice(-300) : next
        })
      }),
      on('test_started', (data: unknown) => {
        const d = data as { config?: TestConfig; ts: number }
        setTestState({ status: 'running', started_at: d.ts, config: d.config })
        setLatestMetrics(null)
        setMetricsHistory([])
        setLogs([])
      }),
      on('test_completed', (data: unknown) => {
        const d = data as { ts?: number }
        setTestState(prev => ({ ...prev, status: 'idle', finished_at: d?.ts ?? Date.now() / 1000 }))
      }),
      on('test_error', (data: unknown) => {
        const d = data as { message: string; ts: number }
        setLogs(prev => [...prev, { ts: d.ts * 1000, msg: d.message, type: 'err' }])
      }),
      on('test_log', (data: unknown) => {
        const d = data as { message: string; ts: number }
        setLogs(prev => {
          const next = [...prev, { ts: (d.ts ?? Date.now() / 1000) * 1000, msg: d.message, type: '' as const }]
          return next.length > 500 ? next.slice(-500) : next
        })
      }),
      on('agents_update', (data: unknown) => {
        setAgents(data as Agent[])
      }),
    ]
    return () => { unsubs.forEach(fn => fn?.()) }
  }, [on])

  // ── Agent CRUD ────────────────────────────────────────────────
  const toast = useCallback((msg: string, type: 'info' | 'ok' | 'err' = 'info') => {
    window.dispatchEvent(new CustomEvent('toast', { detail: { msg, type } }))
  }, [])

  useEffect(() => {
    void loadAuth()
  }, [loadAuth])

  useEffect(() => {
    const handleAuthRequired = () => {
      resetRuntimeState()
      didInitializeAgents.current = false
      setAuth(prev => prev ? { ...prev, authenticated: false, username: '' } : { enabled: true, authenticated: false, username: '' })
    }

    window.addEventListener('auth-required', handleAuthRequired)
    return () => window.removeEventListener('auth-required', handleAuthRequired)
  }, [resetRuntimeState])

  const login = useCallback(async (username: string, password: string) => {
    setAuthBusy(true)
    try {
      const data = await api<AuthSession>('/api/auth/session', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
        onUnauthorized: 'error',
      })
      if (data) {
        didInitializeAgents.current = false
        setAuth(data)
      }
    } finally {
      setAuthBusy(false)
    }
  }, [])

  const logout = useCallback(async () => {
    await api<AuthSession>('/api/auth/session', { method: 'DELETE', onUnauthorized: 'error' })
    resetRuntimeState()
    didInitializeAgents.current = false
    setAuth(prev => prev ? { ...prev, authenticated: false, username: '' } : prev)
  }, [resetRuntimeState])

  const refreshAgents = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const data = await api<Agent[]>('/api/agents?refresh=1')
      if (data) {
        setAgents(data)
        const online = data.filter(a => a.status === 'online').length
        toast(`${online}/${data.length} agents online`, online === data.length ? 'ok' : 'info')
      }
    } finally {
      setIsRefreshing(false)
    }
  }, [toast])

  const addAgent = useCallback(async (url: string, name: string, apiKey: string) => {
    const data = await api<Agent>('/api/agents', {
      method: 'POST',
      body: JSON.stringify({ url, name, api_key: apiKey }),
    })
    if (data) {
      setAgents(prev => [...prev.filter(a => a.id !== data.id), data])
      toast(`Agent "${data.name}" added`, 'ok')
    }
  }, [toast])

  const updateAgentKey = useCallback(async (id: string, apiKey: string) => {
    const data = await api<Agent>(`/api/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ api_key: apiKey }),
    })
    if (data) {
      setAgents(prev => prev.map(a => (a.id === data.id ? data : a)))
      toast(apiKey ? `Stored API key for "${data.name}"` : `Cleared API key for "${data.name}"`, 'ok')
    }
  }, [toast])

  const removeAgent = useCallback(async (id: string) => {
    await api(`/api/agents/${id}`, { method: 'DELETE' })
    setAgents(prev => prev.filter(a => a.id !== id))
  }, [])

  const discoverAgents = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    setIsDiscovering(true)
    try {
      const before = agents.length
      const data = await api<{ agents: Agent[] }>('/api/agents/discover', { method: 'POST' })
      if (data?.agents) {
        setAgents(prev => {
          const map = new Map(prev.map(a => [a.id, a]))
          data.agents.forEach(a => map.set(a.id, a))
          return Array.from(map.values())
        })
        if (silent) return
        const found = data.agents.length - before
        if (found > 0) {
          toast(`Discovered ${found} new agent${found !== 1 ? 's' : ''}`, 'ok')
        } else if (data.agents.length > 0) {
          toast(`${data.agents.length} agent${data.agents.length !== 1 ? 's' : ''} already known`, 'info')
        } else {
          toast('No agents found on the network', 'info')
        }
      }
    } finally {
      setIsDiscovering(false)
    }
  }, [agents.length, toast])

  // ── Profiles ─────────────────────────────────────────────────-
  const loadProfiles = useCallback(async () => {
    const data = await api<Profile[]>('/api/profiles')
    if (!data) return

    setProfiles(data)
    setActiveProfile(prev => {
      if (!prev) return prev
      return data.some(profile => profile.name === prev) ? prev : ''
    })
  }, [])

  const loadProfileByName = useCallback(async (requestedName: string, showMissingToast = true) => {
    const selectedName = requestedName.trim()
    if (!selectedName) {
      if (showMissingToast) {
        toast('Select a profile first', 'info')
      }
      return
    }

    const loadSeq = ++profileLoadSeq.current
    const data = await api<{ name: string; config: TestConfig }>(`/api/profiles/${encodeURIComponent(selectedName)}`)
    if (!data?.config) return
    if (loadSeq !== profileLoadSeq.current) return

    const profileName = (data.name || selectedName).trim() || selectedName
    window.dispatchEvent(new CustomEvent('load-profile', { detail: data.config }))
    setActiveTab('test')
    setActiveProfile(profileName)
    toast(`Loaded profile "${profileName}"`, 'ok')
  }, [toast])

  const handleProfileChange = useCallback((name: string) => {
    setActiveProfile(name)

    if (!name) {
      profileLoadSeq.current += 1
      return
    }

    void loadProfileByName(name, false)
  }, [loadProfileByName])

  const saveProfile = useCallback(async () => {
    if (!draftConfig) {
      toast('Configure server and clients before saving a profile', 'info')
      return
    }

    const suggestedName = activeProfile || 'profile'
    const entered = window.prompt('Save profile as:', suggestedName)
    if (entered === null) return

    const name = entered.trim()
    if (!name) {
      toast('Profile name is required', 'err')
      return
    }

    const data = await api<{ ok: boolean; name: string }>('/api/profiles', {
      method: 'POST',
      body: JSON.stringify({ name, config: draftConfig }),
    })
    if (!data) return

    const savedName = data.name || name
    await loadProfiles()
    setActiveProfile(savedName)
    toast(`Saved profile "${savedName}"`, 'ok')
  }, [activeProfile, draftConfig, loadProfiles, toast])

  const deleteSelectedProfile = useCallback(async () => {
    if (!activeProfile) {
      toast('Select a profile first', 'info')
      return
    }

    if (!window.confirm(`Delete profile "${activeProfile}"?`)) return

    const deletedName = activeProfile
    const data = await api<{ ok: boolean }>(`/api/profiles/${encodeURIComponent(activeProfile)}`, {
      method: 'DELETE',
    })
    if (!data) return

    setActiveProfile('')
    setProfiles(prev => prev.filter(profile => profile.name !== deletedName))
    toast(`Deleted profile "${deletedName}"`, 'ok')
  }, [activeProfile, toast])

  // ── Test control ──────────────────────────────────────────────
  const startTest = useCallback(async (config: TestConfig) => {
    setLatestMetrics(null)
    setMetricsHistory([])
    setLogs([])
    await api('/api/test/start', { method: 'POST', body: JSON.stringify(config) })
  }, [])

  const stopTest = useCallback(async () => {
    await api('/api/test/stop', { method: 'POST' })
  }, [])

  const clearLogs = useCallback(() => setLogs([]), [])

  // ── Initial load ──────────────────────────────────────────────
  useEffect(() => {
    if (!auth || !isAuthenticated) {
      didInitializeAgents.current = false
      return
    }
    if (didInitializeAgents.current) return
    didInitializeAgents.current = true

    void (async () => {
      await refreshAgents()
      await discoverAgents({ silent: true })
    })()
  }, [auth, discoverAgents, isAuthenticated, refreshAgents])

  useEffect(() => {
    if (!auth || !isAuthenticated) {
      setProfiles([])
      setActiveProfile('')
      return
    }
    void loadProfiles()
  }, [auth, isAuthenticated, loadProfiles])

  if (!auth) {
    return (
      <div className="min-h-screen bg-bg text-fg flex items-center justify-center">
        <div className="text-[13px] uppercase tracking-[0.22em] text-fg-3">Loading dashboard…</div>
      </div>
    )
  }

  if (authEnabled && !isAuthenticated) {
    return (
      <>
        <AuthPanel loading={authBusy} onSubmit={login} />
        <Toast />
      </>
    )
  }

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col bg-bg text-fg overflow-hidden">
      <Header
        connected={connected}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(prev => !prev)}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        profiles={profiles}
        activeProfile={activeProfile}
        onProfileChange={handleProfileChange}
        onProfileSave={saveProfile}
        onProfileDelete={deleteSelectedProfile}
        authUser={auth.username}
        onLogout={authEnabled ? logout : undefined}
      />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          open={sidebarOpen}
          agents={agents}
          onRefresh={refreshAgents}
          onAdd={addAgent}
          onUpdateAgentKey={updateAgentKey}
          onRemove={removeAgent}
          onDiscover={discoverAgents}
          isDiscovering={isDiscovering}
          isRefreshing={isRefreshing}
        />

        <main className="flex-1 overflow-y-auto p-4 space-y-4">
          <KPIBar agents={agents} testState={testState} latest={latestMetrics} />

          {activeTab === 'test' && (
            <>
              <TestConfigPanel
                agents={agentsMap}
                testState={testState}
                latestMetrics={latestMetrics}
                onStart={startTest}
                onStop={stopTest}
                onConfigChange={setDraftConfig}
              />
              <LiveResults
                testState={testState}
                metrics={latestMetrics}
                metricsHistory={metricsHistory}
              />
              <LogPanel logs={logs} onClear={clearLogs} />
            </>
          )}

          {activeTab === 'reports' && (
            selectedReport
              ? <ReportViewer key={selectedReport} filename={selectedReport} onBack={() => setSelectedReport(null)} />
              : <ReportList onSelect={setSelectedReport} />
          )}
        </main>
      </div>

      <Toast />
    </div>
  )
}
