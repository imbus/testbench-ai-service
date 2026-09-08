import { de } from './de'
import { en } from './en'
import type { Translations } from './de'

export type Lang = 'de' | 'en'
export type { Translations }

const DICTIONARIES: Record<Lang, Translations> = { de, en }

export function useTranslations(lang: Lang): Translations {
  return DICTIONARIES[lang]
}
