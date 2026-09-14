import { useState } from 'react'

import type { ConfigIssue, ExtraModelEntry, RoutingFamily } from '../api/types'
import { useDraft } from '../state/draft'
import { useTranslations, type Lang } from '../i18n'

/**
 * Which request shapes each provider's client can produce. Mirrors
 * `ALLOWED_ROUTING` in models/config.py — the server refuses a bad pairing as
 * a ConfigIssue, and filtering here keeps the operator from queuing one.
 *
 * Wire tokens, not prose: kept in English regardless of `lang`, the same way
 * Field.tsx never translates `spec.key`.
 */
const ALLOWED_ROUTING: Record<string, RoutingFamily[]> = {
  openai: ['chat', 'reasoning', 'fallback'],
  azure_openai: ['chat', 'reasoning', 'fallback'],
  anthropic: ['adaptive', 'budget', 'fallback'],
  custom: ['fallback'],
}

const PROVIDERS = Object.keys(ALLOWED_ROUTING)

/**
 * Display labels for the "new provider" select only. The `llm_config.provider`
 * field elsewhere on this same screen already renders the raw wire token
 * (e.g. "openai") as plain text; an option with identical text would make
 * `getByText('openai')` — and a sighted operator — see two "openai"s with no
 * way to tell which is which. The `value` submitted to the draft stays the
 * lowercase wire token; only what is displayed differs.
 */
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  azure_openai: 'Azure OpenAI',
  anthropic: 'Anthropic',
  custom: 'Custom',
}

/** The draft path one entry's field lives at. */
function path(model: string, field?: 'provider' | 'routing'): string {
  const base = `llm_config.extra_models.${model}`
  return field ? `${base}.${field}` : base
}

/**
 * Same prefix rule `ConfigSection` uses for its own fields
 * (`issueMatchesField`): exact match or a child path, never a bare
 * `startsWith` — that would make `claude-opus-6` match `claude-opus-60`.
 */
function issueMatchesRow(issuePath: string, rowKey: string): boolean {
  return issuePath === rowKey || issuePath.startsWith(rowKey + '.')
}

export function ModelTable({
  entries,
  issues,
  readOnly = false,
  lang = 'de',
}: {
  /** Operator-added entries only — `llm_config.extra_models` as saved/drafted. Built-ins never appear here. */
  entries: Record<string, ExtraModelEntry>
  issues: ConfigIssue[]
  readOnly?: boolean
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const draft = useDraft()

  const [newName, setNewName] = useState('')
  const [newProvider, setNewProvider] = useState(PROVIDERS[0])
  const [newRouting, setNewRouting] = useState<RoutingFamily>(ALLOWED_ROUTING[PROVIDERS[0]][0])

  const routingChoicesFor = (provider: string): RoutingFamily[] =>
    ALLOWED_ROUTING[provider] ?? ['fallback']

  const onProviderChange = (provider: string) => {
    setNewProvider(provider)
    const choices = routingChoicesFor(provider)
    if (!choices.includes(newRouting)) {
      setNewRouting(choices[0])
    }
  }

  const onAdd = () => {
    const name = newName.trim()
    if (name === '') return
    draft.setValue(path(name, 'provider'), newProvider)
    draft.setValue(path(name, 'routing'), newRouting)
    setNewName('')
  }

  const onRemove = (model: string) => {
    draft.unsetSubtree(path(model))
  }

  const rowIssue = (model: string): string | undefined =>
    issues.find((issue) => issueMatchesRow(issue.path, path(model)))?.message

  const modelNames = Object.keys(entries)

  return (
    <div style={{ marginTop: 24 }}>
      <h3 style={{ margin: '0 0 4px' }}>{t.models}</h3>
      <p className="text-muted" style={{ fontSize: 12, margin: '0 0 12px' }}>
        {t.modelsHint}
      </p>

      {modelNames.length === 0 ? (
        <p className="text-muted" style={{ fontSize: 13 }}>
          {t.modelsEmpty}
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {modelNames.map((model) => {
            const entry = entries[model]
            const issue = rowIssue(model)
            return (
              <div
                key={model}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr 1fr auto',
                  gap: 12,
                  alignItems: 'center',
                  padding: '6px 0',
                  borderBottom: '1px solid var(--color-divider)',
                }}
              >
                <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{model}</span>
                <span>{entry.provider}</span>
                <span>{entry.routing}</span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={readOnly}
                  onClick={() => onRemove(model)}
                >
                  {t.modelRemove}
                </button>
                {issue && (
                  <span
                    role="alert"
                    style={{ gridColumn: '1 / -1', fontSize: 11, color: '#a33a2b' }}
                  >
                    {issue}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 1fr auto',
          gap: 12,
          alignItems: 'end',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label htmlFor="model-new-name" style={{ fontSize: 11 }}>
            {t.modelNewName}
          </label>
          <input
            id="model-new-name"
            className="input"
            type="text"
            value={newName}
            disabled={readOnly}
            onChange={(event) => setNewName(event.target.value)}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label htmlFor="model-new-provider" style={{ fontSize: 11 }}>
            {t.modelNewProvider}
          </label>
          <select
            id="model-new-provider"
            className="input"
            value={newProvider}
            disabled={readOnly}
            onChange={(event) => onProviderChange(event.target.value)}
          >
            {PROVIDERS.map((provider) => (
              <option key={provider} value={provider}>
                {PROVIDER_LABELS[provider] ?? provider}
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label htmlFor="model-new-routing" style={{ fontSize: 11 }}>
            {t.modelNewRouting}
          </label>
          <select
            id="model-new-routing"
            className="input"
            value={newRouting}
            disabled={readOnly}
            onChange={(event) => setNewRouting(event.target.value as RoutingFamily)}
          >
            {routingChoicesFor(newProvider).map((routing) => (
              <option key={routing} value={routing}>
                {routing}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn" disabled={readOnly} onClick={onAdd}>
          {t.modelAdd}
        </button>
      </div>
    </div>
  )
}
