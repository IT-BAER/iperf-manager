import { useRef, useEffect, useState } from 'react'
import type { LogEntry } from '../types'

interface Props {
  logs: LogEntry[]
  onClear: () => void
}

export function LogPanel({ logs, onClear }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(true)

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length, open])

  const colorClass = (type: LogEntry['type']) => {
    switch (type) {
      case 'ok': return 'text-ok'
      case 'err': return 'text-err'
      case 'info': return 'text-accent'
      default: return 'text-fg-2'
    }
  }

  return (
    <div className="panel">
      <div
        className="px-4 py-3 border-b border-line flex items-center justify-between cursor-pointer select-none hover:bg-surface-hover transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-2.5">
          <h3 className="text-sm font-semibold">Log</h3>
          {logs.length > 0 && (
            <span className="text-[11px] font-mono text-fg-4">{logs.length}</span>
          )}
        </div>
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          <button onClick={onClear} className="btn btn-sm" disabled={logs.length === 0}>Clear</button>
          <span className={`text-fg-3 text-sm transition-transform duration-150 ${open ? '' : '-rotate-90'}`}>▾</span>
        </div>
      </div>
      {open && (
        <div className="h-44 overflow-y-auto p-3 font-mono text-[12px] leading-5 bg-bg">
          {logs.length === 0 ? (
            <span className="text-fg-3">No log entries.</span>
          ) : (
            logs.map((entry, i) => (
              <div key={i} className={colorClass(entry.type)}>
                <span className="text-fg-4 select-none mr-2 tabular">
                  [{new Date(entry.ts).toLocaleTimeString()}]
                </span>
                {entry.msg}
              </div>
            ))
          )}
          <div ref={endRef} />
        </div>
      )}
    </div>
  )
}