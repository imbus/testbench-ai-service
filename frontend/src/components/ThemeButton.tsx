import { useTranslations, type Lang } from '../i18n'
import type { Theme } from '../theme'

/**
 * The artboard's theme toggle: one sun glyph in both themes, so the control
 * never moves or changes shape. What it will do is carried by the label, not
 * by the icon.
 */
export function ThemeButton({
  theme,
  lang,
  onToggle,
  size = 36,
}: {
  theme: Theme
  lang: Lang
  onToggle: () => void
  size?: number
}) {
  const t = useTranslations(lang)
  return (
    <button
      type="button"
      className="btn btn-secondary btn-icon"
      style={{ width: size, height: size }}
      onClick={onToggle}
      aria-label={theme === 'light' ? t.darkTheme : t.lightTheme}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    </button>
  )
}
