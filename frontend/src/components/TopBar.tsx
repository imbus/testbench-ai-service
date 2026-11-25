import { useState } from 'react'
import { Avatar } from 'primereact/avatar'
import { Button } from 'primereact/button'
import { BrandMark } from './BrandMark'
import { LangSeg } from './LangSeg'
import { ThemeButton } from './ThemeButton'
import { Modal } from './Modal'
import { useDraftChangeCount } from '../state/draft'
import { hasUnsavedPrompt } from '../state/unsaved'
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

export function TopBar({ session, theme, serviceLabel, onToggleTheme, onSignOut }: TopBarProps) {
  const { t } = useTranslation()
  const queuedChanges = useDraftChangeCount()
  // What signing out would throw away, asked at the click -- `null` while the
  // question is not open. Signing out clears the queued config changes and
  // unmounts the prompt editor, and neither can be brought back.
  const [losing, setLosing] = useState<{ changes: number; prompt: boolean } | null>(null)
  const askSignOut = () => {
    const prompt = hasUnsavedPrompt()
    if (queuedChanges > 0 || prompt) setLosing({ changes: queuedChanges, prompt })
    else onSignOut()
  }
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
            fontFamily: 'var(--font-code)',
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
        <Avatar
          aria-hidden="true"
          shape="circle"
          label={session.username.slice(0, 1).toUpperCase()}
          style={{ width: 28, height: 28, fontSize: 12, flex: 'none' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
          <span style={{ fontSize: 13 }}>{session.username}</span>
          <span className="text-muted" style={{ fontSize: 11 }}>
            {session.is_admin ? t('admin') : t('roleReadOnly')}
          </span>
        </div>
        <Button
          type="button"
          text
          label={t('logout')}
          style={{ fontSize: 12 }}
          onClick={askSignOut}
        />
      </div>
      {losing && (
        <Modal label={t('logoutUnsavedTitle')} width={480} onClose={() => setLosing(null)}>
          <h3 style={{ margin: 0 }}>{t('logoutUnsavedTitle')}</h3>
          <div style={{ fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {losing.changes > 0 && <div>{t('logoutUnsavedConfig', { count: losing.changes })}</div>}
            {losing.prompt && <div>{t('logoutUnsavedPrompt')}</div>}
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button type="button" outlined label={t('cancel')} onClick={() => setLosing(null)} />
            <Button
              type="button"
              severity="danger"
              label={t('logoutAnyway')}
              onClick={() => {
                setLosing(null)
                onSignOut()
              }}
            />
          </div>
        </Modal>
      )}
    </header>
  )
}
