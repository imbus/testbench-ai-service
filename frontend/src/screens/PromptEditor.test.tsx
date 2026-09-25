/**
 * The prompt editor screen (design §5.6): an IDE-style workbench -- toolbar,
 * a variant/message tree, one centre pane (prompt.yaml header, variant
 * settings, or a single message), the variable sidebar and the
 * preview/test-run pane -- assembled on top of `promptDraftReducer`, seeded by
 * a `reset` dispatched from an effect once the document loads.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  ConfigResponse,
  LintError,
  PromptDocument,
  PromptPlanResponse,
  PromptSaveResponse,
} from '../api/types'
import type { Lang } from '../i18n'
import { PromptEditor } from './PromptEditor'

// CM6 needs DOM APIs jsdom lacks; the wrapper holds no logic (Task 10/13's
// ruling), so replacing it with a textarea costs no coverage. Mocked at the
// path MessagePane itself resolves `./CodeEditor` to. Also renders
// `diagnostics` as its own alert text -- the real CodeEditor feeds them into
// CodeMirror's lint gutter, which jsdom cannot render, but a screen test
// still needs *some* observable proof that a diagnostic reached this deep.
vi.mock('../components/CodeEditor', async () => {
  const { forwardRef, useImperativeHandle } = await import('react')
  return {
    CodeEditor: forwardRef(function MockCodeEditor(
      { value, onChange, ariaLabel, readOnly, diagnostics }: {
        value: string
        onChange: (value: string) => void
        ariaLabel: string
        readOnly?: boolean
        diagnostics?: LintError[]
      },
      ref,
    ) {
      useImperativeHandle(ref, () => ({ insert: (text: string) => onChange(value + text) }), [value, onChange])
      return (
        <div>
          <textarea
            aria-label={ariaLabel}
            value={value}
            readOnly={readOnly}
            onChange={(e) => onChange(e.target.value)}
          />
          {(diagnostics ?? []).map((error, index) => (
            <div key={index} role="alert">{error.message}</div>
          ))}
        </div>
      )
    }),
  }
})

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

/**
 * A copy of `DOC` whose 'Thorough' variant has three inline messages instead
 * of two, one per role so each has a distinct, unambiguous `aria-label`
 * (`editorLabel` renders a file-less message's own `role`).
 *
 * Needed for the diagnostics-invalidation-on-remove test: with only two
 * messages, removing the one BEFORE the flagged message shifts the flagged
 * one to index 0 and leaves nothing at its old index -- a stale (uncleared)
 * diagnostics map then points at an index past the end of the array, which
 * renders as "no alert" for the same reason a correctly-cleared map does.
 * That test cannot tell "cleared" from "silently out of range" apart, which
 * is exactly the misattribution bug it exists to catch. With three messages,
 * flagging the MIDDLE one and removing the FIRST leaves the flagged one's
 * old index (1) occupied by a DIFFERENT, real, rendered message (the one
 * that was last) -- a stale map now visibly (and wrongly) flags that one.
 */
function docWithThreeMessages(): PromptDocument {
  return {
    ...DOC,
    variants: [
      {
        name: 'Thorough',
        description: 'The careful one',
        model: null,
        vars: {},
        messages: [
          { role: 'system', source: 'inline', file: null, content: 'First message', readable: true },
          { role: 'user', source: 'inline', file: null, content: 'Middle message', readable: true },
          { role: 'assistant', source: 'inline', file: null, content: 'Last message', readable: true },
        ],
      },
      DOC.variants[1],
    ],
  }
}

/**
 * The second agent the toolbar's agent select can switch to. Shares the
 * variant name 'Quick' with `DOC`, and its `default_variant` is NOT
 * `variants[0]` -- so a switch that kept the previous selection by name, or
 * fell back to `variants[0]`, would each open the wrong variant.
 */
