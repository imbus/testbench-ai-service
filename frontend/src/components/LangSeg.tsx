import { useTranslation } from 'react-i18next'
import { useLang } from '../i18n'

/**
 * The artboard's DE/EN segmented control, which appears twice: on the login
 * card and in the top bar. `name` keeps the two radio groups apart if they
 * ever render together.
 */
export function LangSeg({
  name = 'console-lang',
  compact = false,
}: {
  name?: string
  compact?: boolean
}) {
  const { t, i18n } = useTranslation()
  const lang = useLang()
  return (
    <div className="seg" role="group" aria-label={t('language')}>
      {(['de', 'en'] as const).map((code) => (
        <label key={code} className="seg-opt" style={compact ? { padding: '4px 10px' } : undefined}>
          <input
            type="radio"
            name={name}
            checked={lang === code}
            onChange={() => void i18n.changeLanguage(code)}
          />
          {code.toUpperCase()}
        </label>
      ))}
    </div>
  )
}
