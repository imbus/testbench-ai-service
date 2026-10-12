import { de } from './de'
import { en } from './en'
import { i18n } from '.'

const placeholders = (text: string) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort()

test('both languages use the same placeholders per key', () => {
  for (const key of Object.keys(de) as (keyof typeof de)[]) {
    expect(placeholders(en[key]), `placeholders of ${key}`).toEqual(placeholders(de[key]))
  }
})

test('i18next starts in German and switches to English', async () => {
  expect(i18n.t('service')).toBe('Dienst')
  await i18n.changeLanguage('en')
  expect(i18n.t('service')).toBe('Service')
})

test('both languages define exactly the same keys', () => {
  expect(Object.keys(de).sort()).toEqual(Object.keys(en).sort())
})

test('no translation is left empty', () => {
  for (const [key, value] of Object.entries({ ...de, ...en })) {
    expect(value, `empty translation for ${key}`).not.toBe('')
  }
})

test('German is the default service language, matching the backend', () => {
  expect(de.status).toBe('Status')
  expect(de.service).toBe('Dienst')
})

test('the traceback label keeps the technical term in both languages', () => {
  expect(de.traceback).toBe('Traceback')
  expect(en.traceback).toBe('Traceback')
})

test('counts pick the singular or plural form', () => {
  expect(i18n.t('inFlight', { count: 1 })).toBe('1 Agent-Lauf ist noch aktiv.')
  expect(i18n.t('inFlight', { count: 3 })).toBe('3 Agent-Läufe sind noch aktiv.')
  expect(i18n.t('overrideCount', { count: 1, lng: 'en' })).toBe('1 override')
})
