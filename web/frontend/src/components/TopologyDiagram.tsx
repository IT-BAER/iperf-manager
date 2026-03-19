import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import type { Agent, TestConfig, ClientRow, Metrics } from '../types'

interface NI { iface: string; ip: string }

interface Props {
  agents: Record<string, Agent>
  config: TestConfig
  isRunning: boolean
  latestMetrics?: Metrics | null
  onUpdate: <K extends keyof TestConfig>(key: K, value: TestConfig[K]) => void
  onUpdateRow: (idx: number, key: keyof ClientRow, value: string) => void
  onAddClient: (agentId: string) => void
  onRemoveClient: (idx: number) => void
  onSetServer: (agentId: string) => void
  onRemoveServer: () => void
}

/** Extract typed interfaces list from an agent's details */
function getInterfaces(a: Agent | undefined): NI[] {
  if (!a) return []
  const ifaces = a.details?.interfaces
  if (Array.isArray(ifaces) && ifaces.length > 0) return ifaces as NI[]
  const ips = a.details?.ips
  if (Array.isArray(ips)) return (ips as string[]).map(ip => ({ iface: ip, ip }))
  return []
}

/* ── tiny drop-zone hook ──────────────────────────────────── */
function useDropZone(onDrop: (agentId: string) => void, disabled: boolean) {
  const [over, setOver] = useState(false)
  const onDragOver = (e: React.DragEvent) => {
    if (disabled) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setOver(true)
  }
  const onDragLeave = () => setOver(false)
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setOver(false)
    if (disabled) return
    const id = e.dataTransfer.getData('application/agent-id')
    if (id) onDrop(id)
  }
  return { over, onDragOver, onDragLeave, onDrop: handleDrop }
}

