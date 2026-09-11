/**
 * The prompt editor screen (design §5.6): header fields, a variant selector,
 * VarDeclTable and MessageList for the selected variant, and RenderPreview --
 * assembled on top of `promptDraftReducer`, seeded by a `reset` dispatched
 * from an effect once the document loads.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConfigResponse, LintError, PromptDocument, PromptSaveResponse } from '../api/types'
import type { Lang } from '../i18n'
import { PromptEditor } from './PromptEditor'

// CM6 needs DOM APIs jsdom lacks; the wrapper holds no logic (Task 10/13's
// ruling), so replacing it with a textarea costs no coverage. Mocked at the
// path MessageList itself resolves `./CodeEditor` to. Also renders
// `diagnostics` as its own alert text -- the real CodeEditor feeds them into
// CodeMirror's lint gutter, which jsdom cannot render, but a screen test
// still needs *some* observable proof that a diagnostic reached this deep.
vi.mock('../components/CodeEditor', () => ({
  CodeEditor: ({
    value,
    onChange,
    ariaLabel,
    readOnly,
    diagnostics,
  }: {
    value: string
    onChange: (value: string) => void
    ariaLabel: string
    readOnly?: boolean
    diagnostics?: LintError[]
  }) => (
    <div>
      <textarea
        aria-label={ariaLabel}
        value={value}
        readOnly={readOnly}
        onChange={(e) => onChange(e.target.value)}
      />
      {(diagnostics ?? []).map((error, index) => (
        <div key={index} role="alert">
          {error.message}
        </div>
      ))}
    </div>
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
/** What `POST /prompts/lint` answers for a given message body. Defaults to
 * clean; a test overrides it to make one message's content report an error. */
let lintResponder: (content: string) => { ok: boolean; errors: LintError[] }

