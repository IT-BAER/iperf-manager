import { useState } from 'react'
import type { Agent } from '../types'

interface Props {
  open: boolean
  agents: Agent[]
  onRefresh: () => void
  onAdd: (url: string, name: string, apiKey: string) => void
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

export function Sidebar({ open, agents, onRefresh, onAdd, onRemove, onDiscover, isDiscovering, isRefreshing }: Props) {
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
              placeholder="http://host:9001"
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
            No agents. Click Discover or + to add.
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
                  <button
                    onClick={() => onRemove(agent.id)}
                    className="opacity-0 group-hover:opacity-100 text-fg-3 hover:text-err transition-opacity active:scale-90"
                    aria-label={`Remove ${agent.name}`}
                  >
                    <i className="fa-solid fa-xmark text-[11px]" />
                  </button>
                </div>
                <div className="text-xs text-fg-3 mt-0.5 ml-3.5 truncate font-mono">
                  {agent.url}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}