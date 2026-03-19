import { useState, useEffect, useCallback, useRef } from 'react'
import type { Agent, TestConfig, TestState, ClientRow, Metrics } from '../types'
import TopologyDiagram from './TopologyDiagram'

const MODES = ['bidirectional', 'upload', 'download'] as const
const PROTOCOLS = ['tcp', 'udp'] as const

const DEFAULT_CONFIG: TestConfig = {
  server_agent: '',
  server_bind: '',
  api_key: '',
  duration_sec: 10,
  base_port: 5201,
  poll_interval_sec: 1,
  protocol: 'tcp',
  parallel: 1,
  omit_sec: 0,
  bitrate: '',
  tcp_window: '',
  mode: 'bidirectional',
  clients: [],
}

interface TestConfigProps {
  agents: Record<string, Agent>
  testState: TestState
  latestMetrics?: Metrics | null
  onStart: (config: TestConfig) => Promise<void>
  onStop: () => Promise<void>
  onConfigChange?: (config: TestConfig) => void
}

export default function TestConfigPanel({
  agents, testState, latestMetrics, onStart, onStop, onConfigChange,
}: TestConfigProps) {
  const [open, setOpen] = useState(true)
  const [showParams, setShowParams] = useState(false)
  const [config, setConfig] = useState<TestConfig>(DEFAULT_CONFIG)

  const isRunning = testState.status !== 'idle'
  const canStart = Boolean(config.server_agent) && config.clients.length > 0

  // Keep parent in sync
  const onConfigChangeRef = useRef(onConfigChange)
  onConfigChangeRef.current = onConfigChange
  useEffect(() => { onConfigChangeRef.current?.(config) }, [config])

  // Receive loaded profiles
  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<TestConfig>
      if (ce.detail && typeof ce.detail === 'object') setConfig(ce.detail)
    }
    window.addEventListener('load-profile', handler)
    return () => window.removeEventListener('load-profile', handler)
  }, [])

  const update = useCallback(<K extends keyof TestConfig>(key: K, value: TestConfig[K]) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }, [])

  const removeRow = (idx: number) => {
    setConfig(prev => ({ ...prev, clients: prev.clients.filter((_, i) => i !== idx) }))
  }

  const updateRow = (idx: number, key: keyof ClientRow, value: string) => {
    setConfig(prev => ({
      ...prev,
      clients: prev.clients.map((r, i) => i === idx ? { ...r, [key]: value } : r),
    }))
  }

  // CSS helpers
  const SL = 'text-[11px] font-semibold uppercase tracking-widest text-fg-3 mb-2'
  const FL = 'block text-[12px] font-medium text-fg-2 mb-1'

  // Mode / protocol toggle classes
  const toggleBtn = (active: boolean) =>
    `inline-flex items-center px-3 h-8 text-[13px] font-medium border-r border-line last:border-r-0 transition-colors duration-150 leading-none ` +
    (active
      ? 'bg-accent-subtle text-accent'
      : 'text-fg-3 hover:text-fg hover:bg-surface-hover disabled:opacity-40 disabled:cursor-not-allowed')

  const statusLabel =
    testState.status === 'running' ? 'Running…' :
    testState.status === 'stopping' ? 'Stopping…' : ''

  return (
    <div className="panel">
      {/* ── Header ──────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-line cursor-pointer select-none hover:bg-surface-hover transition-colors duration-150"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-semibold text-fg">Test Configuration</span>
          {statusLabel && <span className="text-[12px] text-fg-3">{statusLabel}</span>}
        </div>
        <span className={`text-fg-3 text-lg leading-none transition-transform duration-150 ${open ? '' : '-rotate-90'}`}>
          ▾
        </span>
      </div>

      {/* ── Body ────────────────────────────────────────────── */}
      <div className={`collapsible-grid ${open ? 'open' : 'closed'}`}>
        <div className="collapsible-inner">
          <div className="p-4 flex flex-col gap-0">

          {/* Topology Diagram */}
          <TopologyDiagram
            agents={agents}
            config={config}
            isRunning={isRunning}
            latestMetrics={latestMetrics}
            onUpdate={update}
            onUpdateRow={updateRow}
            onAddClient={(agentId: string) => {
              setConfig(prev => {
                // Prevent duplicates: skip if agent is already a client or is the server
                if (prev.server_agent === agentId) return prev
                if (prev.clients.some(c => c.agent === agentId)) return prev
                return {
                  ...prev,
                  clients: [...prev.clients, { agent: agentId, name: '', server_target: '', bind: '', api_key: '' }],
                }
              })
            }}
            onRemoveClient={removeRow}
            onSetServer={(agentId: string) => {
              setConfig(prev => {
                // Remove from clients if being promoted to server
                const clients = prev.clients.filter(c => c.agent !== agentId)
                return { ...prev, server_agent: agentId, clients }
              })
            }}
            onRemoveServer={() => { update('server_agent', ''); update('server_bind', '') }}
          />

          <hr className="my-4 border-line" />

          {/* Parameters + Advanced + Protocol — collapsible */}
          <button
            type="button"
            className="flex items-center gap-2 w-full text-left mb-2"
            onClick={() => setShowParams(p => !p)}
          >
            <span className={`text-fg-3 text-xs leading-none transition-transform duration-150 ${showParams ? '' : '-rotate-90'}`}>▾</span>
            <span className={SL + ' mb-0'}>Parameters &amp; Options</span>
          </button>

          <div className={`overflow-hidden transition-all duration-200 ${showParams ? 'max-h-[600px] opacity-100' : 'max-h-0 opacity-0'}`}>
          <div className={SL}>Parameters</div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
            <div>
              <label htmlFor="duration-sec" className={FL}>Duration (s)</label>
              <input
                id="duration-sec"
                name="durationSec"
                type="number" min={1}
                className="input-base"
                value={config.duration_sec}
                onChange={e => update('duration_sec', Math.max(1, parseInt(e.target.value) || 1))}
                disabled={isRunning}
              />
            </div>
            <div>
              <label htmlFor="base-port" className={FL}>Base Port</label>
              <input
                id="base-port"
                name="basePort"
                type="number" min={1024} max={65534}
                className="input-base"
                value={config.base_port}
                onChange={e => update('base_port', parseInt(e.target.value) || 5201)}
                disabled={isRunning}
              />
            </div>
            <div>
              <label htmlFor="poll-interval-sec" className={FL}>Poll Interval (s)</label>
              <input
                id="poll-interval-sec"
                name="pollIntervalSec"
                type="number" min={0.1} step={0.1}
                className="input-base"
                value={config.poll_interval_sec}
                onChange={e => update('poll_interval_sec', parseFloat(e.target.value) || 1)}
                disabled={isRunning}
              />
            </div>
            <div>
              <label htmlFor="parallel-streams" className={FL}>Parallel Streams</label>
              <input
                id="parallel-streams"
                name="parallelStreams"
                type="number" min={1} max={128}
                className="input-base"
                value={config.parallel}
                onChange={e => update('parallel', Math.max(1, parseInt(e.target.value) || 1))}
                disabled={isRunning}
              />
            </div>
            <div>
              <label htmlFor="omit-sec" className={FL}>Omit (s)</label>
              <input
                id="omit-sec"
                name="omitSec"
                type="number" min={0}
                className="input-base"
                value={config.omit_sec}
                onChange={e => update('omit_sec', Math.max(0, parseInt(e.target.value) || 0))}
                disabled={isRunning}
              />
            </div>
          </div>

          <hr className="my-4 border-line" />

          {/* Advanced */}
          <div className={SL}>Advanced</div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
            <div>
              <label htmlFor="bitrate" className={FL}>Bitrate</label>
              <input
                id="bitrate"
                name="bitrate"
                className="input-base"
                placeholder="e.g. 100M or 0"
                value={config.bitrate}
                onChange={e => update('bitrate', e.target.value)}
                disabled={isRunning}
              />
            </div>
            <div>
              <label htmlFor="tcp-window" className={FL}>TCP Window</label>
              <input
                id="tcp-window"
                name="tcpWindow"
                className="input-base"
                placeholder="e.g. 128K"
                value={config.tcp_window}
                onChange={e => update('tcp_window', e.target.value)}
                disabled={isRunning}
              />
            </div>
          </div>

          <hr className="my-4 border-line" />

          {/* Protocol + Mode toggles */}
          <div className="flex gap-8 flex-wrap">
            <div>
              <div className={SL}>Protocol</div>
              <div className="inline-flex border border-line rounded-sm overflow-hidden bg-bg">
                {PROTOCOLS.map(p => (
                  <button
                    key={p}
                    type="button"
                    disabled={isRunning}
                    onClick={() => update('protocol', p)}
                    className={toggleBtn(config.protocol === p)}
                  >
                    {p.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className={SL}>Mode</div>
              <div className="inline-flex border border-line rounded-sm overflow-hidden bg-bg">
                {MODES.map(m => (
                  <button
                    key={m}
                    type="button"
                    disabled={isRunning}
                    onClick={() => update('mode', m)}
                    className={toggleBtn(config.mode === m)}
                  >
                    {m.charAt(0).toUpperCase() + m.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>
          </div>{/* end collapsible */}

          <hr className="my-4 border-line" />

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              className="btn btn-primary"
              disabled={isRunning || !canStart}
              onClick={() => onStart(config)}
            >
              {isRunning && (
                <span className="btn-loader shrink-0" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              )}
              Start Test
            </button>
            <button
              className="btn btn-danger"
              disabled={testState.status === 'idle'}
              onClick={() => onStop()}
            >
              Stop
            </button>
            {!isRunning && !canStart && (
              <span className="text-[12px] text-fg-3 ml-1">
                {config.server_agent ? 'Add at least one client agent to start' : 'Select a server agent to start'}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  </div>
  )
}