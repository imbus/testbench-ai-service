import { useTranslations, type Lang } from '../i18n'

/**
 * The artboard's DE/EN segmented control, which appears twice: on the login
 * card and in the top bar. `name` keeps the two radio groups apart if they
 * ever render together.
 */
export function LangSeg({
  lang,
  onSetLang,
  name = 'console-lang',
  compact = false,
}: {
  lang: Lang
  onSetLang: (lang: Lang) => void
  name?: string
  compact?: boolean
}) {
  const t = useTranslations(lang)
  return (
    <div className="seg" role="group" aria-label={t.language}>
      {(['de', 'en'] as const).map((code) => (
        <label key={code} className="seg-opt" style={compact ? { padding: '4px 10px' } : undefined}>
          <input
            type="radio"
            name={name}
            checked={lang === code}
            onChange={() => onSetLang(code)}
          />
          {code.toUpperCase()}
        </label>
      ))}
    </div>
  )
}