const OTHER_DOC: PromptDocument = {
  ...DOC,
  agent: 'other',
  file: 'de/other/prompt.yaml',
  name: 'Other',
  default_variant: 'Deep',
  variants: [
    {
      name: 'Quick',
      description: null,
      model: null,
      vars: {},
      messages: [{ role: 'user', source: 'inline', file: null, content: 'Other quick', readable: true }],
    },
    {
      name: 'Deep',
      description: null,
      model: null,
      vars: {},
      messages: [{ role: 'user', source: 'inline', file: null, content: 'Other deep', readable: true }],
    },
  ],
}

const CONFIG: ConfigResponse = {
  running: {},
  disk: { agents: { explainer: { prompt: { variant: 'Thorough' } } } },
  config_path: 'C:/svc/config.toml',
}

const SAVE_OK: PromptSaveResponse = {
  written: ['de/explainer/prompt.yaml'],
  created: [],
  deleted: [],
  deletions_skipped: null,
  backups: [],
}

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
/** What `POST /prompts/{lang}/{agent}/plan` answers. Defaults to a plan that
 * names a file the browser's own client-side diff could never have computed
 * (a deletion) -- proof the dialog's file list comes from the server, not
 * from `changedFiles`. */
let planResult: { status: 200; body: PromptPlanResponse } | { status: 422; detail: string }
/** What `POST /prompts/lint` answers for a given message body. Defaults to
 * clean; a test overrides it to make one message's content report an error. */
let lintResponder: (content: string) => { ok: boolean; errors: LintError[] }
/** Set by a test to make `POST /prompts/lint` fail instead of answering. */
let lintFailure: { status: number; detail: string } | null

beforeEach(() => {
  docBody = DOC
  putResult = { status: 200 }
  planResult = {
    status: 200,
    body: {
      created: [],
      updated: ['/p/de/explainer/prompt.yaml'],
      deleted: ['/p/de/explainer/user.jinja'],
      deletions_skipped: null,
    },
  }
  lintResponder = () => ({ ok: true, errors: [] })
  lintFailure = null
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (method === 'POST' && url.startsWith('/admin/api/prompts/lint')) {
      if (lintFailure) return fail(lintFailure.status, lintFailure.detail)
      const body = init?.body ? (JSON.parse(String(init.body)) as { content: string }) : { content: '' }
      return ok(lintResponder(body.content))
    }
    if (method === 'POST' && url.startsWith('/admin/api/prompts/render')) {
      return ok({ messages: [] })
    }
    // ABOVE the generic POST/PUT branches below: `/plan` is a POST to the
    // same `/admin/api/prompts/{lang}/{agent}` prefix the PUT below matches,
    // so it must be checked first or it would always fall through to the PUT
    // branch instead.
    if (method === 'POST' && url.endsWith('/plan')) {
      return planResult.status === 200 ? ok(planResult.body) : fail(planResult.status, planResult.detail)
    }
    if (method === 'PUT' && url.startsWith('/admin/api/prompts/')) {
      if (putResult.status === 200) return ok(SAVE_OK)
      return fail(putResult.status, putResult.detail)
    }
    // The toolbar's language/agent selects read the prompt tree. ABOVE the
    // generic document GET below only for readability -- it has no trailing
    // slash, so it never matched that branch anyway.
    if (method === 'GET' && url === '/admin/api/prompts') {
      return ok({ languages: [{ lang: 'de', prompts: [
        { agent: 'explainer', file: 'de/explainer/prompt.yaml', name: 'Explainer', variants: ['Thorough', 'Quick'], ok: true, error: null, used_by: [] },
        { agent: 'other', file: 'de/other/prompt.yaml', name: 'Other', variants: ['Quick', 'Deep'], ok: true, error: null, used_by: [] },
      ] }] })
    }
    if (method === 'GET' && url === '/admin/api/prompts/de/other') return ok(OTHER_DOC)
    if (method === 'GET' && url.startsWith('/admin/api/prompts/')) {
      return docBody ? ok(docBody) : fail(404, 'no such prompt')
    }
    return fail(404, 'no')
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  // The Split/Tabs choice persists in localStorage; without this a test that
  // picks Tabs would leak that layout into every later test.
  localStorage.clear()
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
    [{ path: '/admin/prompts/:lang/:agent', element: <PromptEditor lang={lang} isAdmin={isAdmin} /> }],
    { initialEntries: [`/admin/prompts/${docLang}/${agent}`] },
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
        path: '/admin/prompts/:lang/:agent',
        element: (
          <div>
            <Link to="/elsewhere">Elsewhere</Link>
            <PromptEditor lang={lang} isAdmin={isAdmin} />
          </div>
        ),
      },
      { path: '/elsewhere', element: <div data-testid="elsewhere">Elsewhere page</div> },
    ],
    { initialEntries: [`/admin/prompts/${docLang}/${agent}`] },
  )
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

