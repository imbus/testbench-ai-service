import { useRef, useState } from 'react'
import { Button } from 'primereact/button'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import { Password } from 'primereact/password'
import { BrandMark } from '../components/BrandMark'
import { LangSeg } from '../components/LangSeg'
import { ThemeButton } from '../components/ThemeButton'
import { useTranslation } from 'react-i18next'
import type { ApiError } from '../api/client'
import type { Translations } from '../i18n/de'
import type { Theme } from '../theme'

interface LoginProps {
  theme: Theme
  busy: boolean
  error: ApiError | null
  /** The previous session ended on its own; say so instead of showing a bare form. */
  expired?: boolean
  onSignIn: (username: string, password: string) => void
  onToggleTheme: () => void
}

/**
 * The i18n keys of the headline and the hint for a failed sign-in.
 *
 * The service's own message is technical (it is the requests exception for an
 * unreachable TestBench), so it goes under "Details" rather than in the headline.
 */
function signInErrorKeys(status: number): [keyof Translations, keyof Translations | null] {
  switch (status) {
    case 0:
      return ['loginErrorService', 'loginErrorServiceHint']
    case 401:
      return ['loginErrorCredentials', null]
    case 500:
      return ['loginErrorConfig', 'loginErrorConfigHint']
    case 502:
    case 504:
      return ['loginErrorUnreachable', 'loginErrorUnreachableHint']
    default:
      return ['loginErrorUnknown', null]
  }
}

/**
 * The artboard's login artboard, minus its role picker.
 *
 * The blueprint grid behind the card, the brand lockup, the corner language
 * and theme controls and the framed submit button are all the artboard's; the
 * role segmented control is not ported, because the role comes from the JWT
 * TestBench issues and is not the operator's to choose.
 */
export function Login({ theme, busy, error, expired, onSignIn, onToggleTheme }: LoginProps) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  // Set by a submit with an empty field, cleared by the next keystroke.
  const [missing, setMissing] = useState(false)
  // The server's answer the operator has moved on from, by editing a field or
  // submitting again. It answered one attempt: shown over a form that no longer
  // holds what was sent, it reads as the verdict on what is typed now. A new
  // failed attempt is a new error object and shows again.
  const [staleError, setStaleError] = useState<ApiError | null>(null)
  const shownError = error !== staleError ? error : null
  const userInput = useRef<HTMLInputElement>(null)
  const passInput = useRef<HTMLInputElement>(null)

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
          if (!username || !password) {
            // Say why nothing happened, and put the cursor where the gap is.
            setMissing(true)
            setStaleError(error)
            ;(username ? passInput : userInput).current?.focus()
            return
          }
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
            ref={userInput}
            value={username}
            aria-invalid={missing && !username ? true : undefined}
            onChange={(event) => {
              setMissing(false)
              setStaleError(error)
              setUsername(event.target.value)
            }}
          />
        </div>

        <div className="field">
          <label htmlFor="login-pass">{t('password')}</label>
          {/* No strength meter: this is a sign-in, not a password choice. */}
          <Password
            inputId="login-pass"
            feedback={false}
            autoComplete="current-password"
            inputRef={passInput}
            value={password}
            aria-invalid={missing && !password ? true : undefined}
            onChange={(event) => {
              setMissing(false)
              setStaleError(error)
              setPassword(event.target.value)
            }}
            style={{ display: 'flex' }}
            inputStyle={{ width: '100%' }}
          />
        </div>

        {expired && !shownError && !missing && (
          <Message
            severity="info"
            style={{ justifyContent: 'flex-start' }}
            text={t('sessionExpired')}
          />
        )}
        {missing && (
          <Message
            severity="warn"
            style={{ justifyContent: 'flex-start' }}
            text={t('loginMissing')}
          />
        )}
        {shownError && !missing && <SignInError error={shownError} />}

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

function SignInError({ error }: { error: ApiError }) {
  const { t } = useTranslation()
  const [headline, hint] = signInErrorKeys(error.status)
  return (
    <Message
      severity="error"
      style={{ justifyContent: 'flex-start', alignItems: 'flex-start' }}
      text={
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <strong>{t(headline)}</strong>
          {hint && <span style={{ fontSize: 12 }}>{t(hint)}</span>}
          {error.status !== 401 && (
            <details style={{ fontSize: 11 }}>
              <summary style={{ cursor: 'pointer' }}>{t('details')}</summary>
              <pre
                style={{
                  margin: '4px 0 0',
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  fontSize: 11,
                }}
              >
                {error.message}
              </pre>
            </details>
          )}
        </div>
      }
    />
  )
}
