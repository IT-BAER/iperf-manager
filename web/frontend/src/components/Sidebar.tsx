import { useState } from 'react'
import { isNewerVersion } from '../format'
import type { Agent } from '../types'

interface Props {
  open: boolean
  agents: Agent[]
  latestAgentVersion: string | null
  updatingAgents: ReadonlyMap<string, number>
  onUpdateAgent: (id: string) => void
  onRefresh: () => void
  onAdd: (url: string, name: string, apiKey: string) => void
  onUpdateAgentKey: (id: string, apiKey: string) => void
  onTrustCertificate: (id: string, fingerprint: string) => void
  onRemove: (id: string) => void
  onDiscover: () => void
  isDiscovering?: boolean
  isRefreshing?: boolean
}

function Spinner() {
  return (
    <span className="btn-loader shrink-0" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  )
}

function RefreshIcon() {
  return <i className="fa-solid fa-rotate-right text-[11px] shrink-0" aria-hidden="true" />
}

function AgentVersionLine({ agent, latest, updating, onUpdate }: {
  agent: Agent
  latest: string | null
  updating: boolean
  onUpdate: () => void
}) {
  const version = typeof agent.details?.version === 'string' ? agent.details.version : ''
  const update = agent.details?.update ?? {}
  const remoteUpdate = agent.details?.remote_update === true
  if (!version && !updating) return null
  const available = !!(version && latest && isNewerVersion(latest, version))
  return (
    <div className="text-xs text-fg-3 mt-1 ml-3.5 flex items-center gap-2 min-w-0">
      {version && <span className="font-mono tabular">v{version}</span>}
      {updating ? (
        <span className="flex items-center gap-1.5 text-accent"><Spinner /><span>Updating…</span></span>
      ) : available && (
        <>
          <span className="text-warn truncate" title={`Latest release: v${latest}`}>v{latest} available</span>
          {remoteUpdate ? (
            <button
              onClick={() => {
                if (window.confirm(`Update "${agent.name}" from v${version} to the latest release (v${latest})?\n\n`
                  + 'The agent restarts. Do not start tests on this agent until the update ends.')) onUpdate()
              }}
              className="underline hover:text-accent shrink-0"
            >
              Update
            </button>
          ) : (
            <span
              className="shrink-0 cursor-help"
              title="Remote update is off for this agent. Enable it with the installer option --remote-update yes (Linux) or -RemoteUpdate Yes (Windows)."
            >
              <i className="fa-solid fa-circle-info text-[10px]" aria-label="Remote update off" />
            </span>
          )}
        </>
      )}
      {!updating && update.state === 'failed' && (
        <span className="text-err truncate" title={update.error}>Update failed</span>
      )}
    </div>
  )
}

