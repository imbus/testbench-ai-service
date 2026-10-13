import { BrandMark } from './BrandMark'
import { LangSeg } from './LangSeg'
import { ThemeButton } from './ThemeButton'
import { useTranslation } from 'react-i18next'
import type { Theme } from '../theme'
import type { SessionInfo } from '../api/types'

interface TopBarProps {
  session: SessionInfo
  theme: Theme
  /** Where the service itself answers, as `host:port`. Absent until /status lands. */
  serviceLabel?: string
  onToggleTheme: () => void
  onSignOut: () => void
}

export function TopBar({
  session,
  theme,
  serviceLabel,
  onToggleTheme,
  onSignOut,
}: TopBarProps) {
  const { t } = useTranslation()
  return (
    <header
      style={{
        height: 52,
        flex: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '0 16px',
        borderBottom: '1px solid var(--color-divider)',
        background: 'var(--color-bg)',
        // The nav rail below sticks to `top: 52`, which only holds if the bar
        // above it stays put too.
        position: 'sticky',
        top: 0,
        zIndex: 5,
      }}
    >
      <BrandMark size="header" />
      {serviceLabel && (
        <span
          className="text-muted"
          style={{
            fontSize: 12,
            fontFamily: 'ui-monospace, Menlo, monospace',
            whiteSpace: 'nowrap',
          }}
        >
          {serviceLabel}
        </span>
      )}
      <div style={{ flex: 1 }} />
      <LangSeg compact />
      <ThemeButton theme={theme} onToggle={onToggleTheme} size={32} />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderLeft: '1px solid var(--color-divider)',
          paddingLeft: 14,
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            border: '1px solid var(--color-accent)',
            display: 'grid',
            placeItems: 'center',
            fontSize: 12,
            color: 'var(--color-accent-700)',
            flex: 'none',
          }}
        >
          {session.username.slice(0, 1).toUpperCase()}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
          <span style={{ fontSize: 13 }}>{session.username}</span>
          <span className="text-muted" style={{ fontSize: 11 }}>
            {session.is_admin ? t('admin') : t('testManager')}
          </span>
        </div>
        <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={onSignOut}>
          {t('logout')}
        </button>
      </div>
    </header>
  )
}
