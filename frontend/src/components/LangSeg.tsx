import { SelectButton } from 'primereact/selectbutton'
import { useTranslation } from 'react-i18next'
import { pickLang, useLang } from '../i18n'

const OPTIONS = (['de', 'en'] as const).map((code) => ({ label: code.toUpperCase(), value: code }))

export function LangSeg({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const lang = useLang()
  return (
    <SelectButton
      aria-label={t('language')}
      value={lang}
      options={OPTIONS}
      allowEmpty={false}
      onChange={(event) => {
        if (event.value) void pickLang(event.value)
      }}
      pt={compact ? { button: { style: { padding: '4px 10px' } } } : undefined}
    />
  )
}
