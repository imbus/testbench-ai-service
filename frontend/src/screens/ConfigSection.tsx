import { useState } from 'react'
import { useConfig } from '../api/queries'
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

export function ConfigSection({ section, lang }: { section: Section; lang: Lang }) {
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

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 900,
      }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t[TITLE_KEY[section]]}</h2>
        <div
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {TOML_SECTION[section]} · {config.data.config_path}
        </div>
      </div>

      {section === 'service' && (
        <div role="tablist" style={{ display: 'flex', gap: 18 }}>
          {SERVICE_TABS.map((entry) => (
            <button
              key={entry.key}
              role="tab"
              aria-selected={tab === entry.key}
              onClick={() => setTab(entry.key)}
              style={{
                background: 'none',
                border: 0,
                borderBottom: `2px solid ${tab === entry.key ? 'var(--color-accent)' : 'transparent'}`,
                padding: '6px 0',
                font: 'inherit',
                fontSize: 14,
                color: 'inherit',
                opacity: tab === entry.key ? 1 : 0.7,
                cursor: 'pointer',
              }}
            >
              {t[entry.labelKey]}
            </button>
          ))}
        </div>
      )}

      <div>
        {fields.map((spec) => (
          <ReadOnlyField key={spec.key} spec={spec} value={valueAt(running, spec.key)} />
        ))}
      </div>
    </div>
  )
}
