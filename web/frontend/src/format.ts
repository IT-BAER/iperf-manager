/** Shared throughput label so KPIs, live results, topology and reports read the same. */
export function formatMbps(mbps: number | null | undefined): string {
  if (mbps == null || !Number.isFinite(mbps)) return '—'
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  if (mbps >= 1) return `${mbps.toFixed(1)} Mbps`
  if (mbps > 0) return `${(mbps * 1000).toFixed(0)} Kbps`
  return '0 Mbps'
}

/** True when version a (x.y.z) is newer than b. */
export function isNewerVersion(a: string, b: string): boolean {
  const pa = a.split('.').map(Number)
  const pb = b.split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0)
  }
  return false
}
