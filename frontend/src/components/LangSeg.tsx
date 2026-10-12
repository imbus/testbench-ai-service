import { SelectButton } from 'primereact/selectbutton'
import { useTranslation } from 'react-i18next'
import { useLang } from '../i18n'

const OPTIONS = (['de', 'en'] as const).map((code) => ({ label: code.toUpperCase(), value: code }))

/**
 * The artboard's DE/EN segmented control, which appears twice: on the login
 * card and in the top bar. A PrimeReact `SelectButton`: a group of toggle
 * buttons, the current language the one that is pressed. `allowEmpty` is off
 * so clicking the current language cannot leave the console without one.
 */
export function LangSeg({ compact = false }: { compact?: boolean }) {
  const { t, i18n } = useTranslation()
  const lang = useLang()
  return (
    <SelectButton
      aria-label={t('language')}
      value={lang}
      options={OPTIONS}
      allowEmpty={false}
      onChange={(event) => {
        if (event.value) void i18n.changeLanguage(event.value)
      }}
      pt={compact ? { button: { style: { padding: '4px 10px' } } } : undefined}
    />
  )
}
