import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTestPrompt } from '../api/mutations'
import { useModels, useProjects } from '../api/queries'
import type { PromptMessageDoc } from '../api/types'
import { useTranslations, type Lang } from '../i18n'

/**
 * Run the draft variant being edited against a real model (design §5.7).
 *
 * The one console action that spends money -- so a run is never implicit,
 * the button is disabled the moment one is in flight (the backend's own 409
 * against a concurrent run is a backstop, not something this relies on), and
 * a non-admin never sees an enabled button at all.
 *
 * The model picker offers the catalogue (`GET /models`) but a model missing
 * from it must stay reachable: the `<select>` writes into the same state the
 * free-text `<input>` binds to, rather than replacing it, so typing a model
 * the catalogue has never heard of still reaches the request. There is no
 * add-model control here -- that lives on the LLM provider view.
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
  const projects = useProjects()
  const models = useModels(project ?? undefined)
  const test = useTestPrompt()

  const selectedRouting = (models.data?.providers ?? [])
    .flatMap((provider) => provider.models)
    .find((entry) => entry.id === model)?.routing

  // An empty model is a guaranteed 502 on a paid endpoint: the request reaches
  // a real client, which asks the provider about a model called "". The one
  // console action that spends money does not get to be spent on nothing.
  const canRun = isAdmin && !test.isPending && model.trim() !== ''

  const handleRun = () => {
    test.mutate({ messages, vars, agent_context: agentContext, model, project })
  }

  return (
    <div data-testid="test-run-panel" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h3 style={{ margin: 0, fontSize: 15 }}>{t.testRun}</h3>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 12 }}>{t.testRunModel}</span>
          {/* Writes into the free-text input's own state rather than a
              separate one -- picking a catalogue entry and typing a model
              the catalogue has never heard of are the same action from the
              request's point of view. */}
          <select
            className="input"
            value=""
            style={{ fontSize: 13 }}
            onChange={(event) => {
              if (event.target.value) setModel(event.target.value)
            }}
          >
            <option value="" />
            {(models.data?.providers ?? []).map((provider) => (
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
          </select>
          <input
            id="testrun-model-input"
            className="input"
            aria-label={t.testRunModel}
            value={model}
            onChange={(event) => setModel(event.target.value)}
            style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}
          />
          {selectedRouting === 'fallback' && (
            <span className="text-muted" style={{ fontSize: 11 }}>
              {t.testRunFallbackHint}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label htmlFor="testrun-project" style={{ fontSize: 12 }}>
            {t.testRunProject}
          </label>
          <select
            id="testrun-project"
            className="input"
            value={project ?? ''}
            style={{ fontSize: 13 }}
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

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!canRun}
          onClick={handleRun}
        >
          {t.testRunGo}
        </button>
        {/* A sibling status note, not a swap of the button's own label --
            the button's accessible name must stay `t.testRunGo` so it is
            still reachable by that name while a run is in flight. */}
        {/* aria-live: the button's own label never changes (see above), so
            without this a screen-reader user gets no announcement at all that
            a run has started -- only a button that has gone quiet. */}
        {test.isPending && (
          <span className="text-muted" aria-live="polite" style={{ fontSize: 12 }}>
            {t.testRunPending}
          </span>
        )}
        {!isAdmin && (
          <span className="text-muted" aria-live="polite" style={{ fontSize: 12 }}>
            {t.testRunAdminOnly}
          </span>
        )}
      </div>

      {test.isError && (
        <div role="alert" style={{ fontSize: 12, color: '#a33a2b' }}>
          {(test.error as Error)?.message}
        </div>
      )}

      {test.data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>{test.data.text}</pre>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t.testRunLatency}: {test.data.latency_ms} ms
          </div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t.testRunRoute}: {test.data.resolved.provider} / {test.data.resolved.model} (
            {test.data.resolved.credential_scope === 'project'
              ? t.testRunScopeProject
              : t.testRunScopeGlobal}
            )
          </div>
        </div>
      )}

      <div className="text-muted" style={{ fontSize: 12 }}>
        <Link to="/admin/llm">{t.testRunAddHint}</Link>
      </div>
    </div>
  )
}
