import { useRef, useState } from 'react'
import { Button } from 'primereact/button'
import { useTranslation } from 'react-i18next'
import {
  agentModelPath,
  effectiveAgent,
  effectiveAgentModel,
  type InheritedModelSource,
  type Scope,
} from '../api/agents'
import { useModels, usePromptMeta } from '../api/queries'
import { valueAt } from '../screens/fields'
import { useDraft } from '../state/draft'
import { SearchPopover } from './SearchPopover'

const SOURCE_LABEL = {
  globalAgent: 'modelFromGlobalAgent',
  projectModel: 'modelFromProjectModel',
  llmModel: 'modelFromLlmModel',
  prompt: 'modelFromPrompt',
} as const satisfies Record<InheritedModelSource, string>

/**
 * Which model one agent runs on in one scope, as `llm_config.agent_models`.
 *
 * Shows the model that actually applies as a value, not as a form field: the
 * scope's own entry, bold, or what it inherits, dashed and named by where it
 * comes from (the global entry, a `llm_config.model`, or the prompt's model,
 * in the order the server resolves them). Clicking it opens a searchable list
 * per provider. Picking writes the scope's entry into the draft; "Inherit"
 * queues its removal.
 */
export function AgentModelPicker({
  agentKey,
  scope,
  disk,
  running,
  language,
  readOnly = false,
}: {
  agentKey: string
  scope: Scope
  disk: Record<string, unknown>
  running: Record<string, unknown>
  language: string
  readOnly?: boolean
}) {
  const { t } = useTranslation()
  const draft = useDraft()
  const project = scope.kind === 'project' ? scope.project : null
  const agent = effectiveAgent(running, agentKey, project)
  const promptFile = typeof agent.prompt?.file === 'string' ? agent.prompt.file : undefined
  const meta = usePromptMeta(language, agentKey, promptFile)
  const models = useModels(project ?? undefined, { enabled: !readOnly })

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const root = useRef<HTMLSpanElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  const variantName = agent.prompt?.variant ?? meta.data?.default_variant
  const variant = meta.data?.variants.find((entry) => entry.name === variantName)
  const promptModel = variant?.model ?? meta.data?.default_model

  const read = (path: string) => draft.valueOf(path, valueAt(disk, path) ?? valueAt(running, path))
  const { own, inherited, source } = effectiveAgentModel(read, scope, agentKey, promptModel)
  const path = agentModelPath(scope, agentKey)
  const label = `${agentKey} · ${t('model')}`
  const shown = own ?? inherited
  const origin = own ? t('modelOwn') : source ? t(SOURCE_LABEL[source]) : ''

  const close = (refocus: boolean) => {
    setOpen(false)
    setQuery('')
    if (refocus) trigger.current?.focus()
  }
  const pick = (model: string | null) => {
    close(true)
    if (model === null) draft.unsetValue(path)
    else draft.setValue(path, model)
  }
  const value = (
    <>
      <span className={shown ? 'name' : 'name missing'}>{shown ?? t('modelNone')}</span>
      {origin && <span className="src">{origin}</span>}
    </>
  )

  if (readOnly) {
    return (
      <span className="model-inline" data-state={own ? 'override' : 'inherit'}>
        {value}
      </span>
    )
  }

  const needle = query.trim().toLocaleLowerCase()
  const providers = (models.data?.providers ?? [])
    .map((provider) => ({
      ...provider,
      models: provider.models.filter((entry) => entry.id.toLocaleLowerCase().includes(needle)),
    }))
    .filter((provider) => provider.models.length > 0)
  const listed = (models.data?.providers ?? []).some((p) => p.models.some((m) => m.id === own))
  // A saved model the catalogue does not list still shows as itself.
  const unlisted = own && !listed && own.toLocaleLowerCase().includes(needle) ? own : null
  const firstMatch = unlisted ?? providers[0]?.models[0]?.id

  const item = (model: string | null, text: string, title?: string, muted = false) => {
    const current = model === (own ?? null)
    return (
      <button
        type="button"
        className="tb-popover-item"
        aria-current={current}
        title={title}
        onClick={() => pick(model)}
        style={muted && !current ? { opacity: 0.6 } : undefined}
      >
        <span className="check" aria-hidden>
          {current ? '✓' : ''}
        </span>
        <span style={model ? { fontFamily: 'var(--font-code)', fontSize: 12.5 } : undefined}>
          {text}
        </span>
      </button>
    )
  }

  return (
    <span
      ref={root}
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 4 }}
    >
      <button
        ref={trigger}
        type="button"
        className="model-inline"
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-testid={`agent-model-${agentKey}`}
        data-state={own ? 'override' : 'inherit'}
        onClick={() => (open ? close(false) : setOpen(true))}
      >
        {value}
        <span className="chev" aria-hidden>
          ▾
        </span>
      </button>
      {draft.isChanged(path) && (
        <Button
          type="button"
          text
          size="small"
          label={t('revert')}
          style={{ fontSize: 11, padding: '0 6px' }}
          onClick={() => draft.revert(path)}
        />
      )}
      {open && (
        <SearchPopover
          anchor={root}
          onDismiss={() => close(false)}
          label={label}
          searchLabel={t('modelSearch')}
          query={query}
          onQuery={setQuery}
          onEnter={() => firstMatch && pick(firstMatch)}
          onEscape={() => close(true)}
          width={300}
          footer={t('modelApplyHint')}
        >
          {!needle && (
            <li style={{ borderBottom: '1px solid var(--color-divider)', paddingBottom: 4 }}>
              {item(null, `${t('modelInherit')} (${inherited ?? '—'})`)}
            </li>
          )}
          {unlisted && <li>{item(unlisted, unlisted)}</li>}
          {providers.map((provider) => (
            <li key={provider.provider}>
              <div className="tb-popover-group">
                {provider.provider}
                {!provider.key_present && <span className="warn">{t('modelNoKey')}</span>}
              </div>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {provider.models.map((entry) => (
                  <li key={entry.id}>
                    {item(
                      entry.id,
                      entry.id,
                      provider.key_present ? undefined : t('modelNoKeyHint'),
                      !provider.key_present,
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {needle && !unlisted && providers.length === 0 && (
            <li className="tb-popover-empty">{t('modelNoMatch')}</li>
          )}
        </SearchPopover>
      )}
    </span>
  )
}
