import { Button } from 'primereact/button'
import { Dropdown } from 'primereact/dropdown'
import { useTranslation } from 'react-i18next'
import { agentModelPath, effectiveAgent, effectiveAgentModel, type Scope } from '../api/agents'
import { useModels, usePromptMeta } from '../api/queries'
import { valueAt } from '../screens/fields'
import { useDraft } from '../state/draft'

/** The dropdown's value for "no entry of my own". Never a model id; Prime
 *  reads an empty value as "nothing selected". */
const INHERIT = '__inherit__'

/**
 * Which model one agent runs on in one scope, as `llm_config.agent_models`.
 *
 * Shows the model that actually applies: the scope's own entry when it has
 * one, otherwise what it inherits -- the global entry, `llm_config.model`, or
 * the prompt's model, in the order the server resolves them. Picking writes
 * the scope's entry into the draft; "Inherit" queues its removal.
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

  const variantName = agent.prompt?.variant ?? meta.data?.default_variant
  const variant = meta.data?.variants.find((entry) => entry.name === variantName)
  const promptModel = variant?.model ?? meta.data?.default_model

  const read = (path: string) => draft.valueOf(path, valueAt(disk, path) ?? valueAt(running, path))
  const { own, inherited } = effectiveAgentModel(read, scope, agentKey, promptModel)
  const path = agentModelPath(scope, agentKey)
  const inheritLabel = `${t('inherit')} (${inherited ?? '—'})`

  if (readOnly) {
    return (
      <span className="text-muted" style={{ fontSize: 12, fontFamily: 'var(--font-code)' }}>
        {own ?? inheritLabel}
      </span>
    )
  }

  const providers = models.data?.providers ?? []
  const known = providers.some((provider) => provider.models.some((entry) => entry.id === own))
  // One group per provider, as on the test-run panel. A saved model the
  // catalogue does not list still shows as itself rather than as blank.
  const groups = [
    { label: '', items: [{ label: inheritLabel, value: INHERIT }] },
    ...(own && !known ? [{ label: '', items: [{ label: own, value: own }] }] : []),
    ...providers.map((provider) => ({
      label: provider.key_present ? provider.provider : `${provider.provider} (${t('testRunNoKey')})`,
      items: provider.models.map((entry) => ({ label: entry.id, value: entry.id })),
    })),
  ]

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <Dropdown
        value={own ?? INHERIT}
        options={groups}
        optionGroupLabel="label"
        optionGroupChildren="items"
        aria-label={`${agentKey} · ${t('model')}`}
        data-testid={`agent-model-${agentKey}`}
        data-state={own ? 'override' : 'inherit'}
        onChange={(event) =>
          event.value === INHERIT ? draft.unsetValue(path) : draft.setValue(path, event.value)
        }
        pt={{
          root: { style: { minWidth: 0, maxWidth: 260 } },
          input: { style: { fontSize: 12, padding: '3px 8px', fontFamily: 'var(--font-code)' } },
        }}
      />
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
    </span>
  )
}
