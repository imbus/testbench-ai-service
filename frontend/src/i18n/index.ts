import i18n from 'i18next'
import { initReactI18next, useTranslation } from 'react-i18next'
import { de } from './de'
import { en } from './en'
import type { Translations } from './de'

export type Lang = 'de' | 'en'
export type TranslationKey = keyof Translations
export type { Translations }

// German first, matching the backend's default service language. The
// dictionaries are bundled, so init completes synchronously and the first
// render already has its strings.
void i18n.use(initReactI18next).init({
  resources: {
    de: { translation: de },
    en: { translation: en satisfies Translations },
  },
  lng: 'de',
  fallbackLng: 'de',
  initAsync: false,
  // React escapes rendered text itself.
  interpolation: { escapeValue: false },
})

/** The active UI language, for what `t` does not cover (locales, data picks). */
export function useLang(): Lang {
  const { i18n: instance } = useTranslation()
  return (instance.resolvedLanguage ?? 'de') as Lang
}

export { i18n }

/** The pre-i18next lookup; goes once every caller uses `useTranslation`. */
export function useTranslations(lang: Lang): Translations {
  return lang === 'en' ? en : de
}
