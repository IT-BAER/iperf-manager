import { useEffect, useRef, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'

export function useSocket() {
  const ref = useRef<Socket | null>(null)

  useEffect(() => {
    const s = io({ transports: ['websocket', 'polling'] })
    ref.current = s
    return () => { s.disconnect() }
  }, [])

  const on = useCallback((ev: string, fn: (...args: unknown[]) => void) => {
    ref.current?.on(ev, fn)
    return () => { ref.current?.off(ev, fn) }
  }, [])

  const emit = useCallback((ev: string, data?: unknown) => {
    ref.current?.emit(ev, data)
  }, [])

  return { on, emit }
}