const openMeta = () => userEvent.click(screen.getByRole('button', { name: /prompt\.yaml/ }))
const openVariantSettings = (name: string) =>
  userEvent.click(screen.getByRole('button', { name: `Variant settings: ${name}` }))
const openMessage = (label: RegExp) =>
  userEvent.click(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: label }))

/** The tree's message buttons for the selected variant (each starts with its role tag). */
function treeMessages() {
  return within(screen.getByTestId('prompt-tree')).queryAllByRole('button', {
    name: /^(system|user|assistant)/,
  })
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

function renderCalls() {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes('/prompts/render'))
}

describe('loading a document', () => {
  it('renders the header fields, variant selector, VarDeclTable and message tree', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    expect(treeMessages()).toHaveLength(2)

    await openMeta()
    expect(promptName()).toHaveValue('Explainer')
    expect(screen.getByLabelText('Summary')).toHaveValue('Explains defects')
    expect(header().getByLabelText('Description')).toHaveValue('The full description')
    expect(screen.getByLabelText('Default model')).toHaveValue('gpt-5.5')
    expect(screen.getByLabelText('Default variant')).toHaveValue('Thorough')

    expect(screen.getByRole('button', { name: 'Thorough' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quick' })).toBeInTheDocument()

    await openVariantSettings('Thorough')
    expect(screen.getAllByTestId('var-row')).toHaveLength(1)
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
    await openMeta()
    expect(promptName()).toHaveValue('Explainer')
  })

  it('renders without crashing when variants is empty', async () => {
    docBody = { ...DOC, variants: [], default_variant: '' }
    renderEditor({ lang: 'en' })
    await ready()
    expect(screen.queryAllByRole('button', { name: /^Variant settings:/ })).toHaveLength(0)
    expect(screen.queryAllByTestId('var-row')).toHaveLength(0)
    expect(treeMessages()).toHaveLength(0)
  })

  it('renders without crashing when the selected variant has no messages', async () => {
    docBody = {
      ...DOC,
      variants: [{ name: 'Empty', description: null, model: null, vars: {}, messages: [] }],
      default_variant: 'Empty',
    }
    renderEditor({ lang: 'en' })
    await ready()
    expect(treeMessages()).toHaveLength(0)
    // The default message selection falls through to the variant settings.
    expect(screen.getByText('This variant has no messages.')).toBeInTheDocument()
  })
})

describe('a non-admin session', () => {
  it('renders read-only fields with no Save or Render button', async () => {
    renderEditor({ lang: 'en', isAdmin: false })
    await ready()

    await openMeta()
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

    await openMeta()
    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    // The dialog's file list comes from the server's plan, not from the
    // browser's own diff -- `findByText` waits for that plan to resolve.
    expect(await within(dialog).findByText('/p/de/explainer/prompt.yaml')).toBeInTheDocument()
    expect(putCalls()).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))
    await waitFor(() => expect(putCalls()).toHaveLength(1))
  })

  it('names a deletion the browser could not have computed', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMeta()

    // Any edit at all: the dialog's contents come from the server, not from
    // the shape of the change.
    await userEvent.clear(promptName())
    await userEvent.type(promptName(), 'Renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('/p/de/explainer/user.jinja')).toBeInTheDocument()
    expect(screen.getByText('Deleted (no prompt references it any more):')).toBeInTheDocument()
  })

  it('shows a plan refusal inside the dialog rather than behind it', async () => {
    planResult = { status: 422, detail: "default_variant 'Gone' names no variant. Available: Thorough" }
    renderEditor({ lang: 'en' })
    await ready()

    await openMeta()
    await userEvent.clear(promptName())
    await userEvent.type(promptName(), 'Renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    // The dialog is open AND carries the reason. Phase 4a's M7 failure mode
    // was a marker rendered behind this overlay, i.e. nothing visible
    // happening.
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/default_variant/)
    expect(within(dialog).getByRole('button', { name: 'Confirm' })).toBeDisabled()
    // A plan 422 marks the offending field the same way a save 422 does --
    // both funnel through the same `markSaveError`, so the field marker
    // behind the dialog is not something only the save path produces.
    expect(screen.getByLabelText('Default variant')).toHaveAttribute('aria-invalid', 'true')
  })

  it('does not PUT until the operator confirms', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await openMeta()
    await userEvent.clear(promptName())
    await userEvent.type(promptName(), 'Renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByRole('dialog')

    expect(fetchMock.mock.calls.filter((call) => (call[1]?.method ?? '') === 'PUT')).toHaveLength(0)
  })

  it('calls nothing when the confirm is cancelled', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await openMeta()
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
    await openVariantSettings('Thorough')
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

    await openMeta()
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
    // The field marker lives in `MetaPane`'s `data-testid="prompt-header"`,
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

    await openMeta()
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

    await openMeta()
    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))

    // Marked on the tree's variant rows, the successor of the old chips.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Quick' })).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(screen.getByRole('button', { name: 'Thorough' })).not.toHaveAttribute('aria-invalid')
    expect(within(screen.getByRole('dialog')).getByText(/needs at least one message/)).toBeInTheDocument()
  })

  it('clears a stale 422 field marker once the operator edits that field', async () => {
    putResult = {
      status: 422,
      detail: "default_variant 'Ghost' names no variant. Available: Thorough, Quick",
    }
    renderEditor({ lang: 'en' })
    await ready()

    await openMeta()
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

    await openMeta()
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

    await openMeta()
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

    await openMeta()
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

    await openMeta()
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

    await openMeta()
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

    await userEvent.click(screen.getByRole('button', { name: 'New variant' }))
    // Added under a unique default name and opened in its settings pane, so
    // the operator renames it there.
    expect(screen.getByLabelText('Variant name')).toHaveValue('New variant')
    expect(screen.getByLabelText('Variants')).toHaveValue('New variant')
  })

  it('removes the selected variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: 'Quick' }))
    await openVariantSettings('Quick')
    // Scoped to the settings pane's own action block.
    const actions = screen.getByTestId('variant-actions')
    await userEvent.click(within(actions).getByRole('button', { name: /^remove$/i }))
    expect(screen.queryByRole('button', { name: 'Quick' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Thorough' })).toBeInTheDocument()
  })

  it('renames the selected variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await openVariantSettings('Thorough')
    await userEvent.clear(screen.getByLabelText('Variant name'))
    await userEvent.type(screen.getByLabelText('Variant name'), 'Renamed')
    expect(screen.getByRole('button', { name: 'Renamed' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thorough' })).not.toBeInTheDocument()
  })

  // The test above passes even with the selection-by-name bug, because the
  // fixture's 'Thorough' happens to be BOTH `variants[0]` and
  // `default_variant` -- the two things the resolution falls back to. This
  // renames the one variant that is neither.
  it('renames a variant that is neither the first nor the default', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: 'Quick' }))
    await openVariantSettings('Quick')
    await userEvent.clear(screen.getByLabelText('Variant name'))
    await userEvent.type(screen.getByLabelText('Variant name'), 'Speedy')

    expect(screen.getByRole('button', { name: 'Speedy' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quick' })).not.toBeInTheDocument()
    // The OTHER variant is untouched -- the bug renamed this one instead and
    // left 'Quick' named ''.
    expect(screen.getByRole('button', { name: 'Thorough' })).toBeInTheDocument()
    await openMeta()
    expect(screen.getByLabelText('Default variant')).toHaveValue('Thorough')
  })

  it('sets the selected variant model', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await openVariantSettings('Thorough')
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
    await openMessage(/Explain/)
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

  it('surfaces a failed lint request rather than just stopping the spinner', async () => {
    // A 403, a 500 or a dropped connection used to leave the operator with
    // no feedback at all -- every other action on this screen reports one.
    lintFailure = { status: 500, detail: 'Lint is unavailable' }
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Lint is unavailable'),
    )
    // And no false "clean" verdict alongside it.
    expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^lint$/i })).not.toBeDisabled()
  })

  it('reports no errors for a clean template', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))

    await waitFor(() => expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument())
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

  // A lint result is a snapshot of the content at the moment it ran. Editing,
  // removing, or reordering messages afterward must not leave a stale (or,
  // worse, mis-pointed) marker behind for the operator to trust by mistake.
  describe('invalidating a stale result', () => {
    function flagBroken() {
      lintResponder = (content) =>
        content.includes('BROKEN')
          ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
          : { ok: true, errors: [] }
    }

    it("clears a message's own error marker once its content is edited", async () => {
      flagBroken()
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Explain/)
      await userEvent.type(screen.getByLabelText('user'), 'BROKEN')
      await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
      await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())

      // The operator has changed exactly this text; the old result about it
      // must not still be showing.
      await userEvent.type(screen.getByLabelText('user'), '!')
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('clears every diagnostic when a message is removed, rather than shifting them onto the wrong message', async () => {
      // Three messages (see `docWithThreeMessages`'s own comment for why two
      // is not enough): the error is flagged on the MIDDLE one, and the
      // FIRST is removed. If `clearDiagnostics()` were missing, the stale
      // map (still keyed at index 1) would land on the message that shifts
      // INTO index 1 after the removal -- the one that was LAST, which never
      // had an error -- a surviving, rendered row, not an index the bug
      // could hide behind by falling off the end of the array. A message
      // other than the open one shows its diagnostics as `aria-invalid` on
      // its tree button, so that is where a stale marker would surface.
      docBody = docWithThreeMessages()
      flagBroken()
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Middle message/)
      await userEvent.type(screen.getByLabelText('user'), 'BROKEN')
      await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
      await waitFor(() =>
        expect(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: /Middle message/ }))
          .toHaveAttribute('aria-invalid', 'true'),
      )

      await openMessage(/First message/)
      await userEvent.click(screen.getByRole('button', { name: 'Delete message' }))
      expect(treeMessages()).toHaveLength(2)
      expect(treeMessages().filter((b) => b.getAttribute('aria-invalid') === 'true')).toHaveLength(0)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('clears every diagnostic when messages are reordered', async () => {
      flagBroken()
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Explain/)
      await userEvent.type(screen.getByLabelText('user'), 'BROKEN')
      await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
      await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())

      await userEvent.click(screen.getAllByRole('button', { name: /move (up|down)/i })[0])
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(treeMessages().filter((b) => b.getAttribute('aria-invalid') === 'true')).toHaveLength(0)
    })

    it('shows no "no syntax errors" on a clean message while another message is flagged', async () => {
      lintResponder = (content) =>
        content.includes('helpful')
          ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
          : { ok: true, errors: [] }
      renderEditor({ lang: 'en' })
      await ready()

      // The open message (index 1) is clean; the file-backed one (index 0) is not.
      await openMessage(/Explain/)
      await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
      await waitFor(() =>
        expect(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: /sys\.jinja/ }))
          .toHaveAttribute('aria-invalid', 'true'),
      )
      expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
    })

    it('shows no "no syntax errors" on the prompt.yaml tab while a message is flagged (Tabs)', async () => {
      lintResponder = (content) =>
        content.includes('Explain')
          ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
          : { ok: true, errors: [] }
      renderEditor({ lang: 'en' })
      await ready()
      await userEvent.click(screen.getByRole('radio', { name: 'Tabs' }))

      await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /Explain/ })).toHaveAttribute('aria-invalid', 'true'),
      )
      await userEvent.click(screen.getByRole('button', { name: 'prompt.yaml' }))
      expect(screen.getByTestId('prompt-header')).toBeInTheDocument()
      expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
    })

    it('does not keep a stale "no syntax errors" result after an edit', async () => {
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Explain/)
      await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
      await waitFor(() => expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument())

      await userEvent.type(screen.getByLabelText('user'), '!')
      expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
    })
  })
})

