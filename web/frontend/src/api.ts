class AuthRequiredError extends Error {
  constructor() {
    super('Authentication required')
    this.name = 'AuthRequiredError'
  }
}

interface ApiOptions extends RequestInit {
  onUnauthorized?: 'auth-required' | 'error'
}

export async function api<T = unknown>(url: string, opts: ApiOptions = {}): Promise<T | null> {
  try {
    const { onUnauthorized = 'auth-required', headers, ...requestInit } = opts
    const r = await fetch(url, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...headers as Record<string, string> },
      ...requestInit,
    })
    if (r.status === 401 && onUnauthorized === 'auth-required') {
      window.dispatchEvent(new CustomEvent('auth-required'))
      throw new AuthRequiredError()
    }
    if (!r.ok) {
      const b = await r.json().catch(() => ({}))
      throw new Error((b as { error?: string }).error || `HTTP ${r.status}`)
    }
    return await r.json() as T
  } catch (e) {
    if (e instanceof AuthRequiredError) return null
    const msg = e instanceof Error ? e.message : 'Network error'
    window.dispatchEvent(new CustomEvent('toast', { detail: { msg, type: 'err' } }))
    return null
  }
}

export function parseCSV(text: string): { columns: string[]; rows: Record<string, string>[] } {
  const lines = text.trim().split('\n')
  if (lines.length < 1) return { columns: [], rows: [] }
  const columns = lines[0].split(',').map(c => c.trim())
  const rows = lines.slice(1).map(line => {
    const vals = line.split(',')
    const row: Record<string, string> = {}
    columns.forEach((col, i) => { row[col] = (vals[i] || '').trim() })
    return row
  })
  return { columns, rows }
}
