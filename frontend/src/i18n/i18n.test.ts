import { de } from './de'
import { en } from './en'

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