export function Sidebar({ open, agents, latestAgentVersion, updatingAgents, onUpdateAgent, onRefresh, onAdd, onUpdateAgentKey, onTrustCertificate, onRemove, onDiscover, isDiscovering, isRefreshing }: Props) {
  const [addUrl, setAddUrl] = useState('')
  const [addName, setAddName] = useState('')
  const [addApiKey, setAddApiKey] = useState('')
  const [showAdd, setShowAdd] = useState(false)

  const handleAdd = () => {
    if (!addUrl.trim()) return
    onAdd(addUrl.trim(), addName.trim() || addUrl.trim(), addApiKey.trim())
    setAddUrl('')
    setAddName('')
    setAddApiKey('')
    setShowAdd(false)
  }

  const handleSetKey = (agent: Agent) => {
    const entered = window.prompt(`Set API key for ${agent.name} (leave empty to clear):`, '')
    if (entered === null) return
    onUpdateAgentKey(agent.id, entered.trim())
  }

  const handleTrust = (agent: Agent) => {
    const next = agent.tls_new_fingerprint
    if (!next) return
    const ok = window.confirm(
      `The certificate of "${agent.name}" changed.\n\nPinned:\n${agent.tls_fingerprint}\n\nNew:\n${next}\n\n`
      + 'Trust the new certificate only if you regenerated or reinstalled this agent. '
      + 'Compare the new fingerprint with the agent log or installer output.',
    )
    if (ok) onTrustCertificate(agent.id, next)
  }

  const online = agents.filter(a => a.status === 'online').length

  if (!open) return null

  return (
    <aside className="w-[260px] shrink-0 border-r border-line bg-surface flex flex-col h-full">
      <div className="p-3 border-b border-line">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-[13px] font-semibold text-fg-2 uppercase tracking-wider">
            Agents
          </h2>
          <span className="text-xs text-fg-3 tabular">
            {online}/{agents.length} online
          </span>
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={onDiscover}
            disabled={isDiscovering}
            className="btn btn-sm flex-1 gap-1.5"
          >
            {isDiscovering ? <><Spinner /><span>Discovering…</span></> : <><i className="fa-solid fa-magnifying-glass text-[11px]" /><span>Discover</span></>}
          </button>
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="btn btn-sm flex-1 gap-1.5"
          >
            {isRefreshing
              ? <><Spinner /><span>Refreshing…</span></>
              : <><RefreshIcon /><span>Refresh</span></>
            }
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="btn btn-sm w-7 px-0 justify-center"
            aria-label="Add agent manually"
          ><i className="fa-solid fa-plus text-[11px]" /></button>
        </div>
      </div>

      <div className={`collapsible-grid ${showAdd ? 'open' : 'closed'}`}>
        <div className="collapsible-inner">
          <form
            className="p-3 border-b border-line bg-surface-raised space-y-2"
            onSubmit={event => {
              event.preventDefault()
              handleAdd()
            }}
          >
            <input
              className="input-base"
              name="agentUrl"
              aria-label="Agent URL"
              autoComplete="url"
              placeholder="https://host:9001"
              value={addUrl}
              onChange={e => setAddUrl(e.target.value)}
            />
            <input
              className="input-base"
              name="agentName"
              aria-label="Agent display name"
              autoComplete="off"
              placeholder="Display name (optional)"
              value={addName}
              onChange={e => setAddName(e.target.value)}
            />
            <input
              className="input-base"
              type="password"
              autoComplete="new-password"
              name="agentApiKey"
              aria-label="Agent API key"
              placeholder="Agent API key (optional)"
              value={addApiKey}
              onChange={e => setAddApiKey(e.target.value)}
            />
            <div className="text-[11px] text-fg-3 leading-relaxed">
              Use this to store an agent key on the dashboard server without exposing it back to the browser.
            </div>
            <button type="submit" className="btn btn-primary btn-sm w-full">
              Add Agent
            </button>
          </form>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {agents.length === 0 ? (
          <div className="p-4 text-center text-fg-3 text-[13px]">
            {isRefreshing ? 'Loading agents…' : 'No agents. Click Discover or + to add.'}
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {agents.map(agent => (
              <li
                key={agent.id}
                draggable={agent.status === 'online'}
                onDragStart={e => {
                  e.dataTransfer.setData('application/agent-id', agent.id)
                  e.dataTransfer.effectAllowed = 'copy'
                }}
                className={`px-3 py-2.5 hover:bg-surface-hover transition-colors group animate-agent-in ${
                  agent.status === 'online' ? 'cursor-grab active:cursor-grabbing' : ''
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 transition-colors ${
                        agent.status === 'online' ? 'bg-ok shadow-[0_0_6px_rgba(63,185,80,0.45)]' :
                        agent.status === 'offline' ? 'bg-err' : 'bg-fg-4'
                      }`}
                    />
                    <span className="text-[13px] truncate font-medium">
                      {agent.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSetKey(agent)}
                      className="text-fg-3 hover:text-accent active:scale-90"
                      aria-label={`Set API key for ${agent.name}`}
                      title="Set API key"
                    >
                      <i className="fa-solid fa-key text-[10px]" />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`Remove agent "${agent.name}"? Its stored API key is deleted too.`)) onRemove(agent.id)
                      }}
                      className="text-fg-3 hover:text-err active:scale-90 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                      aria-label={`Remove ${agent.name}`}
                      title="Remove agent"
                    >
                      <i className="fa-solid fa-xmark text-[11px]" />
                    </button>
                  </div>
                </div>
                <div
                  className="text-xs text-fg-3 mt-0.5 ml-3.5 truncate font-mono"
                  title={agent.tls_fingerprint ? `TLS certificate SHA-256 ${agent.tls_fingerprint}` : undefined}
                >
                  {agent.url.startsWith('https://')
                    ? <i className="fa-solid fa-lock text-[9px] mr-1" aria-label="TLS" />
                    : <i className="fa-solid fa-lock-open text-[9px] mr-1 text-warn" aria-label="No TLS" />}
                  {agent.url}
                </div>
                <AgentVersionLine
                  agent={agent}
                  latest={latestAgentVersion}
                  updating={updatingAgents.has(agent.id)}
                  onUpdate={() => onUpdateAgent(agent.id)}
                />
                {agent.tls_error && (
                  <div className="text-xs text-err mt-1 ml-3.5 flex items-center gap-2">
                    <span className="truncate">TLS: {agent.tls_error}</span>
                    {agent.tls_new_fingerprint && (
                      <button onClick={() => handleTrust(agent)} className="underline hover:text-accent shrink-0">
                        Review
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}