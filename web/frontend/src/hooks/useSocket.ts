import { useEffect, useRef, useCallback, useState } from 'react'
import { io } from 'socket.io-client'
import type { Socket } from 'socket.io-client'

export function useSocket(enabled = true) {
  const ref = useRef<Socket | null>(null)
  const [socket, setSocket] = useState<Socket | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!enabled) {
      ref.current?.disconnect()
      ref.current = null
      setSocket(null)
      setConnected(false)
      return
    }

    const s = io({
      path: '/socket.io',
      transports: ['polling'],
      withCredentials: true,
    })
    ref.current = s
    setSocket(s)
    s.on('connect', () => setConnected(true))
    s.on('disconnect', () => setConnected(false))
    s.on('connect_error', error => {
      setConnected(false)
      if (error.message.toLowerCase().includes('unauthorized')) {
        window.dispatchEvent(new CustomEvent('auth-required'))
      }
    })
    return () => {
      s.disconnect()
      if (ref.current === s) ref.current = null
      setSocket(current => current === s ? null : current)
    }
  }, [enabled])

  const on = useCallback((ev: string, fn: (...args: unknown[]) => void) => {
    socket?.on(ev, fn)
    return () => { socket?.off(ev, fn) }
  }, [socket])

  const emit = useCallback((ev: string, data?: unknown) => {
    socket?.emit(ev, data)
  }, [socket])

  return { on, emit, connected }
}