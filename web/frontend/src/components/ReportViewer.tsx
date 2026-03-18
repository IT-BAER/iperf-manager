import { useEffect, useState, useCallback } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import type { ChartData, ChartOptions } from 'chart.js'
import { parseCSV } from '../api'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

interface ReportViewerProps {
  filename: string
  onBack: () => void
}

type SortDir = 'asc' | 'desc'

function parseMbps(val: string): number {
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n / 1e6
}

function fmtMbps(bps: number): string {
  const mbps = bps / 1e6
  if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  return `${mbps.toFixed(1)} Mbps`
}

const MONO_COLS = new Set(['ts', 'on_up', 'on_dn', 'total_up', 'total_dn', 'wall'])

export default function ReportViewer({ filename, onBack }: ReportViewerProps) {
  const [columns, setColumns] = useState<string[]>([])
  const [rows, setRows] = useState<Record<string, string>[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortCol, setSortCol] = useState('')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`/api/reports/${encodeURIComponent(filename)}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.text()
      })
      .then(text => {
        const { columns: cols, rows: data } = parseCSV(text)
        setColumns(cols)
        setRows(data)
        setSortCol(cols[0] ?? '')
      })
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false))
  }, [filename])

  const handleDownload = useCallback(() => {
    const a = document.createElement('a')
    a.href = `/api/reports/${encodeURIComponent(filename)}`
    a.download = filename
    a.click()
  }, [filename])

  const handleSort = (col: string) => {
    if (sortCol === col) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortCol(col)
      setSortDir('asc')
    }
  }

  const sortedRows = [...rows].sort((a, b) => {
    if (!sortCol) return 0
    const av = a[sortCol] ?? ''
    const bv = b[sortCol] ?? ''
    const an = parseFloat(av)
    const bn = parseFloat(bv)
    const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : av.localeCompare(bv)
    return sortDir === 'asc' ? cmp : -cmp
  })

  // Summary stats
  const upVals = rows.map(r => parseFloat(r['on_up'] ?? r['total_up'] ?? '0')).filter(n => !isNaN(n))
  const dnVals = rows.map(r => parseFloat(r['on_dn'] ?? r['total_dn'] ?? '0')).filter(n => !isNaN(n))
  const peakUp = upVals.length ? Math.max(...upVals) : 0
  const peakDn = dnVals.length ? Math.max(...dnVals) : 0
  const avgUp = upVals.length ? upVals.reduce((s, v) => s + v, 0) / upVals.length : 0
  const avgDn = dnVals.length ? dnVals.reduce((s, v) => s + v, 0) / dnVals.length : 0

  // Chart
  const wallCol = columns.includes('wall') ? 'wall' : columns[0] ?? ''
  const upKey = columns.includes('on_up') ? 'on_up' : 'total_up'
  const dnKey = columns.includes('on_dn') ? 'on_dn' : 'total_dn'

  const lineData: ChartData<'line'> = {
    labels: rows.map(r => r[wallCol] ?? ''),
    datasets: [
      {
        label: 'Upload',
        data: rows.map(r => parseMbps(r[upKey] ?? '0')),
        borderColor: '#3ec96a',
        backgroundColor: 'rgba(62,201,106,0.07)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      },
      {
        label: 'Download',
        data: rows.map(r => parseMbps(r[dnKey] ?? '0')),
        borderColor: '#4b8df8',
        backgroundColor: 'rgba(75,141,248,0.07)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      },
    ],
  }

  const chartOptions: ChartOptions<'line'> = {
    responsive: true,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: '#9898a0', font: { size: 11 }, boxWidth: 12, padding: 12 } },
      tooltip: {
        backgroundColor: '#19191d',
        borderColor: '#232328',
        borderWidth: 1,
        titleColor: '#9898a0',
        bodyColor: '#e8e8ec',
        padding: 8,
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(35,35,40,0.6)' },
        ticks: { color: '#6a6a74', font: { size: 10 }, maxTicksLimit: 10 },
      },
      y: {
        grid: { color: 'rgba(35,35,40,0.6)' },
        ticks: { color: '#6a6a74', font: { size: 10 } },
        beginAtZero: true,
      },
    },
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Panel header */}
      <div className="panel">
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <h2 className="text-[14px] font-semibold font-mono text-fg">{filename}</h2>
            <p className="text-[12px] text-fg-3 mt-0.5">{rows.length} data points</p>
          </div>
          <div className="flex gap-2">
            <button className="btn" onClick={onBack}>Back</button>
            <button className="btn btn-primary" onClick={handleDownload}>Download</button>
          </div>
        </div>
      </div>

      {loading && (
        <div className="panel p-8 flex items-center justify-center text-[13px] text-fg-3">
          Loading report…
        </div>
      )}

      {error && (
        <div className="panel px-4 py-3 text-[13px] text-err border-l-2 border-l-err">
          Failed to load: {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Data Points', value: rows.length.toString(), color: 'text-fg' },
              { label: 'Peak Upload', value: fmtMbps(peakUp), color: 'text-ok' },
              { label: 'Peak Download', value: fmtMbps(peakDn), color: 'text-accent' },
              { label: 'Avg Throughput', value: fmtMbps(avgUp + avgDn), color: 'text-warn' },
            ].map(c => (
              <div
                key={c.label}
                className="bg-surface border border-line rounded p-4 hover:border-line-bright transition-colors duration-150"
              >
                <div className={`text-2xl font-bold font-mono tabular leading-none ${c.color}`}>
                  {c.value}
                </div>
                <div className="text-[11px] font-medium uppercase tracking-wider text-fg-3 mt-1.5">
                  {c.label}
                </div>
              </div>
            ))}
          </div>

          {/* Chart */}
          <div className="panel p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-fg-3 mb-3">
              Throughput Over Time (Mbps)
            </div>
            <Line data={lineData} options={chartOptions} />
          </div>

          {/* Data table */}
          <div className="panel overflow-hidden">
            <div className="px-4 py-3 border-b border-line flex items-center justify-between">
              <span className="text-[13px] font-semibold text-fg">Raw Data</span>
              <span className="text-[12px] font-mono text-fg-3">{rows.length} rows × {columns.length} cols</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-line">
                    {columns.map(col => (
                      <th
                        key={col}
                        className="text-left px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-fg-3 cursor-pointer hover:text-fg transition-colors duration-150 select-none whitespace-nowrap bg-surface-raised"
                        onClick={() => handleSort(col)}
                      >
                        <span>{col}</span>
                        {sortCol === col && (
                          <span className="ml-1 text-accent">{sortDir === 'asc' ? '▲' : '▼'}</span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-line/40 hover:bg-surface-hover transition-colors duration-150 last:border-b-0"
                    >
                      {columns.map(col => (
                        <td
                          key={col}
                          className={`px-3 py-1.5 text-fg-2 whitespace-nowrap ${MONO_COLS.has(col) ? 'font-mono' : ''}`}
                        >
                          {row[col] ?? ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}