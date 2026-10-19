import { useState } from 'react'
import { Card as PrimeCard } from 'primereact/card'
import { Message } from 'primereact/message'
import { SelectButton } from 'primereact/selectbutton'
import { useActivity, useStatus } from '../api/queries'
import type { ActivityScope } from '../api/types'
import { useTranslation } from 'react-i18next'
import { type Lang, useLang } from '../i18n'

const LEVEL_COLORS: Record<string, string> = {
  ERROR: '#c0392b',
  CRITICAL: '#c0392b',
  WARNING: '#b8860b',
}

export function formatUptime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

const LOCALES: Record<Lang, string> = { de: 'de-DE', en: 'en-GB' }
// Wide enough for "12/10/26, 10:12:03"; the traceback is indented by time and level.
const TIME_COLUMN = 140
const LEVEL_COLUMN = 70
const COLUMN_GAP = 12

/**
 * Local `HH:MM:SS` for an entry from today, a short local date plus time for an
 * older one: the activity log persists across days. `locale` and `timeZone`
 * default to the browser's; tests pass them for determinism.
 */
export function formatActivityTime(
  iso: string,
  now: Date = new Date(),
  locale?: string,
  timeZone?: string,
): string {
  const date = new Date(iso)
  const time = { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone } as const
  const day = { day: '2-digit', month: '2-digit', year: '2-digit', timeZone } as const
  if (date.toLocaleDateString(locale, day) === now.toLocaleDateString(locale, day)) {
    return date.toLocaleTimeString(locale, time)
  }
  return date.toLocaleString(locale, { ...day, ...time })
}

function Card({ kicker, children }: { kicker: string; children: React.ReactNode }) {
  return (
    // Prime's `Card` for the surface inside the artboard's blueprint frame:
    // the registration marks are `.blueprint > .corner`, direct children
    // only, and Card nests its content two levels down. The frame's border
    // and (soft-corner) rounding belong to the wrapper, so the card drops its
    // own radius. The kicker, title and meta lines keep the artboard's
    // classes, which Card's title slots do not match.
    <div className="blueprint">
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
      <PrimeCard
        style={{ height: '100%', borderRadius: 0 }}
        pt={{ content: { style: { display: 'flex', flexDirection: 'column', gap: 8 } } }}
      >
        <div className="card-kicker">{kicker}</div>
        {children}
      </PrimeCard>
    </div>
  )
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: ok ? '#2e9e6b' : '#c0392b',
        display: 'inline-block',
      }}
    />
  )
}

const SCOPES: ActivityScope[] = ['mine', 'service', 'all']

