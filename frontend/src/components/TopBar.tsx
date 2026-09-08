import { useTranslations, type Lang } from '../i18n'
import type { Theme } from '../theme'
import type { SessionInfo } from '../api/types'

interface TopBarProps {
  session: SessionInfo
  lang: Lang
  theme: Theme
  onToggleTheme: () => void
  onSetLang: (lang: Lang) => void
  onSignOut: () => void
}

export function TopBar({
  session,
  lang,
  theme,
  onToggleTheme,
  onSetLang,
  onSignOut,
}: TopBarProps) {
  const t = useTranslations(lang)
  return (
    <header
      style={{
        height: 52,
        flex: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        padding: '0 var(--space-4)',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <span className="nav-brand">TestBench AI Service</span>
      <div style={{ flex: 1 }} />
      <div className="seg" role="group" aria-label={t.language}>
        {(['de', 'en'] as const).map((code) => (
          <label key={code} className="seg-opt">
            <input
              type="radio"
              name="console-lang"
              checked={lang === code}
              onChange={() => onSetLang(code)}
            />
            {code}
          </label>
        ))}
      </div>
      <button
        className="btn btn-secondary btn-icon"
        onClick={onToggleTheme}
        aria-label={theme === 'light' ? 'Dark theme' : 'Light theme'}
      >
        {theme === 'light' ? '◐' : '◑'}
      </button>
      <span style={{ fontSize: 13 }}>{session.username}</span>
      <span className="tag tag-neutral">
        {session.is_admin ? t.admin : t.testManager}
      </span>
      <button className="btn btn-ghost" onClick={onSignOut}>
        {t.logout}
      </button>
    </header>
  )
}
