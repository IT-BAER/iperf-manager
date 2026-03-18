import { useState } from 'react'
import type { Agent } from '../types'

interface Props {
  open: boolean
  agents: Agent[]
  onRefresh: () => void
  onAdd: (url: string, name: string) => void
  onRemove: (id: string) => void
  onDiscover: () => void
}

export function Sidebar({ open, agents, onRefresh, onAdd, onRemove, onDiscover }: Props) {
  const [addUrl, setAddUrl] = useState('')
  const [addName, setAddName] = useState('')
  const [showAdd, setShowAdd] = useState(false)

  const handleAdd = () => {
    if (!addUrl.trim()) return
    onAdd(addUrl.trim(), addName.trim() || addUrl.trim())
    setAddUrl('')
    setAddName('')
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
          <button onClick={onDiscover} className="btn btn-sm flex-1">Discover</button>
          <button onClick={onRefresh} className="btn btn-sm flex-1">Refresh</button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="btn btn-sm w-7 px-0 justify-center"
            aria-label="Add agent manually"
          >+</button>
        </div>
      </div>

      {showAdd && (
        <div className="p-3 border-b border-line bg-surface-raised space-y-2">
          <input
            className="input-base"
            placeholder="http://host:9001"
            value={addUrl}
            onChange={e => setAddUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
          />
          <input
            className="input-base"
            placeholder="Display name (optional)"
            value={addName}
            onChange={e => setAddName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
          />
          <button onClick={handleAdd} className="btn btn-primary btn-sm w-full">
            Add Agent
          </button>
        </div>
      )}

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
                className="px-3 py-2.5 hover:bg-surface-hover transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        agent.status === 'online' ? 'bg-ok' :
                        agent.status === 'offline' ? 'bg-err' : 'bg-fg-4'
                      }`}
                    />
                    <span className="text-[13px] truncate font-medium">
                      {agent.name}
                    </span>
                  </div>
                  <button
                    onClick={() => onRemove(agent.id)}
                    className="opacity-0 group-hover:opacity-100 text-fg-3 hover:text-err text-xs transition-opacity"
                    aria-label={`Remove ${agent.name}`}
                  >
                    ✕
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