describe('the enum edge', () => {
  it('disables Save while ANY variant declares an enum var with no choices', async () => {
    // The offending var sits in 'Quick', which is NOT the selected variant --
    // the save sends every variant, so any one of them 422s it.
    docBody = {
      ...DOC,
      variants: [
        DOC.variants[0],
        {
          ...DOC.variants[1],
          vars: {
            mode: {
              name: 'mode',
              description: null,
              value_type: 'enum',
              choices: [],
              default_value: null,
              required: false,
            },
          },
        },
      ],
    }
    renderEditor({ lang: 'en' })
    await ready()

    // Dirty, so `!dirty` is not what is keeping Save disabled.
    await openMeta()
    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
  })

  it('leaves Save enabled once the enum has choices', async () => {
    renderEditor({ lang: 'en' })
    await ready()

    await openMeta()
    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')

    expect(screen.getByRole('button', { name: /^save$/i })).toBeEnabled()
  })
})

describe('sample vars for the render preview', () => {
  it('omits a var with no default rather than sending null', async () => {
    // `RenderRequest.vars` is dict[str, str | bool | int | float]; a single
    // null 422s the whole request, and FastAPI's 422 detail is a LIST, which
    // `apiFetch` cannot render -- the operator saw only "Request failed with
    // status 422". Four of this repo's eight prompts declare such a var.
    docBody = {
      ...DOC,
      variants: [
        {
          ...DOC.variants[0],
          vars: {
            ...DOC.variants[0].vars,
            glossary: {
              name: 'glossary',
              description: null,
              value_type: 'text',
              choices: null,
              default_value: null,
              required: false,
            },
          },
        },
        DOC.variants[1],
      ],
    }
    renderEditor({ lang: 'en' })
    await ready()

    await userEvent.click(screen.getByRole('button', { name: /^render$/i }))

    await waitFor(() => expect(renderCalls()).toHaveLength(1))
    const body = JSON.parse(String((renderCalls()[0][1] as RequestInit).body)) as {
      vars: Record<string, unknown>
    }
    expect(body.vars).toEqual({ tone: 'neutral' })
    expect(Object.values(body.vars)).not.toContain(null)
  })
})

