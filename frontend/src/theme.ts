export type Theme = 'light' | 'dark'
export type Brand = 'testbench' | 'industry'

const STORAGE_KEY = 'tbai-console-theme'

/** The viewer's OS preference, defaulting to light where unknown. */
export function preferredTheme(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

/** Stamp the root element so the design system's token blocks apply. */
export function applyTheme(theme: Theme, brand: Brand = 'testbench'): void {
  const root = document.documentElement
  root.dataset.theme = theme
  root.dataset.brand = brand
  root.dataset.corners = 'soft'
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // A private window or blocked storage must not break theming.
  }
}
