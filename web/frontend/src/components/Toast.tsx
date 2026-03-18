import { useEffect, useState, useCallback } from 'react'

interface ToastItem {
  id: number
  msg: string
  type: 'info' | 'ok' | 'err'
  exiting?: boolean
}

let _id = 0

export function Toast() {
  const [items, setItems] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    // trigger exit animation first
    setItems(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t))
    setTimeout(() => {
      setItems(prev => prev.filter(t => t.id !== id))
    }, 180)
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { msg: string; type?: string }
      const item: ToastItem = { id: ++_id, msg: detail.msg, type: (detail.type as ToastItem['type']) || 'info' }
      setItems(prev => [...prev, item])
      setTimeout(() => dismiss(item.id), 4000)
    }
    window.addEventListener('toast', handler)
    return () => window.removeEventListener('toast', handler)
  }, [dismiss])

  if (items.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {items.map(item => (
        <div
          key={item.id}
          className={`pointer-events-auto px-4 py-2.5 rounded-sm border text-[13px] shadow-lg flex items-start gap-2
            ${item.exiting ? 'animate-toast-out' : 'animate-toast-in'}
            ${item.type === 'err'
              ? 'bg-surface border-err text-err'
              : item.type === 'ok'
              ? 'bg-surface border-ok text-ok'
              : 'bg-surface border-line text-fg-2'
            }`}
        >
          <span className="flex-1">{item.msg}</span>
          <button
            onClick={() => dismiss(item.id)}
            className="text-fg-4 hover:text-fg-2 shrink-0 active:scale-90 transition-transform"
            aria-label="Dismiss"
          ><i className="fa-solid fa-xmark text-[11px]" /></button>
        </div>
      ))}
    </div>
  )
}