beforeEach(() => {
  docBody = DOC
  putResult = { status: 200 }
  lintResponder = () => ({ ok: true, errors: [] })
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (method === 'POST' && url.startsWith('/admin/api/prompts/lint')) {
      const body = init?.body ? (JSON.parse(String(init.body)) as { content: string }) : { content: '' }
      return ok(lintResponder(body.content))
    }
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

// A data router, not `<MemoryRouter>`/`<Routes>`: `PromptEditor` calls
// `useBlocker` unconditionally (Task 15 fix round, Finding 2), which only
// works inside a data router's context, regardless of whether the component
// itself sits behind a matched data route.
function renderEditor({
  agent = 'explainer',
  docLang = 'de',
  isAdmin = true,
  lang,
}: { agent?: string; docLang?: string; isAdmin?: boolean; lang?: Lang } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [{ path: '/prompts/:lang/:agent', element: <PromptEditor lang={lang} isAdmin={isAdmin} /> }],
    { initialEntries: [`/prompts/${docLang}/${agent}`] },
  )
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

/** Adds an in-app `<Link>` beside the editor and a second route to land on,
 * so a test can exercise `useBlocker`'s block on a real router navigation. */
function renderEditorWithNav({
  agent = 'explainer',
  docLang = 'de',
  isAdmin = true,
  lang,
}: { agent?: string; docLang?: string; isAdmin?: boolean; lang?: Lang } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      {
        path: '/prompts/:lang/:agent',
        element: (
          <div>
            <Link to="/elsewhere">Elsewhere</Link>
            <PromptEditor lang={lang} isAdmin={isAdmin} />
          </div>
        ),
      },
      { path: '/elsewhere', element: <div data-testid="elsewhere">Elsewhere page</div> },
    ],
    { initialEntries: [`/prompts/${docLang}/${agent}`] },
  )
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
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

function lintCalls() {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes('/prompts/lint'))
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

  it('marks the offending field on a 422, AND shows it in the still-open dialog', async () => {
    // The field marker lives in `<section data-testid="prompt-header">`,
    // which sits BEHIND the confirm dialog's `position:fixed` overlay -- an
    // operator with the dialog open must see the failure inside it too, or
    // Confirm silently does nothing from where they are looking (Task 15
    // review, Finding 1).
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
    // Dialog stays open (does not auto-close on a failed save) and carries
    // the message itself -- not only the (currently hidden-behind-it) field.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByText(/names no variant/)).toBeInTheDocument()
  })

  it('marks every variant a 422 names as having no messages', async () => {
    putResult = {
      status: 422,
      detail: 'Every variant needs at least one message. Empty: Quick',
    }
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Quick' })).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(screen.getByRole('tab', { name: 'Thorough' })).not.toHaveAttribute('aria-invalid')
    expect(within(screen.getByRole('dialog')).getByText(/needs at least one message/)).toBeInTheDocument()
  })

  it('clears a stale 422 field marker once the operator edits that field', async () => {
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

    await userEvent.selectOptions(screen.getByLabelText('Default variant'), 'Quick')
    expect(screen.getByLabelText('Default variant')).not.toHaveAttribute('aria-invalid')
  })

  it('clears a stale 422 field marker when the confirm dialog is cancelled', async () => {
    putResult = {
      status: 422,
      detail: "default_variant 'Ghost' names no variant. Available: Thorough, Quick",
    }
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    let dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))
    await waitFor(() =>
      expect(screen.getByLabelText('Default variant')).toHaveAttribute('aria-invalid', 'true'),
    )

    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^cancel$/i }))
    expect(screen.getByLabelText('Default variant')).not.toHaveAttribute('aria-invalid')

    // Reopening Save must not resurrect the stale marker either.
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    dialog = await screen.findByRole('dialog')
    expect(screen.getByLabelText('Default variant')).not.toHaveAttribute('aria-invalid')
  })

  it('does not replace the editor with an error page when a background refetch fails', async () => {
    // `useSavePrompt`'s `onSuccess` invalidates the document query; if THAT
    // refetch fails, react-query keeps the last good `data` and only flips
    // `isError` -- this must show as an inline banner, not the fatal
    // load-failure guard, or a successful save's own aftermath would destroy
    // the screen the operator is looking at.
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')

    docBody = null // the next GET (the post-save refetch) 404s
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))

    await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0))
    // Still the editor, not the fatal guard's full-page error.
    expect(screen.getByTestId('prompt-editor')).toBeInTheDocument()
    expect(promptName()).toBeInTheDocument()
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

  // Pins the exact bug fixed in the first round: on the render where
  // `document.data` first arrives, `draft` has not been `reset` yet, so
  // diffing against the raw query data (rather than `originalRef.current`)
  // read as spuriously dirty for one render -- long enough to register a
  // `beforeunload` listener nothing actually justified. `ready()`'s own
  // `waitFor` lets that whole loading -> loaded cascade settle before this
  // asserts, so a regression here would show as a `'beforeunload'` call this
  // spy catches, not as a failed dispatch-and-check (the false-negative shape
  // the two tests above cannot rule out by themselves).
  it('never registers a beforeunload listener across a clean load', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    renderEditor({ lang: 'en' })
    await ready()

    expect(addSpy.mock.calls.some((call) => call[0] === 'beforeunload')).toBe(false)
  })

  it('blocks an in-app navigation while dirty, and cancelling stays on the editor', async () => {
    renderEditorWithNav({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    await userEvent.click(screen.getByRole('link', { name: 'Elsewhere' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: /unsaved changes/i })).toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByTestId('elsewhere')).not.toBeInTheDocument()
    expect(screen.getByTestId('prompt-editor')).toBeInTheDocument()
  })

  it('leaves the editor on an in-app navigation when the operator confirms', async () => {
    renderEditorWithNav({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    await userEvent.click(screen.getByRole('link', { name: 'Elsewhere' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^leave anyway$/i }))

    await waitFor(() => expect(screen.getByTestId('elsewhere')).toBeInTheDocument())
    expect(screen.queryByTestId('prompt-editor')).not.toBeInTheDocument()
  })

  it('does not block an in-app navigation when the draft is clean', async () => {
    renderEditorWithNav({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('link', { name: 'Elsewhere' }))
    await waitFor(() => expect(screen.getByTestId('elsewhere')).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('variant controls', () => {
  it('adds a variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.type(screen.getByLabelText('New variant name'), 'Extra')
    await userEvent.click(screen.getByRole('button', { name: /^add variant$/i }))
    expect(screen.getByRole('tab', { name: 'Extra' })).toBeInTheDocument()
  })

  it('removes the selected variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('tab', { name: 'Quick' }))
    // Scoped: MessageList renders its own per-row "Remove" button, and
    // `Quick`'s one message means there is one on screen at the same time.
    const actions = screen.getByTestId('variant-actions')
    await userEvent.click(within(actions).getByRole('button', { name: /^remove$/i }))
    expect(screen.queryByRole('tab', { name: 'Quick' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Thorough' })).toBeInTheDocument()
  })

  it('renames the selected variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.clear(screen.getByLabelText('Variant name'))
    await userEvent.type(screen.getByLabelText('Variant name'), 'Renamed')
    expect(screen.getByRole('tab', { name: 'Renamed' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Thorough' })).not.toBeInTheDocument()
  })

  it('sets the selected variant model', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.type(screen.getByLabelText('Variant model'), 'gpt-5.5-mini')
    expect(screen.getByLabelText('Variant model')).toHaveValue('gpt-5.5-mini')
  })
})

describe('linting', () => {
  it('surfaces a Jinja syntax error to the operator', async () => {
    lintResponder = (content) =>
      content.includes('{% bad')
        ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
        : { ok: true, errors: [] }
    renderEditor({ lang: 'en' })
    await ready()

    // The 'Thorough' variant's inline ("user") message -- unique among its
    // two messages, unlike the file-backed one ("system (sys.jinja)").
    // userEvent.type treats `{`/`}` as special-key syntax, so a literal `{`
    // must be escaped as `{{`.
    await userEvent.type(screen.getByLabelText('user'), '{{% bad')
    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Unexpected end of template'),
    )
    // Not just the UI state -- the request that produced it.
    expect(lintCalls().length).toBeGreaterThan(0)
  })

  it('is available to a non-admin session', async () => {
    // Session-gated, not admin-gated (unlike Render): a read-only operator
    // must still be able to check a template's syntax.
    renderEditor({ lang: 'en', isAdmin: false })
    await ready()

    const button = screen.getByRole('button', { name: /^lint$/i })
    await userEvent.click(button)

    await waitFor(() => expect(lintCalls().length).toBeGreaterThan(0))
  })

  it('reports no errors for a clean template', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))

    await waitFor(() => expect(screen.getByText('No syntax errors.')).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('makes one lint request per message in the selected variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))

    // The 'Thorough' variant (selected by default) has two messages.
    await waitFor(() => expect(lintCalls()).toHaveLength(2))
    expect(
      lintCalls().every((call) => (call[1] as RequestInit | undefined)?.method === 'POST'),
    ).toBe(true)
  })
})

// Every test above pins lang="en" to keep its English-text assertions
// meaningful. This is the one that exercises the real German default.
it('renders German labels by default', async () => {
  renderEditor({})
  await ready()
  expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument()
})
