import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Dropdown } from 'primereact/dropdown'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import { Tag } from 'primereact/tag'
import { useTestPrompt } from '../api/mutations'
import { useModels, useProjects } from '../api/queries'
import type { PromptMessageDoc } from '../api/types'
import { useTranslation } from 'react-i18next'
import { useLang } from '../i18n'
import { MarkdownView } from './MarkdownView'

/** The picker's "Other model…" entry -- not a model id, so it can never collide with one. */
const CUSTOM = '__custom__'

/**
 * Run the draft variant being edited against a real model (design §5.7).
 *
 * The one console action that spends money -- so a run is never implicit,
 * the button is disabled the moment one is in flight (the backend's own 409
 * against a concurrent run is a backstop, not something this relies on), and
 * a session that may not run never sees an enabled button at all.
 *
 * The model picker offers the catalogue (`GET /models`) but a model missing
 * from it must stay reachable: its "Other model…" entry reveals a free-text
 * input bound to the same state the picker writes, so typing a model the
 * catalogue has never heard of still reaches the request. The input also
 * shows on its own whenever the chosen model is not a catalogue entry (the
 * catalogue is empty, failed, or arrived after the operator typed). There is
 * no add-model control here -- that lives on the LLM provider view.
 *
 * Mounted below the app's own `QueryClientProvider` (`main.tsx`) like every
 * other screen -- `useModels`/`useProjects` share the same cache the rest of
 * the console already populated (the Projects screen's list, in particular),
 * rather than a private client that would refetch it and could disagree.
 */
