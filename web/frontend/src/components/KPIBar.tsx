import type { Agent, TestState, Metrics } from '../types'

interface Props {
  agents: Agent[]
  testState: TestState
  latest: Metrics | null
}

function fmt(val: number): string {
  if (val >= 1000) return (val / 1000).toFixed(1) + ' Gbps'
  if (val >= 1) return val.toFixed(1) + ' Mbps'
  return (val * 1000).toFixed(0) + ' Kbps'
}

export function KPIBar({ agents, testState, latest }: Props) {
  const online = agents.filter(a => a.status === 'online').length

  const cards = [
    {
      label: 'Agents Online',
      value: `${online}/${agents.length}`,
      color: online > 0 ? 'text-ok' : 'text-fg-3',
    },
    {
      label: 'Test Status',
      value: testState.status === 'running' ? 'Running' : testState.status === 'stopping' ? 'Stopping' : 'Idle',
      color: testState.status === 'running' ? 'text-ok' : testState.status === 'stopping' ? 'text-warn' : 'text-fg-3',
    },
    {
      label: 'Upload',
      value: latest ? fmt(latest.total_up) : '—',
      color: 'text-accent',
    },
    {
      label: 'Download',
      value: latest ? fmt(latest.total_dn) : '—',
      color: 'text-accent',
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map(card => (
        <div key={card.label} className="panel px-4 py-3">
          <div className="text-[11px] font-medium text-fg-3 uppercase tracking-wider mb-1">
            {card.label}
          </div>
          <div className={`text-xl font-semibold tabular ${card.color}`}>
            {card.value}
          </div>
        </div>
      ))}
    </div>
  )
}