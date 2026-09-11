/**
 * The prompt editor screen (design §5.6): header fields, a variant selector,
 * VarDeclTable and MessageList for the selected variant, and RenderPreview --
 * assembled on top of `promptDraftReducer`, seeded by a `reset` dispatched
 * from an effect once the document loads.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConfigResponse, PromptDocument, PromptSaveResponse } from '../api/types'
import type { Lang } from '../i18n'
import { PromptEditor } from './PromptEditor'

// CM6 needs DOM APIs jsdom lacks; the wrapper holds no logic (Task 10/13's
// ruling), so replacing it with a textarea costs no coverage. Mocked at the
// path MessageList itself resolves `./CodeEditor` to.
vi.mock('../components/CodeEditor', () => ({
  CodeEditor: ({
    value,
    onChange,
    ariaLabel,
    readOnly,
  }: {
    value: string
    onChange: (value: string) => void
    ariaLabel: string
    readOnly?: boolean
  }) => (
    <textarea
      aria-label={ariaLabel}
      value={value}
      readOnly={readOnly}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}))

const DOC: PromptDocument = {
  lang: 'de',
  agent: 'explainer',
  file: 'de/explainer/prompt.yaml',
  name: 'Explainer',
  summary: 'Explains defects',
  description: 'The full description',
  default_model: 'gpt-5.5',
  default_variant: 'Thorough',
  variants: [
    {
      name: 'Thorough',
      description: 'The careful one',
      model: null,
      vars: {
        tone: {
          name: 'tone',
          description: null,
          value_type: 'string',
          choices: null,
          default_value: 'neutral',
          required: false,
        },
      },
      messages: [
        { role: 'system', source: 'file', file: 'sys.jinja', content: 'You are helpful.', readable: true },
        { role: 'user', source: 'inline', file: null, content: 'Explain {{ agent.defect }}', readable: true },
      ],
    },
    {
      name: 'Quick',
      description: null,
      model: null,
      vars: {},
      messages: [{ role: 'user', source: 'inline', file: null, content: 'Quick', readable: true }],
    },
  ],
  agent_context_skeleton: { defect: '' },
}

const CONFIG: ConfigResponse = {
  running: {},
  disk: { agents: { explainer: { prompt: { variant: 'Thorough' } } } },
  config_path: 'C:/svc/config.toml',
}

const SAVE_OK: PromptSaveResponse = { written: ['de/explainer/prompt.yaml'], backups: [] }

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function fail(status: number, detail: unknown) {
  return { ok: false, status, json: async () => ({ detail }) } as Response
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

let fetchMock: ReturnType<typeof vi.fn>
let docBody: PromptDocument | null
let putResult: { status: 200 } | { status: 409; detail: string } | { status: 422; detail: string }

beforeEach(() => {
  docBody = DOC
  putResult = { status: 200 }
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (method === 'PUT' && url.startsWith('/admin/api/prompts/')) {
      if (putResult.status === 200) return ok(SAVE_OK)
      return fail(putResult.status, putResult.detail)
    }
    if (method === 'GET' && url.startsWith('/admin/api/prompts/')) {
      return docBody ? ok(docBody) : fail(404, 'no such prompt')
    }
    return fail(404, 'no')
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderEditor({
  agent = 'explainer',
  docLang = 'de',
  isAdmin = true,
  lang,
}: { agent?: string; docLang?: string; isAdmin?: boolean; lang?: Lang } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/prompts/${docLang}/${agent}`]}>
        <Routes>
          <Route path="/prompts/:lang/:agent" element={<PromptEditor lang={lang} isAdmin={isAdmin} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function header() {
  return within(screen.getByTestId('prompt-header'))
}

function promptName() {
  return header().getByLabelText('Name')
}

async function ready() {
  await waitFor(() => expect(screen.getByTestId('prompt-editor')).toBeInTheDocument())
}

function putCalls() {
  return fetchMock.mock.calls.filter(
    (call) => String((call[1] as RequestInit | undefined)?.method).toUpperCase() === 'PUT',
  )
}

describe('loading a document', () => {
  it('renders the header fields, variant selector, VarDeclTable and MessageList', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    expect(promptName()).toHaveValue('Explainer')
    expect(screen.getByLabelText('Summary')).toHaveValue('Explains defects')
    expect(header().getByLabelText('Description')).toHaveValue('The full description')
    expect(screen.getByLabelText('Default model')).toHaveValue('gpt-5.5')
    expect(screen.getByLabelText('Default variant')).toHaveValue('Thorough')

    expect(screen.getByRole('tab', { name: 'Thorough' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Quick' })).toBeInTheDocument()

    expect(screen.getAllByTestId('var-row')).toHaveLength(1)
    expect(screen.getAllByTestId('message-row')).toHaveLength(2)
  })

  // Phase 3's AgentDetail crashed with "Rendered more hooks than during the
  // previous render" because a hook sat below the loading/error guards, so
  // the hook count changed between the loading and loaded renders. Mounting
  // while the query is pending and then resolving it exercises exactly that
  // transition on THIS screen, which has more hooks than any other.
  it('does not crash moving from loading to loaded (hook order)', async () => {
    const deferred = deferredResponse()
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.startsWith('/admin/api/config')) return ok(CONFIG)
      if (method === 'GET' && url.startsWith('/admin/api/prompts/')) return deferred.promise
      return fail(404, 'no')
    })

    renderEditor({ lang: 'en' })
    // Still loading: the document query has not resolved yet.
    expect(screen.queryByTestId('prompt-editor')).not.toBeInTheDocument()

    deferred.resolve(ok(DOC))
    await ready()
    expect(promptName()).toHaveValue('Explainer')
  })

  it('renders without crashing when variants is empty', async () => {
    docBody = { ...DOC, variants: [], default_variant: '' }
    renderEditor({ lang: 'en' })
    await ready()
    expect(screen.queryAllByRole('tab')).toHaveLength(0)
    expect(screen.queryAllByTestId('var-row')).toHaveLength(0)
    expect(screen.queryAllByTestId('message-row')).toHaveLength(0)
  })

  it('renders without crashing when the selected variant has no messages', async () => {
    docBody = {
      ...DOC,
      variants: [{ name: 'Empty', description: null, model: null, vars: {}, messages: [] }],
      default_variant: 'Empty',
    }
    renderEditor({ lang: 'en' })
    await ready()
    expect(screen.queryAllByTestId('message-row')).toHaveLength(0)
  })
})

describe('a non-admin session', () => {
  it('renders read-only fields with no Save or Render button', async () => {
    renderEditor({ lang: 'en', isAdmin: false })
    await ready()

    expect(promptName()).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Default variant')).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^save$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^render$/i })).not.toBeInTheDocument()
  })
})

describe('saving', () => {
  it('opens a confirm naming the changed files and does not save until confirmed', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('de/explainer/prompt.yaml')).toBeInTheDocument()
    expect(putCalls()).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))
    await waitFor(() => expect(putCalls()).toHaveLength(1))
  })

  it('calls nothing when the confirm is cancelled', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')

    await userEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(putCalls()).toHaveLength(0)
  })

  it('warns about a variant a rename would orphan, before the save is refused', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    // Renaming the variant `config.disk` points at away from its current name.
    await userEvent.clear(screen.getByLabelText('Variant name'))
    await userEvent.type(screen.getByLabelText('Variant name'), 'Renamed')

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/the global agents table/)).toBeInTheDocument()
  })

  it('surfaces the server message from a 409 rather than a generic failure', async () => {
    putResult = {
      status: 409,
      detail:
        "This save would remove a variant that is still in use: 'Thorough' in the global agents table. Point the agent at a different variant first, then rename or remove this one.",
    }
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /Point the agent at a different variant first/,
      ),
    )
  })

  it('marks the offending field on a 422', async () => {
    putResult = {
      status: 422,
      detail: "default_variant 'Ghost' names no variant. Available: Thorough, Quick",
    }
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))

    await waitFor(() =>
      expect(screen.getByLabelText('Default variant')).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(screen.getByText(/names no variant/)).toBeInTheDocument()
  })
})

describe('unsaved changes', () => {
  it('warns before leaving the page with unsaved edits', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('does not warn when nothing has changed', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
  })
})

// Every test above pins lang="en" to keep its English-text assertions
// meaningful. This is the one that exercises the real German default.
it('renders German labels by default', async () => {
  renderEditor({})
  await ready()
  expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument()
})