/** Format Mbps to human-readable string */
function fmtSpeed(mbps: number): string {
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(1)} Gbps`
  if (mbps >= 1) return `${mbps.toFixed(1)} Mbps`
  if (mbps > 0) return `${(mbps * 1000).toFixed(0)} Kbps`
  return '0'
}

function metricClientKey(row: ClientRow): string {
  return row.name.trim() || row.agent
}

/* ── main component ──────────────────────────────────────── */
export default function TopologyDiagram({
  agents, config, isRunning, latestMetrics,
  onUpdate, onUpdateRow, onAddClient, onRemoveClient, onSetServer, onRemoveServer,
}: Props) {
  const serverAgent = agents[config.server_agent]
  const serverIfaces = getInterfaces(serverAgent)

  /* SVG line drawing refs */
  const containerRef = useRef<HTMLDivElement>(null)
  const serverRef = useRef<HTMLDivElement>(null)
  const clientRefs = useRef<(HTMLDivElement | null)[]>([])
  const [lines, setLines] = useState<{ x1: number; y1: number; x2: number; y2: number }[]>([])

  const recalcLines = useCallback(() => {
    if (!containerRef.current || !serverRef.current) { setLines([]); return }
    const cRect = containerRef.current.getBoundingClientRect()
    const sRect = serverRef.current.getBoundingClientRect()
    const sx = sRect.right - cRect.left
    const sy = sRect.top + sRect.height / 2 - cRect.top
    const next: typeof lines = []
    clientRefs.current.forEach(el => {
      if (!el) return
      const r = el.getBoundingClientRect()
      next.push({ x1: sx, y1: sy, x2: r.left - cRect.left, y2: r.top + r.height / 2 - cRect.top })
    })
    setLines(next)
  }, [])

  useEffect(() => {
    recalcLines()
    const obs = new ResizeObserver(recalcLines)
    if (containerRef.current) obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [config.server_agent, config.clients.length, recalcLines])

  /* Drop zones */
  const serverDrop = useDropZone(id => {
    if (config.clients.some(c => c.agent === id)) return  // already a client
    onSetServer(id)
  }, isRunning)
  const clientDrop = useDropZone(id => {
    if (id === config.server_agent) return                // already the server
    if (config.clients.some(c => c.agent === id)) return  // already a client
    onAddClient(id)
  }, isRunning)

  /* Card enter/exit animation */
  const [exitingServer, setExitingServer] = useState(false)
  const [exitingClients, setExitingClients] = useState<Set<number>>(new Set())

  const handleRemoveServer = useCallback(() => {
    setExitingServer(true)
    setTimeout(() => { setExitingServer(false); onRemoveServer() }, 250)
  }, [onRemoveServer])

  const handleRemoveClient = useCallback((idx: number) => {
    setExitingClients(prev => new Set(prev).add(idx))
    setTimeout(() => {
      setExitingClients(prev => { const n = new Set(prev); n.delete(idx); return n })
      onRemoveClient(idx)
    }, 250)
  }, [onRemoveClient])

  return (
    <div ref={containerRef} className="relative">
      {/* SVG lines */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none z-0" style={{ overflow: 'visible' }}>
        <defs>
          <marker id="arrow" viewBox="-2 -2 14 11" refX="10" refY="3.5" markerWidth="10" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
            <path d="M0 0 L10 3.5 L0 7Z" fill="currentColor" className="text-accent/50" />
          </marker>
          <marker id="arrow-active" viewBox="-2 -2 14 11" refX="10" refY="3.5" markerWidth="10" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
            <path d="M0 0 L10 3.5 L0 7Z" className="fill-accent" />
          </marker>
          {isRunning && (
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          )}
        </defs>
        {lines.map((l, i) => {
          const row = config.clients[i]
          const cm = row && latestMetrics?.clients[metricClientKey(row)]
          const active = isRunning && cm && (cm.up > 0 || cm.dn > 0)
          return (
            <g key={i}>
              <line
                x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
                className={`topo-line ${active ? 'stroke-accent' : 'stroke-accent/30'}`}
                strokeWidth={active ? 3 : 2.25}
                strokeDasharray={active ? '1 10' : '1 8'}
                strokeLinecap="round"
                markerEnd={active ? 'url(#arrow-active)' : 'url(#arrow)'}
                filter={active ? 'url(#glow)' : undefined}
                style={active ? { animation: 'dash-flow 0.8s linear infinite, line-pulse 1.6s ease-in-out infinite' } : undefined}
              />
            </g>
          )
        })}
      </svg>

      {/* Inject keyframe for flowing dashes */}
      {isRunning && (
        <style>{`
          @keyframes dash-flow { to { stroke-dashoffset: -22; } }
          @keyframes line-pulse {
            0%, 100% { opacity: 0.88; }
            50% { opacity: 1; }
          }
        `}</style>
      )}
      {/* Card animations */}
      <style>{`
        @keyframes card-enter { from { opacity: 0; transform: translateY(10px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
        @keyframes card-exit  { from { opacity: 1; transform: translateY(0) scale(1); } to { opacity: 0; transform: translateY(-8px) scale(0.97); } }
        .topo-line { transition: x1 0.4s ease, y1 0.4s ease, x2 0.4s ease, y2 0.4s ease, stroke-width 0.3s ease, opacity 0.3s ease; }
      `}</style>

      <div className="grid grid-cols-[minmax(200px,340px)_150px_minmax(250px,480px)] gap-12 items-start relative z-10 justify-center">
        {/* ── SERVER ZONE ─────────────────────────────── */}
        <div
          className={`min-h-[160px] rounded-lg border-2 border-dashed p-3 transition-colors duration-150 ${
            serverDrop.over
              ? 'border-accent bg-accent/5'
              : serverAgent
                ? 'border-line bg-surface-raised'
                : 'border-line/50 bg-surface'
          }`}
          onDragOver={serverDrop.onDragOver}
          onDragLeave={serverDrop.onDragLeave}
          onDrop={serverDrop.onDrop}
        >
          <div className="text-[11px] font-semibold uppercase tracking-widest text-fg-3 mb-2 flex items-center gap-2">
            <i className="fa-solid fa-server text-accent text-[12px]" />
            Server
          </div>

          {serverAgent ? (
            <div ref={serverRef} className={`min-h-[189px] rounded-md border bg-bg p-3 space-y-2 transition-all duration-300 ${
              isRunning ? 'border-accent/40 shadow-[0_0_12px_rgba(68,147,248,0.16)]' : 'border-line'
            }`} style={{ animation: exitingServer ? 'card-exit 0.25s ease-in forwards' : 'card-enter 0.35s ease-out' }}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-ok animate-pulse' : 'bg-ok'} shadow-[0_0_6px_rgba(63,185,80,0.45)]`} />
                  <span className="text-[13px] font-semibold text-fg">{serverAgent.name}</span>
                </div>
                {!isRunning && (
                  <button
                    onClick={handleRemoveServer}
                    className="w-5 h-5 flex items-center justify-center text-fg-4 hover:text-err transition-colors"
                    title="Remove server"
                  >
                    <i className="fa-solid fa-xmark text-[10px]" />
                  </button>
                )}
              </div>
              <div className="text-[11px] text-fg-3 font-mono">{serverAgent.url}</div>

              <div>
                <label className="text-[11px] text-fg-3 block mb-0.5">Bind Interface</label>
                <select
                  className="input-base text-[12px]"
                  value={config.server_bind}
                  onChange={e => onUpdate('server_bind', e.target.value)}
                  disabled={isRunning}
                >
                  <option value="">All interfaces</option>
                  {serverIfaces.map(ni => (
                    <option key={ni.ip} value={ni.ip}>{ni.iface} ({ni.ip})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[11px] text-fg-3 block mb-0.5">API Key</label>
                <input
                  className="input-base text-[12px]"
                  type="password"
                  placeholder="Optional"
                  value={config.api_key}
                  onChange={e => onUpdate('api_key', e.target.value)}
                  disabled={isRunning}
                />
              </div>
            </div>
          ) : (
            <div ref={serverRef} className="flex flex-col items-center justify-center h-24 text-fg-4 text-[12px] gap-1.5"
              style={{ animation: 'card-enter 0.35s ease-out' }}>
              <i className="fa-solid fa-arrow-down-to-line text-lg opacity-50" />
              <span>Drag an agent here</span>
            </div>
          )}
        </div>

        {/* ── CENTER ARROW ────────────────────────────── */}
        <div className="relative flex flex-col items-center justify-center self-center gap-1 text-fg-4 select-none w-[150px]">
          {isRunning ? (
            <>
              <i className="fa-solid fa-arrows-left-right text-lg text-accent animate-pulse relative z-10 drop-shadow-[0_0_10px_rgba(68,147,248,0.22)]" />
              <div className={`relative z-10 rounded-full border px-2.5 py-1.5 text-center backdrop-blur-sm transition-all duration-250 ease-out ${
                latestMetrics
                  ? 'border-line/30 bg-bg/70 opacity-100 scale-100'
                  : 'border-line/20 bg-bg/55 opacity-85 scale-95'
              }`}>
                <div className="text-[9px] uppercase tracking-[0.18em] text-accent font-semibold mb-0.5">Live</div>
                {latestMetrics ? (
                  <div className="flex items-center justify-center gap-3">
                    <span className="text-[10px] font-mono font-semibold text-ok">↑ {fmtSpeed(latestMetrics.total_up)}</span>
                    <span className="text-[10px] font-mono font-semibold text-accent">↓ {fmtSpeed(latestMetrics.total_dn)}</span>
                  </div>
                ) : (
                  <div className="text-[10px] font-medium text-accent/80">waiting</div>
                )}
              </div>
            </>
          ) : (
            <>
              <i className="fa-solid fa-arrows-left-right text-lg opacity-40" />
              <span className="text-[10px] uppercase tracking-wider opacity-40">iperf3</span>
            </>
          )}
        </div>

        {/* ── CLIENTS ZONE ────────────────────────────── */}
        <div
          className={`min-h-[160px] rounded-lg border-2 border-dashed p-3 transition-colors duration-150 ${
            clientDrop.over
              ? 'border-accent bg-accent/5'
              : config.clients.length > 0
                ? 'border-line bg-surface-raised'
                : 'border-line/50 bg-surface'
          }`}
          onDragOver={clientDrop.onDragOver}
          onDragLeave={clientDrop.onDragLeave}
          onDrop={clientDrop.onDrop}
        >
          <div className="text-[11px] font-semibold uppercase tracking-widest text-fg-3 mb-2 flex items-center gap-2">
            <i className="fa-solid fa-laptop text-accent text-[12px]" />
            Clients
            {config.clients.length > 0 && (
              <span className="text-[10px] font-mono text-fg-4">{config.clients.length}</span>
            )}
          </div>

          {config.clients.length > 0 ? (
            <div className="space-y-2">
              {config.clients.map((row, i) => {
                const ca = agents[row.agent]
                const cIfaces = getInterfaces(ca)
                const cm = latestMetrics?.clients[metricClientKey(row)]
                const clientActive = isRunning && cm && (cm.up > 0 || cm.dn > 0)
                return (
                  <div
                    key={i}
                    ref={el => { clientRefs.current[i] = el }}
                    className={`min-h-[189px] rounded-md border bg-bg p-3 transition-all duration-300 ${
                      clientActive ? 'border-accent/40 shadow-[0_0_12px_rgba(68,147,248,0.16)]' : 'border-line'
                    }`}
                    style={{ animation: exitingClients.has(i) ? 'card-exit 0.25s ease-in forwards' : 'card-enter 0.35s ease-out' }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${
                          clientActive ? 'bg-ok animate-pulse' : ca?.status === 'online' ? 'bg-ok' : 'bg-fg-4'
                        } shadow-[0_0_6px_rgba(63,185,80,0.45)]`} />
                        <span className="text-[13px] font-semibold text-fg">{ca?.name ?? 'Unknown'}</span>
                      </div>
                      {!isRunning && (
                        <button
                          onClick={() => handleRemoveClient(i)}
                          className="w-5 h-5 flex items-center justify-center text-fg-4 hover:text-err transition-colors"
                          title="Remove client"
                        >
                          <i className="fa-solid fa-xmark text-[10px]" />
                        </button>
                      )}
                    </div>
                    {ca && <div className="mt-2 text-[11px] text-fg-3 font-mono">{ca.url}</div>}
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <div>
                        <label className="text-[11px] text-fg-3 block mb-0.5">Name</label>
                        <input
                          className="input-base text-[12px]"
                          placeholder="e.g. client-1"
                          value={row.name}
                          onChange={e => onUpdateRow(i, 'name', e.target.value)}
                          disabled={isRunning}
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-fg-3 block mb-0.5">API Key</label>
                        <input
                          className="input-base text-[12px]"
                          type="password"
                          placeholder="Optional"
                          value={row.api_key}
                          onChange={e => onUpdateRow(i, 'api_key', e.target.value)}
                          disabled={isRunning}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <div>
                        <label className="text-[11px] text-fg-3 block mb-0.5">Bind Interface</label>
                        <select
                          className="input-base text-[12px]"
                          value={row.bind}
                          onChange={e => onUpdateRow(i, 'bind', e.target.value)}
                          disabled={isRunning}
                        >
                          <option value="">Auto</option>
                          {cIfaces.map(ni => (
                            <option key={ni.ip} value={ni.ip}>{ni.iface} ({ni.ip})</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-[11px] text-fg-3 block mb-0.5">Server Target</label>
                        <select
                          className="input-base text-[12px]"
                          value={row.server_target}
                          onChange={e => onUpdateRow(i, 'server_target', e.target.value)}
                          disabled={isRunning}
                        >
                          <option value="">Auto</option>
                          {serverIfaces.map(ni => (
                            <option key={ni.ip} value={ni.ip}>{ni.iface} ({ni.ip})</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-24 text-fg-4 text-[12px] gap-1.5">
              <i className="fa-solid fa-arrow-down-to-line text-lg opacity-50" />
              <span>Drag agents here</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
