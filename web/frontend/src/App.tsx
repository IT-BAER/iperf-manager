import { useState, useEffect, useCallback } from 'react'
import { useSocket } from './hooks/useSocket'
import { api } from './api'
import type { Agent, TestState, Metrics, Report, Profile, LogEntry } from './types'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { KPIBar } from './components/KPIBar'
import { TestConfig } from './components/TestConfig'
import { LiveResults } from './components/LiveResults'
import { LogPanel } from './components/LogPanel'
import { ReportViewer } from './components/ReportViewer'
import { Toast } from './components/Toast'

type View = 'dashboard' | 'reports'

export function App() {
  const [view, setView] = useState<View>('dashboard')
  const [agents, setAgents] = useState<Agent[]>([])
  const [testState, setTestState] = useState<TestState>({ status: 'idle' })
  const [metrics, setMetrics] = useState<Metrics[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [viewingReport, setViewingReport] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const { on, emit: sEmit } = useSocket()

  const log = useCallback((msg: string, type: LogEntry['type'] = 'info') => {
    setLogs(prev => [...prev.slice(-200), { ts: Date.now(), msg, type }])
  }, [])

  // Fetch initial data
  useEffect(() => {
    api<Agent[]>('/api/agents?refresh=1').then(d => d && setAgents(d))
    api<Report[]>('/api/reports').then(d => d && setReports(d))
    api<Profile[]>('/api/profiles').then(d => d && setProfiles(d))
    api<TestState>('/api/test/status').then(d => d && setTestState(d))
  }, [])

  // Socket.IO events
  useEffect(() => {
    const off1 = on('status', (d: unknown) => {
      const data = d as { test: TestState }
      setTestState(data.test)
    })
    const off2 = on('metrics', (d: unknown) => {
      const m = d as Metrics
      setMetrics(prev => [...prev.slice(-300), m])
    })
    const off3 = on('agents_update', (d: unknown) => {
      setAgents(d as Agent[])
    })
    const off4 = on('test_finished', (d: unknown) => {
      const data = d as { csv?: string }
      log('Test finished' + (data.csv ? ` → ${data.csv}` : ''), 'ok')
      setTestState(prev => ({ ...prev, status: 'idle', finished_at: Date.now(), last_csv: data.csv }))
      api<Report[]>('/api/reports').then(r => r && setReports(r))
    })
    const off5 = on('log', (d: unknown) => {
      const entry = d as LogEntry
      log(entry.msg, entry.type)
    })
    return () => { off1(); off2(); off3(); off4(); off5() }
  }, [on, log])

  const refreshAgents = useCallback(() => {
    sEmit('ping_agents')
    log('Refreshing agents…')
  }, [sEmit, log])

  const addAgent = useCallback(async (url: string, name: string) => {
    const a = await api<Agent>('/api/agents', {
      method: 'POST', body: JSON.stringify({ url, name }),
    })
    if (a) {
      setAgents(prev => [...prev.filter(x => x.id !== a.id), a])
      log(`Added agent: ${a.name}`, 'ok')
    }
  }, [log])

  const removeAgent = useCallback(async (id: string) => {
    await api('/api/agents/' + id, { method: 'DELETE' })
    setAgents(prev => prev.filter(x => x.id !== id))
    log('Removed agent', 'info')
  }, [log])

  const discover = useCallback(async () => {
    log('Discovering agents…')
    const r = await api<{ discovered: number; agents: Agent[] }>('/api/agents/discover', { method: 'POST' })
    if (r) {
      setAgents(prev => {
        const map = new Map(prev.map(a => [a.id, a]))
        r.agents.forEach(a => map.set(a.id, a))
        return Array.from(map.values())
      })
      log(`Discovered ${r.discovered} agent(s)`, r.discovered > 0 ? 'ok' : 'info')
    }
  }, [log])

  const latestMetrics = metrics.length > 0 ? metrics[metrics.length - 1] : null

  return (
    <div className="flex h-screen bg-bg text-fg overflow-hidden">
      <Sidebar
        open={sidebarOpen}
        agents={agents}
        onRefresh={refreshAgents}
        onAdd={addAgent}
        onRemove={removeAgent}
        onDiscover={discover}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <Header
          view={view}
          onViewChange={setView}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(o => !o)}
          testState={testState}
        />

        <main className="flex-1 overflow-y-auto p-4 space-y-4">
          {view === 'dashboard' ? (
            <>
              <KPIBar
                agents={agents}
                testState={testState}
                latest={latestMetrics}
              />
              <TestConfig
                agents={agents}
                profiles={profiles}
                testState={testState}
                onProfilesChange={setProfiles}
                onLog={log}
              />
              <LiveResults
                metrics={metrics}
                testState={testState}
              />
              <LogPanel logs={logs} onClear={() => setLogs([])} />
            </>
          ) : (
            <ReportViewer
              reports={reports}
              viewingReport={viewingReport}
              onView={setViewingReport}
              onRefresh={() => api<Report[]>('/api/reports').then(r => r && setReports(r))}
            />
          )}
        </main>
      </div>

      <Toast />
    </div>
  )
}