import { useEffect, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line, Bar } from 'react-chartjs-2'
import type { ChartOptions, ChartData } from 'chart.js'
import type { TestState, Metrics } from '../types'

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, Title, Tooltip, Legend, Filler
)

interface MetricPoint { ts: number; up: number; dn: number }

interface LiveResultsProps {
  testState: TestState
  metrics: Metrics | null
  metricsHistory: MetricPoint[]
}

function formatBps(mbps: number): string {
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  if (mbps >= 1) return `${mbps.toFixed(1)} Mbps`
  if (mbps >= 0.001) return `${(mbps * 1000).toFixed(0)} Kbps`
  return `${mbps.toFixed(0)} Mbps`
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`
}

const CHART_COLORS = {
  ok: '#3ec96a',
  okFill: 'rgba(62,201,106,0.07)',
  accent: '#4b8df8',
  accentFill: 'rgba(75,141,248,0.07)',
  grid: 'rgba(35,35,40,0.6)',
  tick: '#6a6a74',
  legend: '#9898a0',
}

function buildLineOptions(): ChartOptions<'line'> {
  return {
    responsive: true,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: CHART_COLORS.legend, font: { size: 11 }, boxWidth: 12, padding: 12 } },
      tooltip: {
        backgroundColor: '#19191d',
        borderColor: '#232328',
        borderWidth: 1,
        titleColor: CHART_COLORS.legend,
        bodyColor: '#e8e8ec',
        padding: 8,
      },
    },
    scales: {
      x: {
        grid: { color: CHART_COLORS.grid },
        ticks: { color: CHART_COLORS.tick, font: { size: 10 }, maxTicksLimit: 8 },
      },
      y: {
        grid: { color: CHART_COLORS.grid },
        ticks: { color: CHART_COLORS.tick, font: { size: 10 } },
        beginAtZero: true,
      },
    },
  }
}

function buildBarOptions(): ChartOptions<'bar'> {
  return {
    responsive: true,
    animation: false,
    plugins: {
      legend: { labels: { color: CHART_COLORS.legend, font: { size: 11 }, boxWidth: 12, padding: 12 } },
      tooltip: {
        backgroundColor: '#19191d',
        borderColor: '#232328',
        borderWidth: 1,
        titleColor: CHART_COLORS.legend,
        bodyColor: '#e8e8ec',
        padding: 8,
      },
    },
    scales: {
      x: {
        grid: { color: CHART_COLORS.grid },
        ticks: { color: CHART_COLORS.tick, font: { size: 10 } },
      },
      y: {
        grid: { color: CHART_COLORS.grid },
        ticks: { color: CHART_COLORS.tick, font: { size: 10 } },
        beginAtZero: true,
      },
    },
  }
}

export default function LiveResults({ testState, metrics, metricsHistory }: LiveResultsProps) {
  const [open, setOpen] = useState(true)
  const [nowMs, setNowMs] = useState(Date.now())
  const isRunning = testState.status === 'running'

  useEffect(() => {
    if (!isRunning) return
    const t = setInterval(() => setNowMs(Date.now()), 500)
    return () => clearInterval(t)
  }, [isRunning])

  const duration = testState.config?.duration_sec ?? 0
  const startedMs = testState.started_at ? testState.started_at * 1000 : nowMs
  const finishedMs = testState.finished_at ? testState.finished_at * 1000 : null
  const elapsedMs = isRunning
    ? Math.max(0, nowMs - startedMs)
    : finishedMs
      ? Math.max(0, finishedMs - startedMs)
      : 0
  const progress = duration > 0 ? Math.min(100, (elapsedMs / 1000 / duration) * 100) : 0

  const totalUp = metrics?.total_up ?? 0
  const totalDn = metrics?.total_dn ?? 0

  // Throughput line chart
  const lineLabels = metricsHistory.map(p => {
    const d = new Date(p.ts * 1000)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
  })
  const lineData: ChartData<'line'> = {
    labels: lineLabels,
    datasets: [
      {
        label: 'Upload',
        data: metricsHistory.map(p => p.up),
        borderColor: CHART_COLORS.ok,
        backgroundColor: CHART_COLORS.okFill,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      },
      {
        label: 'Download',
        data: metricsHistory.map(p => p.dn),
        borderColor: CHART_COLORS.accent,
        backgroundColor: CHART_COLORS.accentFill,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      },
    ],
  }

  // Per-agent bar chart
  const agentIds = metrics ? Object.keys(metrics.clients) : []
  const barData: ChartData<'bar'> = {
    labels: agentIds,
    datasets: [
      {
        label: 'Upload',
        data: agentIds.map(id => metrics?.clients[id]?.up ?? 0),
        backgroundColor: 'rgba(62,201,106,0.7)',
        borderColor: CHART_COLORS.ok,
        borderWidth: 1,
      },
      {
        label: 'Download',
        data: agentIds.map(id => metrics?.clients[id]?.dn ?? 0),
        backgroundColor: 'rgba(75,141,248,0.7)',
        borderColor: CHART_COLORS.accent,
        borderWidth: 1,
      },
    ],
  }

  const lineOptions = buildLineOptions()
  const barOptions = buildBarOptions()

  return (
    <div className="panel">
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-line cursor-pointer select-none hover:bg-surface-hover transition-colors duration-150"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-semibold text-fg">Live Results</span>
          <span className={`w-2 h-2 rounded-full ${testState.status === 'running' ? 'bg-ok' : 'bg-warn'}`} />
          <span className="text-[12px] text-fg-3 capitalize">{testState.status}</span>
        </div>
        <i className={`fa-solid fa-chevron-down text-fg-3 text-[11px] transition-transform duration-150 ${open ? '' : '-rotate-90'}`} />
      </div>

      <div className={`collapsible-grid ${open ? 'open' : 'closed'}`}>
        <div className="collapsible-inner">
          <div className="p-4 flex flex-col gap-4">
          {/* Progress */}
          {duration > 0 && (
            <div className="flex items-center gap-3">
              <div className="flex-1 h-[3px] bg-surface-active rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-[12px] font-mono text-fg-3 tabular w-10 text-right">
                {Math.round(progress)}%
              </span>
            </div>
          )}

          {/* Metric cards */}
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-surface-raised border border-line rounded p-3">
              <div className="text-[22px] font-bold font-mono tabular leading-none text-ok">
                {formatBps(totalUp)}
              </div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-fg-3 mt-1.5">Upload</div>
            </div>
            <div className="bg-surface-raised border border-line rounded p-3">
              <div className="text-[22px] font-bold font-mono tabular leading-none text-accent">
                {formatBps(totalDn)}
              </div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-fg-3 mt-1.5">Download</div>
            </div>
            <div className="bg-surface-raised border border-line rounded p-3">
              <div className="text-[22px] font-bold font-mono tabular leading-none text-warn">
                {formatBps(totalUp + totalDn)}
              </div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-fg-3 mt-1.5">Total</div>
            </div>
            <div className="bg-surface-raised border border-line rounded p-3">
              <div className="text-[22px] font-bold font-mono tabular leading-none text-fg-2">
                {formatElapsed(elapsedMs)}
              </div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-fg-3 mt-1.5">Elapsed</div>
            </div>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-surface-raised border border-line rounded p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-fg-3 mb-2">
                Throughput (Mbps)
              </div>
              <Line data={lineData} options={lineOptions} />
            </div>
            <div className="bg-surface-raised border border-line rounded p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-fg-3 mb-2">
                Per-Agent (Mbps)
              </div>
              <Bar data={barData} options={barOptions} />
            </div>
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}