import { useState } from 'react'
import { Button } from 'primereact/button'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import { Password } from 'primereact/password'
import { BrandMark } from '../components/BrandMark'
import { LangSeg } from '../components/LangSeg'
import { ThemeButton } from '../components/ThemeButton'
import { useTranslation } from 'react-i18next'
import type { Theme } from '../theme'

interface LoginProps {
  theme: Theme
  busy: boolean
  error: string | null
  onSignIn: (username: string, password: string) => void
  onToggleTheme: () => void
}

/**
 * The artboard's login artboard, minus its role picker.
 *
 * The blueprint grid behind the card, the brand lockup, the corner language
 * and theme controls and the framed submit button are all the artboard's; the
 * role segmented control is not ported, because the role comes from the JWT
 * TestBench issues and is not the operator's to choose.
 */
export function Login({
  theme,
  busy,
  error,
  onSignIn,
  onToggleTheme,
}: LoginProps) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  return (
    <div
      style={{
        minHeight: '100vh',
        position: 'relative',
        display: 'grid',
        placeItems: 'center',
        padding: 32,
        // The artboard's blueprint paper: a 40px rule grid in the divider
        // colour, so it follows the theme without a second token.
        backgroundImage:
          'linear-gradient(var(--color-divider) 1px, transparent 1px), linear-gradient(90deg, var(--color-divider) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 20,
          right: 24,
          display: 'flex',
          gap: 8,
          alignItems: 'center',
        }}
      >
        <LangSeg />
        <ThemeButton theme={theme} onToggle={onToggleTheme} />
      </div>

      <form
        className="blueprint"
        style={{
          width: 400,
          maxWidth: '100%',
          padding: 28,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          background: 'var(--color-bg)',
        }}
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

        {/* The artboard prints the build number after the subtitle. /meta is
            unauthenticated and does not carry one, and inventing a second
            source for it would let the login screen and the Status card
            disagree about which version is running. */}
        <BrandMark size="login" subtitle={t('consoleSubtitle')} />

        <div className="field">
          <label htmlFor="login-user">{t('username')}</label>
          <InputText
            id="login-user"
            autoComplete="username"
            autoFocus
            placeholder="a.mueller"
            style={{ width: '100%' }}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="login-pass">{t('password')}</label>
          {/* No strength meter: this is a sign-in, not a password choice. */}
          <Password
            inputId="login-pass"
            feedback={false}
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={{ display: 'flex' }}
            inputStyle={{ width: '100%' }}
          />
        </div>

        {error && (
          <Message severity="error" style={{ justifyContent: 'flex-start' }} text={error} />
        )}

        <Button
          className="blueprint"
          type="submit"
          disabled={busy}
          label={t('signIn')}
          style={{ height: 40, fontSize: 15, justifyContent: 'center' }}
        >
          <i className="corner tl" />
          <i className="corner tr" />
          <i className="corner bl" />
          <i className="corner br" />
        </Button>

        <div className="text-muted" style={{ fontSize: 11, lineHeight: 1.4 }}>
          {t('loginHint')}
        </div>
      </form>
    </div>
  )
}