describe('workbench navigation', () => {
  const tree = () => within(screen.getByTestId('prompt-tree'))

  it('shows the variant settings when the selected variant has no messages', async () => {
    docBody = { ...DOC, variants: [DOC.variants[0], { ...DOC.variants[1], messages: [] }] }
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    expect(screen.getByTestId('variant-actions')).toBeInTheDocument()
    expect(screen.getByText('This variant has no messages.')).toBeInTheDocument()
  })

  it('moves the selection to the previous message after removing the open one', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.click(screen.getByRole('button', { name: 'Delete message' }))
    expect(tree().getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-current', 'true')
    expect(tree().queryByRole('button', { name: /Explain/ })).not.toBeInTheDocument()
  })

  it('offers no Delete message on a one-message variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    // The reducer keeps a variant's last message (PromptVariant requires
    // one), so a Delete button there could only be a silent no-op.
    expect(screen.getByTestId('message-pane')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete message' })).not.toBeInTheDocument()
  })

  it('keeps the renamed variant selected while typing', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openVariantSettings('Thorough')
    await userEvent.type(screen.getByLabelText('Variant name'), 'X')
    expect(screen.getByLabelText('Variants')).toHaveValue('ThoroughX')
    expect(tree().getByRole('button', { name: 'ThoroughX' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('keeps the current agent selected when a dirty navigation is cancelled', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMeta()
    await userEvent.type(screen.getByLabelText('Summary'), '!')
    const agent = screen.getByLabelText('Agent')
    await within(agent).findByRole('option', { name: 'Other' })
    await userEvent.selectOptions(agent, 'other')
    expect(await screen.findByRole('heading', { name: /unsaved changes/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
    expect(screen.getByLabelText('Agent')).toHaveValue('explainer')
    expect(screen.getByLabelText('Summary')).toHaveValue('Explains defects!')
  })

  it("opens the new document's default variant on a clean agent switch", async () => {
    renderEditor({ lang: 'en' })
    await ready()
    // 'Quick' exists in both documents, so a selection kept by name would
    // survive the switch; 'Deep' is the new document's default, not its first.
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    expect(screen.getByLabelText('Variants')).toHaveValue('Quick')
    const agent = screen.getByLabelText('Agent')
    await within(agent).findByRole('option', { name: 'Other' })
    await userEvent.selectOptions(agent, 'other')
    await waitFor(() => expect(tree().getByRole('button', { name: 'Deep' })).toBeInTheDocument())
    expect(screen.getByLabelText('Variants')).toHaveValue('Deep')
    expect(tree().getByRole('button', { name: /Other deep/ })).toHaveAttribute('aria-current', 'true')
  })

  it('stays on the prompt.yaml pane after a successful save', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMeta()
    await userEvent.clear(screen.getByLabelText('Summary'))
    await userEvent.type(screen.getByLabelText('Summary'), 'New summary')
    // The refetch the save triggers returns the saved document -- a NEW
    // `document.data`, so the document reset really runs.
    docBody = { ...DOC, summary: 'New summary' }
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('/p/de/explainer/prompt.yaml')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))
    // Clean again: the draft was reset from the refetched document.
    await waitFor(() => expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled())
    expect(screen.getByTestId('prompt-header')).toBeInTheDocument()
    expect(screen.getByLabelText('Summary')).toHaveValue('New summary')
  })

  it('declares an undeclared variable from the sidebar', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.type(screen.getByLabelText('user'), ' {{{{ vars.depth }}')
    await userEvent.click(within(screen.getByTestId('var-sidebar')).getByRole('button', { name: 'declare' }))
    await openVariantSettings('Thorough')
    expect(screen.getAllByTestId('var-row')).toHaveLength(2)
  })

  it('inserts a variable at the cursor from the sidebar', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.click(within(screen.getByTestId('var-sidebar')).getByRole('button', { name: /vars\.tone/ }))
    expect(screen.getByLabelText('user')).toHaveValue('Explain {{ agent.defect }}{{ vars.tone }}')
  })
})

describe('the Tabs layout', () => {
  it('replaces the tree with a tab strip, and persists across a reload', async () => {
    const first = renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(screen.getByRole('radio', { name: 'Tabs' }))
    expect(screen.queryByTestId('prompt-tree')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'prompt.yaml' })).toHaveAttribute('aria-pressed', 'false')

    first.unmount()
    renderEditor({ lang: 'en' })
    await ready()
    expect(screen.getByRole('radio', { name: 'Tabs' })).toBeChecked()
    expect(screen.queryByTestId('prompt-tree')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'prompt.yaml' })).toBeInTheDocument()
  })

  it('opens the variant settings from the tab strip', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(screen.getByRole('radio', { name: 'Tabs' }))
    await userEvent.click(screen.getByRole('button', { name: 'Variant settings: Thorough' }))
    expect(screen.getByTestId('variant-actions')).toBeInTheDocument()
  })

  it('shows the variant settings for a variant with no messages', async () => {
    docBody = { ...DOC, variants: [{ ...DOC.variants[0], messages: [] }, DOC.variants[1]] }
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(screen.getByRole('radio', { name: 'Tabs' }))
    expect(screen.getByTestId('variant-actions')).toBeInTheDocument()
    expect(screen.getByText('This variant has no messages.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Variant settings: Thorough' })).toHaveAttribute('aria-pressed', 'true')
  })
})

// Every test above pins lang="en" to keep its English-text assertions
// meaningful. This is the one that exercises the real German default.
it('renders German labels by default', async () => {
  renderEditor({})
  await ready()
  expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument()
})
