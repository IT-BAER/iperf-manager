import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { Agent, TestState, TestConfig as TConfig, Profile, LogEntry, ClientRow } from '../types'

interface Props {
  agents: Agent[]
  profiles: Profile[]
  testState: TestState
  onProfilesChange: (p: Profile[]) => void
  onLog: (msg: string, type?: LogEntry['type']) => void
}

const defaults: Omit<TConfig, 'server_agent' | 'server_bind' | 'api_key' | 'clients'> = {
  duration_sec: 30,
  base_port: 5201,
  poll_interval_sec: 1,
  protocol: 'tcp',
  parallel: 4,
  omit_sec: 1,
  bitrate: '',
  tcp_window: '',
  mode: 'download',
}

export function TestConfig({ agents, profiles, testState, onProfilesChange, onLog }: Props) {
  const [cfg, setCfg] = useState<TConfig>({
    ...defaults,
    server_agent: '',
    server_bind: '',
    api_key: '',
    clients: [],
  })
  const [profileName, setProfileName] = useState('')

  const onlineAgents = agents.filter(a => a.status === 'online')
  const running = testState.status !== 'idle'

  // Auto-select first server agent
  useEffect(() => {
    if (!cfg.server_agent && onlineAgents.length > 0) {
      setCfg(c => ({ ...c, server_agent: onlineAgents[0].url }))
    }
  }, [onlineAgents, cfg.server_agent])

  const update = <K extends keyof TConfig>(key: K, val: TConfig[K]) =>
    setCfg(c => ({ ...c, [key]: val }))

  const addClient = useCallback(() => {
    const available = onlineAgents.filter(
      a => a.url !== cfg.server_agent && !cfg.clients.some(c => c.agent === a.url)
    )
    if (available.length === 0) return
    const a = available[0]
    const row: ClientRow = { agent: a.url, name: a.name, server_target: '', api_key: '' }
    setCfg(c => ({ ...c, clients: [...c.clients, row] }))
  }, [onlineAgents, cfg.server_agent, cfg.clients])

  const removeClient = (idx: number) =>
    setCfg(c => ({ ...c, clients: c.clients.filter((_, i) => i !== idx) }))

  const updateClient = (idx: number, key: keyof ClientRow, val: string) =>
    setCfg(c => ({
      ...c,
      clients: c.clients.map((r, i) => i === idx ? { ...r, [key]: val } : r),
    }))

  const startTest = async () => {
    if (running) return
    if (!cfg.server_agent) {
      onLog('Select a server agent', 'err')
      return
    }
    if (cfg.clients.length === 0) {
      onLog('Add at least one client', 'err')
      return
    }
    onLog('Starting test…')
    await api('/api/test/start', { method: 'POST', body: JSON.stringify(cfg) })
  }

  const stopTest = async () => {
    onLog('Stopping test…')
    await api('/api/test/stop', { method: 'POST' })
  }

  const saveProfile = async () => {
    if (!profileName.trim()) return
    const r = await api<{ ok: boolean; name: string }>('/api/profiles', {
      method: 'POST',
      body: JSON.stringify({ name: profileName.trim(), config: cfg }),
    })
    if (r) {
      onLog(`Profile saved: ${r.name}`, 'ok')
      const list = await api<Profile[]>('/api/profiles')
      if (list) onProfilesChange(list)
    }
  }

  const loadProfile = async (name: string) => {
    const r = await api<{ name: string; config: TConfig }>(`/api/profiles/${name}`)
    if (r) {
      setCfg(r.config)
      setProfileName(name)
      onLog(`Loaded profile: ${name}`, 'ok')
    }
  }

  return (
    <div className="panel">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h3 className="text-sm font-semibold">Test Configuration</h3>
        <div className="flex gap-2">
          {!running ? (
            <button
              onClick={startTest}
              disabled={!cfg.server_agent || cfg.clients.length === 0}
              className="btn btn-primary btn-sm"
            >
              ▶ Start Test
            </button>
          ) : (
            <button onClick={stopTest} className="btn btn-danger btn-sm">
              ■ Stop
            </button>
          )}
        </div>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Server Agent */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Server Agent
          </label>
          <select
            value={cfg.server_agent}
            onChange={e => update('server_agent', e.target.value)}
            disabled={running}
            className="input-base"
          >
            <option value="">— select —</option>
            {onlineAgents.map(a => (
              <option key={a.id} value={a.url}>{a.name}</option>
            ))}
          </select>
        </div>

        {/* Protocol */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Protocol
          </label>
          <select
            value={cfg.protocol}
            onChange={e => update('protocol', e.target.value as 'tcp' | 'udp')}
            disabled={running}
            className="input-base"
          >
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
        </div>

        {/* Mode */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Mode
          </label>
          <select
            value={cfg.mode}
            onChange={e => update('mode', e.target.value)}
            disabled={running}
            className="input-base"
          >
            <option value="download">Download</option>
            <option value="upload">Upload</option>
            <option value="bidirectional">Bidirectional</option>
          </select>
        </div>

        {/* Duration */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Duration (sec)
          </label>
          <input
            type="number"
            value={cfg.duration_sec}
            onChange={e => update('duration_sec', +e.target.value || 30)}
            disabled={running}
            className="input-base"
            min={1}
            max={3600}
          />
        </div>

        {/* Parallel */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Parallel Streams
          </label>
          <input
            type="number"
            value={cfg.parallel}
            onChange={e => update('parallel', +e.target.value || 1)}
            disabled={running}
            className="input-base"
            min={1}
            max={128}
          />
        </div>

        {/* Base Port */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Base Port
          </label>
          <input
            type="number"
            value={cfg.base_port}
            onChange={e => update('base_port', +e.target.value || 5201)}
            disabled={running}
            className="input-base"
          />
        </div>

        {/* Bitrate */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Bitrate (e.g. 1G)
          </label>
          <input
            value={cfg.bitrate}
            onChange={e => update('bitrate', e.target.value)}
            disabled={running}
            className="input-base"
            placeholder="auto"
          />
        </div>

        {/* Omit */}
        <div>
          <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
            Omit (sec)
          </label>
          <input
            type="number"
            value={cfg.omit_sec}
            onChange={e => update('omit_sec', +e.target.value)}
            disabled={running}
            className="input-base"
            min={0}
          />
        </div>
      </div>

      {/* Clients */}
      <div className="px-4 pb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-medium text-fg-3 uppercase tracking-wider">
            Client Agents ({cfg.clients.length})
          </span>
          <button
            onClick={addClient}
            disabled={running}
            className="btn btn-sm"
          >+ Add Client</button>
        </div>

        {cfg.clients.length > 0 && (
          <div className="border border-line rounded-sm overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-surface-raised text-fg-3">
                  <th className="text-left px-3 py-2 font-medium">Agent</th>
                  <th className="text-left px-3 py-2 font-medium">Name</th>
                  <th className="text-left px-3 py-2 font-medium">Server Target</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {cfg.clients.map((c, i) => (
                  <tr key={i} className="hover:bg-surface-hover transition-colors">
                    <td className="px-3 py-1.5">
                      <select
                        value={c.agent}
                        onChange={e => updateClient(i, 'agent', e.target.value)}
                        disabled={running}
                        className="input-base"
                      >
                        {onlineAgents
                          .filter(a => a.url !== cfg.server_agent)
                          .map(a => (
                            <option key={a.id} value={a.url}>{a.name}</option>
                          ))}
                      </select>
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        value={c.name}
                        onChange={e => updateClient(i, 'name', e.target.value)}
                        disabled={running}
                        className="input-base"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        value={c.server_target}
                        onChange={e => updateClient(i, 'server_target', e.target.value)}
                        disabled={running}
                        className="input-base"
                        placeholder="auto"
                      />
                    </td>
                    <td className="px-2 text-center">
                      <button
                        onClick={() => removeClient(i)}
                        disabled={running}
                        className="text-fg-3 hover:text-err text-xs"
                        aria-label="Remove client"
                      >✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Profiles */}
      <div className="px-4 pb-4 border-t border-line pt-3">
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="block text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1.5">
              Profile
            </label>
            <div className="flex gap-2">
              <select
                className="input-base flex-1"
                value=""
                onChange={e => e.target.value && loadProfile(e.target.value)}
              >
                <option value="">Load profile…</option>
                {profiles.map(p => (
                  <option key={p.name} value={p.name}>{p.name}</option>
                ))}
              </select>
              <input
                className="input-base w-40"
                placeholder="New profile name"
                value={profileName}
                onChange={e => setProfileName(e.target.value)}
              />
              <button onClick={saveProfile} className="btn btn-sm" disabled={!profileName.trim()}>
                Save
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
