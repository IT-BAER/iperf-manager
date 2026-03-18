import { useEffect, useRef, useCallback, useState } from 'react'
import { io } from 'socket.io-client'
import type { Socket } from 'socket.io-client'

export function useSocket() {
  const ref = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const s = io({ path: '/socket.io', transports: ['polling', 'websocket'] })
    ref.current = s
    s.on('connect', () => setConnected(true))
    s.on('disconnect', () => setConnected(false))
    return () => { s.disconnect() }
  }, [])

  const on = useCallback((ev: string, fn: (...args: unknown[]) => void) => {
    ref.current?.on(ev, fn)
    return () => { ref.current?.off(ev, fn) }
  }, [])

  const emit = useCallback((ev: string, data?: unknown) => {
    ref.current?.emit(ev, data)
  }, [])

  return { on, emit, connected }
}