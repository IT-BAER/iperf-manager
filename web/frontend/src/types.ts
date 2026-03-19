export interface Agent {
  id: string
  url: string
  name: string
  status: 'online' | 'offline' | 'unknown'
  last_seen: number | null
  details: Record<string, unknown>
}

export interface TestState {
  status: 'idle' | 'running' | 'stopping'
  started_at?: number
  finished_at?: number
  config?: TestConfig
  last_csv?: string
}

export interface AuthSession {
  enabled: boolean
  authenticated: boolean
  username: string
}

export interface TestConfig {
  server_agent: string
  server_bind: string
  api_key: string
  duration_sec: number
  base_port: number
  poll_interval_sec: number
  protocol: 'tcp' | 'udp'
  parallel: number
  omit_sec: number
  bitrate: string
  tcp_window: string
  mode: string
  clients: ClientRow[]
}

export interface ClientRow {
  agent: string
  name: string
  server_target: string
  bind: string
  api_key: string
}

export interface Metrics {
  timestamp: number
  clients: Record<string, { up: number; dn: number; jitter?: number; loss?: number }>
  total_up: number
  total_dn: number
}

export interface Report {
  name: string
  size: number
  modified: number
}

export interface Profile {
  name: string
  file: string
}

export interface LogEntry {
  ts: number
  msg: string
  type: 'info' | 'ok' | 'err' | ''
}

export interface ReportRow {
  ts: string
  wall: string
  on_up: string
  on_dn: string
  total_up: string
  total_dn: string
  [key: string]: string
}
