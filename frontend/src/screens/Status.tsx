import { useLogs, useStatus } from '../api/queries'
import { useTranslations, type Lang } from '../i18n'

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

function Card({ kicker, children }: { kicker: string; children: React.ReactNode }) {
  return (
    <div className="card blueprint" style={{ padding: 16 }}>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
      <div className="card-kicker">{kicker}</div>
      {children}
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

export function Status({ lang }: { lang: Lang }) {
  const t = useTranslations(lang)
  const status = useStatus()
  const logs = useLogs()

  if (status.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (status.isError || !status.data) {
    // The primary line is always the translated fallback — never the raw
    // (often English, backend-shaped) error text — so this alert can never
    // show untranslated copy regardless of what threw. The raw message, if
    // any, is shown underneath only as diagnostic detail.
    const detail = (status.error as Error)?.message
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t.statusError}</div>
        {detail && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
            {detail}
          </div>
        )}
      </div>
    )
  }

  const { service, testbench, api_keys, agents, log_file } = status.data

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        maxWidth: 1200,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t.status}</h2>
        <span className="text-muted" style={{ fontSize: 13 }}>
          {t.statusSub}
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 20,
        }}
      >
        <Card kicker={t.service}>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Dot ok />
            {t.running}
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
            {testbench.reachable ? t.connected : t.notConnected}
          </div>
          <div className="card-meta" style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
            {testbench.url}
          </div>
        </Card>

        <Card kicker={t.apiKeys}>
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
                <span className="text-muted">{key.present ? t.keySet : t.keyMissing}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card kicker={t.agents}>
          <div className="card-title">
            {agents.total} {t.agents}
          </div>
          <div className="card-meta">
            {agents.enabled} {t.agentsOn} · {agents.project_overrides} {t.overrides}
          </div>
        </Card>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h4 style={{ margin: 0 }}>{t.recentLog}</h4>
          <span
            className="text-muted"
            style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
          >
            {log_file}
          </span>
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
          {(logs.data ?? []).map((line) => (
            <div
              key={line.raw}
              data-testid="log-line"
              // The artboard's four fixed tracks: time, level, source, message.
              // A grid keeps the messages on one left edge, which a flex row
              // with per-cell minimums only manages until one source is long.
              style={{
                display: 'grid',
                gridTemplateColumns: '70px 70px 240px 1fr',
                gap: 12,
                whiteSpace: 'pre',
              }}
            >
              <span className="text-muted">{line.timestamp?.slice(11) ?? ''}</span>
              <span
                style={{
                  color: LEVEL_COLORS[line.level ?? ''] ?? 'var(--color-accent-700)',
                  fontWeight: 500,
                }}
              >
                {line.level ?? ''}
              </span>
              <span className="text-muted">{line.source ?? ''}</span>
              <span>{line.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
