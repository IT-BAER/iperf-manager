import { useEffect, useMemo, useState } from 'react'
import type { Profile, ScheduledTest, ScheduleSource, TestConfig } from '../types'

interface CreateSchedulePayload {
  name: string
  cron: string
  source: ScheduleSource
  profile_name?: string
  config?: TestConfig
}

interface Props {
  schedules: ScheduledTest[]
  profiles: Profile[]
  activeProfile: string
  draftConfig: TestConfig | null
  isRunning: boolean
  onCreate: (payload: CreateSchedulePayload) => Promise<void>
  onToggleEnabled: (schedule: ScheduledTest, enabled: boolean) => Promise<void>
  onRunNow: (schedule: ScheduledTest) => Promise<void>
  onDelete: (schedule: ScheduledTest) => Promise<void>
}

function fmtTs(ts: number | null): string {
  if (!ts) return '—'
  const dt = new Date(ts * 1000)
  if (Number.isNaN(dt.getTime())) return '—'
  return dt.toLocaleString()
}

export default function SchedulePanel({
  schedules,
  profiles,
  activeProfile,
  draftConfig,
  isRunning,
  onCreate,
  onToggleEnabled,
  onRunNow,
  onDelete,
}: Props) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [cron, setCron] = useState('*/30 * * * *')
  const [source, setSource] = useState<ScheduleSource>('profile')
  const [profileName, setProfileName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!profileName && activeProfile) {
      setProfileName(activeProfile)
    }
  }, [activeProfile, profileName])

  const hasProfiles = profiles.length > 0
  const canCreate = useMemo(() => {
    if (!name.trim()) return false
    if (!cron.trim()) return false
    if (source === 'profile') return Boolean(profileName.trim())
    return Boolean(draftConfig)
  }, [name, cron, source, profileName, draftConfig])

  const submit = async () => {
    if (!canCreate) return
    const payload: CreateSchedulePayload = {
      name: name.trim(),
      cron: cron.trim(),
      source,
    }

    if (source === 'profile') {
      payload.profile_name = profileName.trim()
    } else if (draftConfig) {
      payload.config = draftConfig
    }

    setCreating(true)
    try {
      await onCreate(payload)
      setName('')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="panel">
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-line cursor-pointer select-none hover:bg-surface-hover transition-colors duration-150"
        onClick={() => setOpen(v => !v)}
      >
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-semibold text-fg">Scheduled Tests</span>
          <span className="text-[12px] text-fg-3">{schedules.length} configured</span>
        </div>
        <span className={`text-fg-3 text-lg leading-none transition-transform duration-150 ${open ? '' : '-rotate-90'}`}>
          ▾
        </span>
      </div>

      <div className={`collapsible-grid ${open ? 'open' : 'closed'}`}>
        <div className="collapsible-inner">
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-[1.3fr_1fr_1fr_1fr_auto] gap-3 items-end">
              <div>
                <label className="block text-[12px] font-medium text-fg-2 mb-1">Schedule Name</label>
                <input
                  className="input-base"
                  placeholder="e.g. Nightly uplink test"
                  value={name}
                  onChange={e => setName(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium text-fg-2 mb-1">Cron</label>
                <input
                  className="input-base"
                  placeholder="*/30 * * * *"
                  value={cron}
                  onChange={e => setCron(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium text-fg-2 mb-1">Source</label>
                <select
                  className="input-base"
                  value={source}
                  onChange={e => setSource((e.target.value as ScheduleSource) || 'profile')}
                >
                  <option value="profile">Profile</option>
                  <option value="manual">Manual Snapshot</option>
                </select>
              </div>
              <div>
                <label className="block text-[12px] font-medium text-fg-2 mb-1">
                  {source === 'profile' ? 'Profile' : 'Manual Config'}
                </label>
                {source === 'profile' ? (
                  <select
                    className="input-base"
                    value={profileName}
                    onChange={e => setProfileName(e.target.value)}
                    disabled={!hasProfiles}
                  >
                    <option value="">Select profile...</option>
                    {profiles.map(profile => (
                      <option key={profile.name} value={profile.name}>{profile.name}</option>
                    ))}
                  </select>
                ) : (
                  <div className="h-8 px-3 rounded-sm border border-line bg-bg text-[12px] text-fg-2 flex items-center">
                    {draftConfig ? 'Using current Test Configuration' : 'No draft config available'}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="btn btn-primary h-8"
                disabled={!canCreate || creating || isRunning}
                onClick={submit}
              >
                {creating ? 'Adding…' : 'Add Schedule'}
              </button>
            </div>

            <div className="text-[11px] text-fg-3">
              Cron format: minute hour day month weekday. Example: <span className="font-mono">0 2 * * *</span> runs daily at 02:00.
            </div>

            {schedules.length === 0 ? (
              <div className="text-[12px] text-fg-3">No schedules yet.</div>
            ) : (
              <div className="space-y-2">
                {schedules.map(schedule => (
                  <div key={schedule.id} className="rounded-sm border border-line bg-bg px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="text-[13px] font-semibold text-fg flex-1">{schedule.name}</div>
                      <span className={`text-[11px] px-2 py-0.5 rounded border ${schedule.enabled ? 'text-ok border-ok/40 bg-ok-subtle' : 'text-fg-3 border-line bg-surface-raised'}`}>
                        {schedule.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                      <span className="text-[11px] px-2 py-0.5 rounded border border-line bg-surface-raised text-fg-2">
                        {schedule.source === 'profile' ? `Profile: ${schedule.profile_name || '—'}` : 'Manual Snapshot'}
                      </span>
                    </div>

                    <div className="mt-1 text-[12px] text-fg-3 font-mono">{schedule.cron}</div>

                    {schedule.source === 'manual' && schedule.manual_summary && (
                      <div className="mt-1 text-[11px] text-fg-3">
                        server={schedule.manual_summary.server_agent || '—'} | clients={schedule.manual_summary.client_count} | duration={schedule.manual_summary.duration_sec}s
                      </div>
                    )}

                    <div className="mt-2 grid grid-cols-[1fr_1fr_1fr_auto] gap-3 items-center">
                      <div className="text-[11px] text-fg-3">Next: {fmtTs(schedule.next_run_at)}</div>
                      <div className="text-[11px] text-fg-3">Last: {fmtTs(schedule.last_run_at)}</div>
                      <div className="text-[11px] text-fg-3 truncate">Result: {schedule.last_result || '—'}</div>
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => onToggleEnabled(schedule, !schedule.enabled)}
                        >
                          {schedule.enabled ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={isRunning}
                          onClick={() => onRunNow(schedule)}
                        >
                          Run now
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => onDelete(schedule)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
