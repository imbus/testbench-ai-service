import i18n from 'i18next'
import { initReactI18next, useTranslation } from 'react-i18next'
import { de } from './de'
import { en } from './en'
import type { Translations } from './de'

export type Lang = 'de' | 'en'
export type { Translations }

const STORAGE_KEY = 'tbai-console-lang'

/** The language the viewer last picked, or null if none (or unreadable). */
export function storedLang(): Lang | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'de' || value === 'en' ? value : null
  } catch {
    return null
  }
}

// The viewer's last pick survives a reload; otherwise German first, matching
// the backend's default service language. The dictionaries are bundled, so
// init completes synchronously and the first render already has its strings.
void i18n.use(initReactI18next).init({
  resources: {
    de: { translation: de },
    en: { translation: en satisfies Translations },
  },
  lng: storedLang() ?? 'de',
  fallbackLng: 'de',
  initAsync: false,
  // React escapes rendered text itself.
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => {
  try {
    localStorage.setItem(STORAGE_KEY, lng)
  } catch {
    // A private window or blocked storage must not break switching.
  }
})

/** The active UI language, for what `t` does not cover (locales, data picks). */
export function useLang(): Lang {
  const { i18n: instance } = useTranslation()
  return (instance.resolvedLanguage ?? 'de') as Lang
}

export { i18n }
