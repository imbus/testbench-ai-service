import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTestPrompt } from '../api/mutations'
import { useModels, useProjects } from '../api/queries'
import type { PromptMessageDoc } from '../api/types'
import { useTranslations, type Lang } from '../i18n'

/** The picker's "Other model…" entry -- not a model id, so it can never collide with one. */
const CUSTOM = '__custom__'

/**
 * Run the draft variant being edited against a real model (design §5.7).
 *
 * The one console action that spends money -- so a run is never implicit,
 * the button is disabled the moment one is in flight (the backend's own 409
 * against a concurrent run is a backstop, not something this relies on), and
 * a non-admin never sees an enabled button at all.
 *
 * The model picker offers the catalogue (`GET /models`) but a model missing
 * from it must stay reachable: its "Other model…" entry reveals a free-text
 * `<input>` bound to the same state the picker writes, so typing a model the
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
  lang = 'de',
}: {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  agentContext: Record<string, unknown>
  isAdmin: boolean
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const [project, setProject] = useState<string | null>(null)
  const [model, setModel] = useState('')
  const [customPicked, setCustomPicked] = useState(false)
  const modelInput = useRef<HTMLInputElement>(null)
  const projects = useProjects()
  const models = useModels(project ?? undefined)
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
  const canRun = isAdmin && !test.isPending && model.trim() !== ''

  const handleRun = () => {
    test.mutate({ messages, vars, agent_context: agentContext, model, project })
  }

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
      <h3 className="testrun-title">{t.testRun}</h3>

      <div className="testrun-fields">
        <div className="field">
          <label htmlFor="testrun-model">{t.testRunModel}</label>
          {hasCatalogue && (
            <select
              id="testrun-model"
              className="input"
              value={custom ? CUSTOM : selectedEntry ? model : ''}
              onChange={(event) => pickModel(event.target.value)}
            >
              <option value="" disabled>
                {t.testRunModelPlaceholder}
              </option>
              {providers.map((provider) => (
                <optgroup
                  key={provider.provider}
                  label={
                    provider.key_present
                      ? provider.provider
                      : `${provider.provider} (${t.testRunNoKey})`
                  }
                >
                  {provider.models.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {`${entry.id} · ${entry.routing}`}
                    </option>
                  ))}
                </optgroup>
              ))}
              <option value={CUSTOM}>{t.testRunModelCustom}</option>
            </select>
          )}
          {custom && (
            <input
              // Without a catalogue this is the only control, so it takes the
              // label's `htmlFor`; beside the picker it names itself.
              id={hasCatalogue ? 'testrun-model-input' : 'testrun-model'}
              ref={modelInput}
              className="input testrun-model-id"
              aria-label={hasCatalogue ? t.testRunModelId : undefined}
              placeholder={t.testRunModelIdPlaceholder}
              value={model}
              spellCheck={false}
              onChange={(event) => setModel(event.target.value)}
            />
          )}
          {selectedEntry && selectedProvider && (
            <div className="testrun-chips">
              <span className="testrun-chip">{selectedProvider.provider}</span>
              {selectedEntry.routing === 'fallback' && (
                <span className="testrun-chip testrun-chip-warn">{t.testRunFallbackHint}</span>
              )}
              {!selectedProvider.key_present && (
                <span className="testrun-chip testrun-chip-warn">{t.testRunNoKey}</span>
              )}
            </div>
          )}
        </div>

        <div className="field">
          <label htmlFor="testrun-project">{t.testRunProject}</label>
          <select
            id="testrun-project"
            className="input"
            value={project ?? ''}
            onChange={(event) => setProject(event.target.value || null)}
          >
            <option value="">{t.testRunProjectGlobal}</option>
            {(projects.data?.projects ?? []).map((entry) => (
              <option key={entry.name} value={entry.name}>
                {entry.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="testrun-actions">
        <button type="button" className="btn btn-primary" disabled={!canRun} onClick={handleRun}>
          {t.testRunGo}
        </button>
        {/* A sibling status note, not a swap of the button's own label --
            the button's accessible name must stay `t.testRunGo` so it is
            still reachable by that name while a run is in flight. */}
        {/* aria-live: the button's own label never changes (see above), so
            without this a screen-reader user gets no announcement at all that
            a run has started -- only a button that has gone quiet. */}
        {test.isPending && (
          <span className="testrun-status" aria-live="polite">
            <span className="testrun-spinner" aria-hidden="true" />
            {t.testRunPending}
          </span>
        )}
        {!isAdmin && (
          <span className="testrun-status" aria-live="polite">
            {t.testRunAdminOnly}
          </span>
        )}
      </div>

      {test.isError && (
        <div role="alert" className="testrun-error">
          {(test.error as Error)?.message}
        </div>
      )}

      {test.data && (
        <div className="testrun-result">
          <div className="testrun-chips">
            <span className="testrun-chip">
              <span className="testrun-chip-label">{t.testRunLatency}</span>
              {test.data.latency_ms} ms
            </span>
            <span className="testrun-chip" title={t.testRunRoute}>
              <span className="testrun-chip-label">{t.testRunRoute}</span>
              <code>
                {test.data.resolved.provider} / {test.data.resolved.model}
              </code>
            </span>
            <span className="testrun-chip">
              {test.data.resolved.credential_scope === 'project'
                ? t.testRunScopeProject
                : t.testRunScopeGlobal}
            </span>
          </div>
          <pre className="testrun-output">{test.data.text}</pre>
        </div>
      )}

      <div className="testrun-hint">
        <Link to="/admin/llm">{t.testRunAddHint}</Link>
      </div>
    </section>
  )
}
