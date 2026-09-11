import { Fragment } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslations, type Lang, type Translations } from '../i18n'

interface NavItem {
  key: string
  path: string
  labelKey: keyof Translations
  icon: string
  adminOnly: boolean
  /** Renders a rule above this entry, the way the artboard groups the rail. */
  dividerBefore?: boolean
}

/** Icon paths are lifted verbatim from the source design's ICONS map. */
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
  {
    key: 'agents',
    path: '/admin/agents',
    labelKey: 'agents',
    icon: 'M12 8V4H8M4 8h16v12H4zM2 14h2M20 14h2M15 13v2M9 13v2',
    // Read-only for a non-admin, like Status: gating the link would hide
    // information the operator is allowed to see.
    adminOnly: false,
    dividerBefore: true,
  },
  {
    key: 'projects',
    path: '/admin/projects',
    labelKey: 'projects',
    icon: 'M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z',
    adminOnly: false,
  },
  {
    key: 'prompts',
    path: '/prompts',
    labelKey: 'prompts',
    icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    // Read-only for a non-admin, like Agents and Projects: the tree and the
    // editor both render through VarDeclTable/MessageList/read-only fields
    // rather than hiding the nav entry, which would conceal information the
    // operator is allowed to see.
    adminOnly: false,
  },
  {
    key: 'raw',
    path: '/admin/raw',
    labelKey: 'raw',
    icon: 'M10 12.5 8 15l2 2.5M14 12.5l2 2.5-2 2.5M14 2v4a2 2 0 0 0 2 2h4M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z',
    adminOnly: true,
    dividerBefore: true,
  },
]

export function NavRail({
  lang,
  isAdmin,
  /** Count shown on Projects, as the artboard badges it. Hidden at zero. */
  overrideCount = 0,
}: {
  lang: Lang
  isAdmin: boolean
  overrideCount?: number
}) {
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
        // Below the 52px top bar, so a long matrix scrolls under a rail that
        // stays where the operator left it.
        position: 'sticky',
        top: 52,
        alignSelf: 'flex-start',
        height: 'calc(100vh - 52px)',
      }}
    >
      {NAV_ITEMS.map((item) => {
        const restricted = item.adminOnly && !isAdmin
        const badge = item.key === 'projects' && overrideCount > 0 ? overrideCount : null
        return (
          <Fragment key={item.key}>
            {item.dividerBefore && (
              <div
                aria-hidden="true"
                style={{ height: 1, background: 'var(--color-divider)', margin: '8px 16px' }}
              />
            )}
            <NavLink
              to={item.path}
              className="tb-nav"
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
                strokeLinejoin="round"
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
              {badge !== null && (
                <span className="tag tag-accent" style={{ padding: '1px 6px', fontSize: 10 }}>
                  {badge}
                </span>
              )}
            </NavLink>
          </Fragment>
        )
      })}
      <div style={{ flex: 1 }} />
      <div
        className="text-muted"
        style={{ padding: '8px 24px', fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
      >
        config.toml · prompts/
      </div>
    </nav>
  )
}