export function TestRunPanel({
  messages,
  vars,
  agentContext,
  isAdmin,
  managedProjects = [],
}: {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  agentContext: Record<string, unknown>
  isAdmin: boolean
  /**
   * The projects a non-admin may run against (a project admin's managed ones).
   * Empty means this session may not run at all. Ignored for an admin.
   */
  managedProjects?: string[]
}) {
  const { t } = useTranslation()
  const lang = useLang()
  const [project, setProject] = useState<string | null>(null)
  const [model, setModel] = useState('')
  const [customPicked, setCustomPicked] = useState(false)
  const modelInput = useRef<HTMLInputElement>(null)
  const projects = useProjects()
  // A non-admin may only ask about a project they manage; the unscoped
  // catalogue is admin-only, so it is not even requested before a pick.
  const mayRun = isAdmin || managedProjects.length > 0
  const models = useModels(project ?? undefined, { enabled: isAdmin || project !== null })
  const test = useTestPrompt()

  const providers = models.data?.providers ?? []
  const selectedProvider = providers.find((provider) =>
    provider.models.some((entry) => entry.id === model),
  )
  const selectedEntry = selectedProvider?.models.find((entry) => entry.id === model)
  const hasCatalogue = providers.some((provider) => provider.models.length > 0)
  const custom = customPicked || !hasCatalogue || (model !== '' && !selectedEntry)

  // An empty model is a guaranteed 502 on a paid endpoint: the request reaches
  // a real client, which asks the provider about a model called "". The one
  // console action that spends money does not get to be spent on nothing.
  const canRun =
    mayRun && (isAdmin || project !== null) && !test.isPending && model.trim() !== ''

  const handleRun = () => {
    test.mutate({ messages, vars, agent_context: agentContext, model, project })
  }

  // One option group per provider, then a label-less group holding only
  // "Other model…": Prime's grouped Dropdown takes groups all the way down.
  const modelGroups = [
    ...providers.map((provider) => ({
      label: provider.key_present ? provider.provider : `${provider.provider} (${t('testRunNoKey')})`,
      items: provider.models.map((entry) => ({ label: `${entry.id} · ${entry.routing}`, value: entry.id })),
    })),
    { label: '', items: [{ label: t('testRunModelCustom'), value: CUSTOM }] },
  ]

  const pickModel = (value: string) => {
    if (value === CUSTOM) {
      setCustomPicked(true)
      // After the render that mounts the input.
      requestAnimationFrame(() => modelInput.current?.focus())
      return
    }
    setCustomPicked(false)
    setModel(value)
  }

  return (
    <section data-testid="test-run-panel" className="testrun">
      <h3 className="testrun-title">{t('testRun')}</h3>

      <div className="testrun-fields">
        <div className="field">
          <label htmlFor="testrun-model">{t('testRunModel')}</label>
          {hasCatalogue && (
            <Dropdown
              inputId="testrun-model"
              // `null` until something is picked shows the placeholder.
              value={custom ? CUSTOM : selectedEntry ? model : null}
              options={modelGroups}
              optionGroupLabel="label"
              optionGroupChildren="items"
              placeholder={t('testRunModelPlaceholder')}
              onChange={(event) => pickModel(event.value as string)}
            />
          )}
          {custom && (
            <InputText
              // Without a catalogue this is the only control, so it takes the
              // label's `htmlFor`; beside the picker it names itself.
              id={hasCatalogue ? 'testrun-model-input' : 'testrun-model'}
              ref={modelInput}
              className="testrun-model-id"
              aria-label={hasCatalogue ? t('testRunModelId') : undefined}
              placeholder={t('testRunModelIdPlaceholder')}
              value={model}
              spellCheck={false}
              onChange={(event) => setModel(event.target.value)}
            />
          )}
          {selectedEntry && selectedProvider && (
            <div className="testrun-chips">
              <Tag severity="secondary" value={selectedProvider.provider} />
              {selectedEntry.routing === 'fallback' && (
                <Tag severity="warning" value={t('testRunFallbackHint')} />
              )}
              {!selectedProvider.key_present && <Tag severity="warning" value={t('testRunNoKey')} />}
            </div>
          )}
        </div>

        <div className="field">
          <label htmlFor="testrun-project">{t('testRunProject')}</label>
          <Dropdown
            inputId="testrun-project"
            value={project ?? ''}
            // A project admin has no "no project" run: the server refuses an
            // unscoped test for them, so the option is not offered.
            options={
              isAdmin
                ? [
                    { label: t('testRunProjectGlobal'), value: '' },
                    ...(projects.data?.projects ?? []).map((entry) => ({
                      label: entry.name,
                      value: entry.name,
                    })),
                  ]
                : managedProjects.map((name) => ({ label: name, value: name }))
            }
            placeholder={isAdmin ? undefined : t('testRunProjectPlaceholder')}
            onChange={(event) => setProject((event.value as string) || null)}
          />
        </div>
      </div>

      <div className="testrun-actions">
        <Button type="button" label={t('testRunGo')} disabled={!canRun} onClick={handleRun} />
        {/* A sibling status note, not a swap of the button's own label --
            the button's accessible name must stay `t('testRunGo')` so it is
            still reachable by that name while a run is in flight. */}
        {/* aria-live: the button's own label never changes (see above), so
            without this a screen-reader user gets no announcement at all that
            a run has started -- only a button that has gone quiet. */}
        {test.isPending && (
          <span className="testrun-status" aria-live="polite">
            <span className="testrun-spinner" aria-hidden="true" />
            {t('testRunPending')}
          </span>
        )}
        {!mayRun && (
          <span className="testrun-status" aria-live="polite">
            {t('testRunAdminOnly')}
          </span>
        )}
      </div>

      {test.isError && (
        <Message
          severity="error"
          className="testrun-error"
          text={(test.error as Error)?.message}
          style={{ justifyContent: 'flex-start' }}
        />
      )}

      {test.data && (
        <div className="testrun-result">
          <div className="testrun-chips">
            <Tag severity="secondary" style={{ gap: 6 }}>
              <span className="testrun-chip-label">{t('testRunLatency')}</span>
              {test.data.latency_ms} ms
            </Tag>
            {test.data.usage && (
              <Tag severity="secondary" title={t('testRunTokensHint')} style={{ gap: 6 }}>
                <span className="testrun-chip-label">{t('testRunTokens')}</span>
                {t('testRunTokensValue', {
                  input: test.data.usage.input_tokens.toLocaleString(lang),
                  output: test.data.usage.output_tokens.toLocaleString(lang),
                })}
                {test.data.usage.reasoning_tokens != null &&
                  ` ${t('testRunTokensReasoning', {
                    reasoning: test.data.usage.reasoning_tokens.toLocaleString(lang),
                  })}`}
              </Tag>
            )}
            <Tag severity="secondary" title={t('testRunRoute')} style={{ gap: 6 }}>
              <span className="testrun-chip-label">{t('testRunRoute')}</span>
              <code>
                {test.data.resolved.provider} / {test.data.resolved.model}
              </code>
            </Tag>
            <Tag
              severity="secondary"
              value={
                test.data.resolved.credential_scope === 'project'
                  ? t('testRunScopeProject')
                  : t('testRunScopeGlobal')
              }
            />
          </div>
          <div className="testrun-output">
            <MarkdownView text={test.data.text} />
          </div>
        </div>
      )}

      <div className="testrun-hint">
        <Link to="/admin/llm">{t('testRunAddHint')}</Link>
      </div>
    </section>
  )
}
