import { NavLink } from 'react-router-dom'
import { useTranslations, type Lang, type Translations } from '../i18n'

interface NavItem {
  key: string
  path: string
  labelKey: keyof Translations
  icon: string
  adminOnly: boolean
}

/** Icon paths are lifted from the source design's ICONS map. */
export const NAV_ITEMS: NavItem[] = [
  {
    key: 'status',
    path: '/admin/status',
    labelKey: 'status',
    icon: 'M22 12h-4l-3 9L9 3l-3 9H2',
    adminOnly: false,
  },
  {
    key: 'service',
    path: '/admin/service',
    labelKey: 'service',
    icon: 'M6 2h12a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM6 12h12a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2zM6 6h.01M6 16h.01',
    adminOnly: true,
  },
  {
    key: 'llm',
    path: '/admin/llm',
    labelKey: 'llm',
    icon: 'M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 9h6v6H9z',
    adminOnly: true,
  },
  {
    key: 'logging',
    path: '/admin/logging',
    labelKey: 'logging',
    icon: 'M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4M19 17V5a2 2 0 0 0-2-2H4M15 8h-5M15 12h-5',
    adminOnly: true,
  },
]

export function NavRail({ lang, isAdmin }: { lang: Lang; isAdmin: boolean }) {
  const t = useTranslations(lang)
  return (
    <nav
      aria-label={t.navLandmark}
      style={{
        width: 200,
        flex: 'none',
        borderRight: '1px solid var(--color-divider)',
        padding: '12px 0',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {NAV_ITEMS.map((item) => {
        const restricted = item.adminOnly && !isAdmin
        return (
          <NavLink
            key={item.key}
            to={item.path}
            aria-disabled={restricted || undefined}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 14px',
              margin: '0 8px',
              color: 'inherit',
              textDecoration: 'none',
              fontSize: 14,
              borderLeft: `2px solid ${isActive ? 'var(--color-accent)' : 'transparent'}`,
              background: isActive ? 'var(--color-accent-100)' : 'transparent',
              opacity: restricted ? 0.5 : isActive ? 1 : 0.8,
            })}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
              style={{ flex: 'none', opacity: 0.8 }}
            >
              <path d={item.icon} />
            </svg>
            <span style={{ flex: 1 }}>{t[item.labelKey]}</span>
            {restricted && (
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <rect x="4" y="11" width="16" height="10" />
                <path d="M8 11V7a4 4 0 0 1 8 0v4" />
              </svg>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}
