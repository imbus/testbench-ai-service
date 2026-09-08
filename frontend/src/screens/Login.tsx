import { useState } from 'react'
import { useTranslations, type Lang } from '../i18n'

interface LoginProps {
  serverUrl: string
  lang: Lang
  busy: boolean
  error: string | null
  onSignIn: (username: string, password: string) => void
}

export function Login({ serverUrl, lang, busy, error, onSignIn }: LoginProps) {
  const t = useTranslations(lang)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--space-6)',
      }}
    >
      <form
        className="card blueprint"
        style={{ width: 'min(380px, 100%)', padding: 'var(--space-6)', gap: 'var(--space-4)' }}
        onSubmit={(event) => {
          event.preventDefault()
          if (!username || !password) return
          onSignIn(username, password)
        }}
      >
        <i className="corner tl" />
        <i className="corner tr" />
        <i className="corner bl" />
        <i className="corner br" />
        <h2 style={{ margin: 0 }}>{t.login}</h2>

        <div className="field">
          <label htmlFor="login-server">{t.server}</label>
          {/* One service, one TestBench: prefilled from config and not editable. */}
          <input
            id="login-server"
            className="input"
            value={serverUrl}
            readOnly
            style={{ opacity: 0.7 }}
          />
        </div>

        <div className="field">
          <label htmlFor="login-user">{t.username}</label>
          <input
            id="login-user"
            className="input"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="login-pass">{t.password}</label>
          <input
            id="login-pass"
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error && (
          <div role="alert" style={{ color: '#c0392b', fontSize: 13 }}>
            {error}
          </div>
        )}

        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {t.signIn}
        </button>
      </form>
    </div>
  )
}
