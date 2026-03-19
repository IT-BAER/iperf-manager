import { useState } from 'react'

interface AuthPanelProps {
  loading?: boolean
  onSubmit: (username: string, password: string) => Promise<void>
}

export function AuthPanel({ loading, onSubmit }: AuthPanelProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  return (
    <div className="min-h-screen bg-bg text-fg flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md panel overflow-hidden shadow-[0_18px_60px_rgba(0,0,0,0.35)]">
        <div className="border-b border-line px-6 py-5 bg-surface-raised">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent mb-2">
            Protected Dashboard
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Sign in to iperf-manager</h1>
          <p className="text-[13px] text-fg-3 mt-2 leading-relaxed">
            Use the dashboard administrator credentials configured on the server. The session stays server-side and uses a secure cookie.
          </p>
        </div>

        <form
          className="px-6 py-6 space-y-4"
          onSubmit={async event => {
            event.preventDefault()
            await onSubmit(username.trim(), password)
          }}
        >
          <div>
            <label htmlFor="dashboard-username" className="block text-[12px] font-medium text-fg-2 mb-1.5">
              Username
            </label>
            <input
              id="dashboard-username"
              name="username"
              className="input-base h-10"
              autoComplete="username"
              value={username}
              onChange={event => setUsername(event.target.value)}
              disabled={loading}
            />
          </div>

          <div>
            <label htmlFor="dashboard-password" className="block text-[12px] font-medium text-fg-2 mb-1.5">
              Password
            </label>
            <input
              id="dashboard-password"
              name="current-password"
              className="input-base h-10"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={event => setPassword(event.target.value)}
              disabled={loading}
            />
          </div>

          <button type="submit" className="btn btn-primary w-full h-10" disabled={loading || !username.trim() || !password}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}