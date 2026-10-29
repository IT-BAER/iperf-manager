/** Shared throughput label so KPIs, live results, topology and reports read the same. */
export function formatMbps(mbps: number | null | undefined): string {
  if (mbps == null || !Number.isFinite(mbps)) return '—'
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  if (mbps >= 1) return `${mbps.toFixed(1)} Mbps`
  if (mbps > 0) return `${(mbps * 1000).toFixed(0)} Kbps`
  return '0 Mbps'
}
