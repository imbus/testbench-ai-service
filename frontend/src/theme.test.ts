import { applyTheme, preferredTheme } from './theme'

test('applyTheme stamps the root element', () => {
  applyTheme('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(document.documentElement.dataset.brand).toBe('testbench')
  expect(document.documentElement.dataset.corners).toBe('soft')
})

test('applyTheme can switch back to light', () => {
  applyTheme('dark')
  applyTheme('light')
  expect(document.documentElement.dataset.theme).toBe('light')
})

test('preferredTheme falls back to light when the media query is unavailable', () => {
  expect(preferredTheme()).toBe('light')
})

test('applyTheme still stamps the root element when localStorage.setItem throws', () => {
  const setItemSpy = vi
    .spyOn(Storage.prototype, 'setItem')
    .mockImplementation(() => {
      throw new Error('storage blocked')
    })

  expect(() => applyTheme('dark')).not.toThrow()
  expect(document.documentElement.dataset.theme).toBe('dark')

  setItemSpy.mockRestore()
})
