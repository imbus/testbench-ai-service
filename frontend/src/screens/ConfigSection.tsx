import { useState } from 'react'
import type { ConfigIssue } from '../api/types'
import { useConfig } from '../api/queries'
import { Field } from '../components/Field'
import { ReadOnlyField } from '../components/ReadOnlyField'
import { useTranslations, type Lang } from '../i18n'
import { LLM_FIELDS, LOGGING_FIELDS, SERVICE_TABS, valueAt, type FieldSpec } from './fields'

type Section = 'service' | 'llm' | 'logging'

const TITLE_KEY: Record<Section, 'service' | 'llm' | 'logging'> = {
  service: 'service',
  llm: 'llm',
  logging: 'logging',
}

const TOML_SECTION: Record<Section, string> = {
  service: '[testbench-ai-service]',
  llm: '[testbench-ai-service.llm_config]',
  logging: '[testbench-ai-service.logging.console] · [.file]',
}

/**
 * Check if an issue path matches a field key or a child path within it.
 * Matches exact equality or paths starting with key + '.' to handle array
 * elements reported by pydantic (e.g., trusted_proxies.0 matches trusted_proxies).
 * Must not be bare startsWith — that would make port match port_extra.
 */
function issueMatchesField(issuePath: string, fieldKey: string): boolean {
  return issuePath === fieldKey || issuePath.startsWith(fieldKey + '.')
}

export function ConfigSection({
  section,
  lang,
  isAdmin,
  issues = [],
}: {
  section: Section
  lang: Lang
  isAdmin: boolean
  /** Field-addressed validation failures from the last preview or apply. */
  issues?: ConfigIssue[]
}) {
  const t = useTranslations(lang)
  const config = useConfig()
  const [tab, setTab] = useState(SERVICE_TABS[0].key)

  if (config.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (config.isError || !config.data) {
    // Same structure as Status.tsx's error branch: the primary line is
    // always the translated fallback — never the raw, often-English,
    // backend-shaped error text — so this alert can never show untranslated
    // copy regardless of what threw. The raw message, if any, is shown
    // underneath only as diagnostic detail, guarded so an empty detail
    // renders nothing.
    const detail = (config.error as Error)?.message
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t.configError}</div>
        {detail && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
            {detail}
          </div>
        )}
      </div>
    )
  }

  const running = config.data.running
  let fields: FieldSpec[]
  if (section === 'service') {
    fields = (SERVICE_TABS.find((entry) => entry.key === tab) ?? SERVICE_TABS[0]).fields
  } else {
    fields = section === 'llm' ? LLM_FIELDS : LOGGING_FIELDS
  }

  // For Service tabs, determine which have issues
  const tabIssueCount = (tabKey: string): number => {
    const tabFields = SERVICE_TABS.find((entry) => entry.key === tabKey)?.fields ?? []
    return issues.filter((issue) =>
      tabFields.some((field) => issueMatchesField(issue.path, field.key)),
    ).length
  }

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        maxWidth: 1100,
      }}
    >
      {/* The artboard sets the screen title and the TOML section it edits on
          one line, so the section reads as the subject of the heading rather
          than as a caption under it. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t[TITLE_KEY[section]]}</h2>
        <span
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {TOML_SECTION[section]} · {config.data.config_path}
        </span>
      </div>

      {section === 'service' && (
        <div
          role="tablist"
          style={{ display: 'flex', gap: 20, borderBottom: '1px solid var(--color-divider)' }}
        >
          {SERVICE_TABS.map((entry) => {
            const count = tabIssueCount(entry.key)
            return (
              <button
                key={entry.key}
                role="tab"
                aria-selected={tab === entry.key}
                aria-label={`${t[entry.labelKey]}${count > 0 ? ` (${count} ${count === 1 ? 'issue' : 'issues'})` : ''}`}
                onClick={() => setTab(entry.key)}
                style={{
                  background: 'none',
                  border: 0,
                  borderBottom: `2px solid ${tab === entry.key ? 'var(--color-accent)' : 'transparent'}`,
                  padding: '8px 0',
                  font: 'inherit',
                  fontSize: 14,
                  color: 'inherit',
                  opacity: tab === entry.key ? 1 : 0.7,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                {t[entry.labelKey]}
                {count > 0 && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 18,
                      height: 18,
                      borderRadius: '50%',
                      background: '#a33a2b',
                      color: '#fff',
                      fontSize: 11,
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}

      <div style={{ maxWidth: 860 }}>
        {fields.map((spec) => {
          const issue = issues.find((entry) => issueMatchesField(entry.path, spec.key))?.message
          // Non-admins keep the phase-1 read-only rendering unchanged rather
          // than getting a form full of disabled inputs.
          return isAdmin ? (
            <Field
              key={spec.key}
              spec={spec}
              // The draft is "what will be written", so it is measured against
              // the file, not against the fully-defaulted running config --
              // otherwise every default the file omits counts as a pending
              // change whose diff would come back empty.
              saved={valueAt(config.data.disk, spec.key) ?? valueAt(running, spec.key)}
              issue={issue}
              lang={lang}
            />
          ) : (
            <ReadOnlyField key={spec.key} spec={spec} value={valueAt(running, spec.key)} />
          )
        })}
      </div>
    </div>
  )
}