function ActivityPanel({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const lang = useLang()
  const [scope, setScope] = useState<ActivityScope>(isAdmin ? 'all' : 'mine')
  const activity = useActivity({ scope })
  const entries = activity.data ?? []
  const scopeLabel: Record<ActivityScope, string> = {
    mine: t('scopeMine'),
    service: t('scopeService'),
    all: t('scopeAll'),
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h4 style={{ margin: 0 }}>{isAdmin ? t('activity') : t('myActivity')}</h4>
        {/* `allowEmpty` off: the log always shows one scope. */}
        {isAdmin && (
          <SelectButton
            aria-label={t('activity')}
            value={scope}
            options={SCOPES.map((s) => ({ label: scopeLabel[s], value: s }))}
            allowEmpty={false}
            onChange={(event) => {
              if (event.value) setScope(event.value as ActivityScope)
            }}
          />
        )}
      </div>
      <div
        className="blueprint"
        style={{
          background: 'var(--color-surface)',
          padding: '10px 14px',
          fontFamily: 'ui-monospace, Menlo, monospace',
          fontSize: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          overflowX: 'auto',
        }}
      >
        <i className="corner tl" />
        <i className="corner tr" />
        <i className="corner bl" />
        <i className="corner br" />
        {entries.length === 0 && <span className="text-muted">{t('activityEmpty')}</span>}
        {entries.map((entry, i) => {
          const startsRun = entry.run_id !== null && entry.run_id !== entries[i - 1]?.run_id
          return (
            <div key={`${entry.timestamp}-${i}`}>
              {startsRun && (
                <div
                  data-testid="run-header"
                  className="text-muted"
                  style={{ marginTop: i ? 8 : 0, fontWeight: 500 }}
                >
                  {[entry.agent, entry.project_key].filter(Boolean).join(' · ')}
                </div>
              )}
              <div
                data-testid="activity-line"
                style={{
                  display: 'grid',
                  gridTemplateColumns: `${TIME_COLUMN}px ${LEVEL_COLUMN}px 1fr`,
                  gap: COLUMN_GAP,
                  whiteSpace: 'pre',
                }}
              >
                <span className="text-muted">
                  {formatActivityTime(entry.timestamp, undefined, LOCALES[lang])}
                </span>
                <span
                  style={{
                    color: LEVEL_COLORS[entry.level] ?? 'var(--color-accent-700)',
                    fontWeight: 500,
                  }}
                >
                  {entry.level}
                </span>
                <span>
                  {entry.scope === 'service' && (
                    <span data-testid="service-badge" className="text-muted">
                      [{t('serviceBadge')}]{' '}
                    </span>
                  )}
                  {entry.message}
                </span>
              </div>
              {entry.exc && (
                <details style={{ marginLeft: TIME_COLUMN + COLUMN_GAP + LEVEL_COLUMN }}>
                  <summary className="text-muted">{t('traceback')}</summary>
                  <pre style={{ margin: 0 }}>{entry.exc}</pre>
                </details>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function Status({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const status = useStatus()

  if (status.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (status.isError || !status.data) {
    // The primary line is always the translated fallback — never the raw
    // (often English, backend-shaped) error text — so this alert can never
    // show untranslated copy regardless of what threw. The raw message, if
    // any, is shown underneath only as diagnostic detail.
    const detail = (status.error as Error)?.message
    return (
      <div style={{ padding: 28 }}>
        <Message
          severity="error"
          style={{ justifyContent: 'flex-start' }}
          content={
            <div>
              <div>{t('statusError')}</div>
              {detail && <div style={{ fontSize: 12, marginTop: 4, opacity: 0.8 }}>{detail}</div>}
            </div>
          }
        />
      </div>
    )
  }

  const { service, testbench, api_keys, agents } = status.data

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t('status')}</h2>
        <span className="text-muted" style={{ fontSize: 13 }}>
          {t('statusSub')}
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 20,
        }}
      >
        <Card kicker={t('service')}>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Dot ok />
            {t('running')}
          </div>
          <div className="card-meta">
            {service.host}:{service.port} · v{service.version} ·{' '}
            {formatUptime(service.uptime_seconds)}
          </div>
        </Card>

        <Card kicker="TestBench">
          <div
            className="card-title"
            data-testid="tb-state"
            style={{ display: 'flex', alignItems: 'center', gap: 8 }}
          >
            <Dot ok={testbench.reachable} />
            {testbench.reachable ? t('connected') : t('notConnected')}
          </div>
          <div className="card-meta" style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
            {testbench.url}
          </div>
        </Card>

        <Card kicker={t('apiKeys')}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {api_keys.map((key) => (
              <div
                key={key.name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 12,
                  opacity: key.present ? 1 : 0.6,
                }}
              >
                <Dot ok={key.present} />
                <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{key.name}</span>
                <span className="text-muted">{key.present ? t('keySet') : t('keyMissing')}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card kicker={t('agents')}>
          <div className="card-title">
            {t('agentCount', { count: agents.total })}
          </div>
          <div className="card-meta">
            {agents.enabled} {t('agentsOn')} · {t('overrideCount', { count: agents.project_overrides })}
          </div>
        </Card>
      </div>

      <ActivityPanel isAdmin={isAdmin} />
    </div>
  )
}
