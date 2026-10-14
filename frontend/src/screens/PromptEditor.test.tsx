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
import { i18n, type Lang } from '../i18n'
import { PromptEditor } from './PromptEditor'
import { chooseOption, dropdownValue, openDropdown } from '../test/prime'

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
      { value, onChange, ariaLabel, readOnly, diagnostics, modelKey }: {
        value: string
        onChange: (value: string) => void
        ariaLabel: string
        readOnly?: boolean
        diagnostics?: LintError[]
        modelKey?: string
      },
      ref,
    ) {
      useImperativeHandle(ref, () => ({ insert: (text: string) => onChange(value + text) }), [value, onChange])
      return (
        <div>
          <textarea
            aria-label={ariaLabel}
            data-model={modelKey}
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
/** What `POST /prompts/render` answers. */
let renderResponse: { messages: { role: string; content: string | null; error: string | null }[] }

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
  renderResponse = { messages: [] }
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (method === 'POST' && url.startsWith('/admin/api/prompts/lint')) {
      if (lintFailure) return fail(lintFailure.status, lintFailure.detail)
      const body = init?.body ? (JSON.parse(String(init.body)) as { content: string }) : { content: '' }
      return ok(lintResponder(body.content))
    }
    if (method === 'POST' && url.startsWith('/admin/api/prompts/render')) {
      return ok(renderResponse)
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
  // The pane height persists in localStorage.
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
  if (lang) void i18n.changeLanguage(lang)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [{ path: '/admin/prompts/:lang/:agent', element: <PromptEditor isAdmin={isAdmin} /> }],
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
  if (lang) void i18n.changeLanguage(lang)
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
            <PromptEditor isAdmin={isAdmin} />
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

// Scoped to the tree: a tab's close button is also a button named after the file.
const tree = () => within(screen.getByTestId('prompt-tree'))
const openMeta = () => userEvent.click(tree().getByRole('button', { name: /prompt\.yaml/ }))
const openVariantSettings = (name: string) =>
  userEvent.click(tree().getByRole('button', { name: `Variant settings: ${name}` }))
const openMessage = (label: RegExp) => userEvent.click(tree().getByRole('button', { name: label }))
/** Opens the ▶ Render tab from the tree; its own Render button is inside the preview. */
async function openRender() {
  await userEvent.click(tree().getByRole('button', { name: 'Render' }))
  return within(screen.getByTestId('render-preview'))
}

/** Pick an agent in the toolbar, once the prompt tree has loaded its options. */
async function pickAgent(name: string) {
  const list = await openDropdown(userEvent.setup(), 'Agent')
  await userEvent.click(await within(list).findByRole('option', { name, hidden: true }))
}

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
    expect(dropdownValue('Default variant')).toBe('Thorough')

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
    // The render endpoint is admin-gated and the preview renders nothing
    // without it, so there is no way to open an empty Render tab either.
    expect(screen.queryByRole('button', { name: 'Open render' })).not.toBeInTheDocument()
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

    await chooseOption(userEvent.setup(), 'Default variant', 'Quick')
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
    expect(dropdownValue('Variants')).toBe('New variant')
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

  it('offers no Remove on the only variant', async () => {
    docBody = { ...DOC, variants: [DOC.variants[0]] }
    renderEditor({ lang: 'en' })
    await ready()
    await openVariantSettings('Thorough')
    expect(within(screen.getByTestId('variant-actions')).queryByRole('button', { name: /^remove$/i }))
      .not.toBeInTheDocument()
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
    expect(dropdownValue('Default variant')).toBe('Thorough')
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
    // The live check of the message opened on load, which is not the
    // button's own request.
    await waitFor(() => expect(lintCalls()).toHaveLength(1))
    fetchMock.mockClear()

    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))

    // The 'Thorough' variant (selected by default) has two messages.
    await waitFor(() => expect(lintCalls()).toHaveLength(2))
    expect(
      lintCalls().every((call) => (call[1] as RequestInit | undefined)?.method === 'POST'),
    ).toBe(true)
  })

  // The open message is re-checked by itself: once when it opens, then after
  // every pause in the typing. The button stays for the whole variant.
  describe('live', () => {
    it('flags a syntax error while typing, without the Lint button', async () => {
      lintResponder = (content) =>
        content.includes('{% bad')
          ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
          : { ok: true, errors: [] }
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Explain/)
      await userEvent.type(screen.getByLabelText('user'), '{{% bad')

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent('Unexpected end of template'),
      )
      expect(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: /Explain/ }))
        .toHaveAttribute('aria-invalid', 'true')
    })

    it('clears the marker once the error is fixed', async () => {
      lintResponder = (content) =>
        content.includes('BROKEN')
          ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
          : { ok: true, errors: [] }
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Explain/)
      const editor = screen.getByLabelText('user')
      await userEvent.type(editor, 'BROKEN')
      await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())

      await userEvent.type(editor, '{Backspace>6/}')
      await waitFor(() => expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument())
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('checks a message as soon as it is opened', async () => {
      lintResponder = (content) =>
        content.includes('helpful')
          ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
          : { ok: true, errors: [] }
      renderEditor({ lang: 'en' })
      await ready()

      // Message 0 (sys.jinja, containing "helpful") is open on load.
      await waitFor(() =>
        expect(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: /sys\.jinja/ }))
          .toHaveAttribute('aria-invalid', 'true'),
      )
    })

    it('stays quiet when the live check cannot reach the server', async () => {
      // Only the button reports a failure; an alert on every typing pause
      // would drown the editor.
      lintFailure = { status: 500, detail: 'Lint is unavailable' }
      renderEditor({ lang: 'en' })
      await ready()

      await openMessage(/Explain/)
      await userEvent.type(screen.getByLabelText('user'), '!')
      await waitFor(() => expect(lintCalls().length).toBeGreaterThan(1))
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
    })
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
      // The live check re-flags the broken message where it now sits (index
      // 0, open after the delete) -- the only marker is on the message that
      // actually has the error, never on the one that shifted into index 1.
      await waitFor(() =>
        expect(treeMessages().map((b) => b.getAttribute('aria-invalid') === 'true')).toEqual([true, false]),
      )
      expect(treeMessages()[0]).toHaveAccessibleName(/Middle message/)
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
      // Only the moved (still broken) message is flagged, at its new index,
      // by the live check -- never the clean one that took its old place.
      await waitFor(() =>
        expect(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: /Explain/ }))
          .toHaveAttribute('aria-invalid', 'true'),
      )
      expect(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: /sys\.jinja/ }))
        .not.toHaveAttribute('aria-invalid')
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
  it('disables Save and says why while a message holds invalid Jinja', async () => {
    lintResponder = (content) =>
      content.includes('{% bad')
        ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
        : { ok: true, errors: [] }
    renderEditor({ lang: 'en' })
    await ready()

    await openMessage(/Explain/)
    const editor = screen.getByLabelText('user')
    await userEvent.type(editor, '{{% bad')

    // Dirty, so `!dirty` is not what is keeping Save disabled.
    await waitFor(() => expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled())
    expect(screen.getByTestId('save-blocked-jinja')).toHaveTextContent(
      'Cannot save: invalid Jinja in message 2 (user), Line 1: Unexpected end of template',
    )

    // Fixed, and still dirty (backspacing alone would restore the loaded text).
    await userEvent.type(editor, '{Backspace>6/}!')
    await waitFor(() => expect(screen.getByRole('button', { name: /^save$/i })).toBeEnabled())
    expect(screen.queryByTestId('save-blocked-jinja')).not.toBeInTheDocument()
  })

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

    const preview = await openRender()
    await userEvent.click(preview.getByRole('button', { name: /^render$/i }))

    await waitFor(() => expect(renderCalls()).toHaveLength(1))
    const body = JSON.parse(String((renderCalls()[0][1] as RequestInit).body)) as {
      vars: Record<string, unknown>
    }
    expect(body.vars).toEqual({ tone: 'neutral', glossary: '' })
    expect(Object.values(body.vars)).not.toContain(null)
  })

  it('sends false for an optional boolean with no default', async () => {
    // The runtime renders with a lenient Environment, where a missing
    // `vars.validate_output` is simply falsy; the preview's StrictUndefined
    // would instead fail `{% if vars.validate_output %}` outright.
    docBody = {
      ...DOC,
      variants: [
        {
          ...DOC.variants[0],
          vars: {
            ...DOC.variants[0].vars,
            validate_output: {
              name: 'validate_output',
              description: null,
              value_type: 'boolean',
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

    const preview = await openRender()
    await userEvent.click(preview.getByRole('button', { name: /^render$/i }))

    await waitFor(() => expect(renderCalls()).toHaveLength(1))
    const body = JSON.parse(String((renderCalls()[0][1] as RequestInit).body)) as {
      vars: Record<string, unknown>
    }
    expect(body.vars).toEqual({ tone: 'neutral', validate_output: false })
  })

  it('still omits a required var with no default', async () => {
    // Required means the caller must supply it, so the preview should keep
    // reporting it as missing rather than paper over it.
    docBody = {
      ...DOC,
      variants: [
        {
          ...DOC.variants[0],
          vars: {
            ...DOC.variants[0].vars,
            audience: {
              name: 'audience',
              description: null,
              value_type: 'text',
              choices: null,
              default_value: null,
              required: true,
            },
          },
        },
        DOC.variants[1],
      ],
    }
    renderEditor({ lang: 'en' })
    await ready()

    const preview = await openRender()
    await userEvent.click(preview.getByRole('button', { name: /^render$/i }))

    await waitFor(() => expect(renderCalls()).toHaveLength(1))
    const body = JSON.parse(String((renderCalls()[0][1] as RequestInit).body)) as {
      vars: Record<string, unknown>
    }
    expect(body.vars).toEqual({ tone: 'neutral' })
  })
})

describe('workbench navigation', () => {
  it('shows the variant settings when the selected variant has no messages', async () => {
    docBody = { ...DOC, variants: [DOC.variants[0], { ...DOC.variants[1], messages: [] }] }
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    expect(screen.getByTestId('variant-actions')).toBeInTheDocument()
    expect(screen.getByText('This variant has no messages.')).toBeInTheDocument()
  })

  it('shows the empty state after removing the message of the only open tab', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    // The single click replaces the preview tab, so Explain is the only tab.
    await openMessage(/Explain/)
    await userEvent.click(screen.getByRole('button', { name: 'Delete message' }))
    expect(tree().queryByRole('button', { name: /Explain/ })).not.toBeInTheDocument()
    expect(tree().getByRole('button', { name: /sys\.jinja/ })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('Open a message, prompt.yaml or the variant settings from the tree.')).toBeInTheDocument()
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
    expect(dropdownValue('Variants')).toBe('ThoroughX')
    expect(tree().getByRole('button', { name: 'ThoroughX' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('keeps the current agent selected when a dirty navigation is cancelled', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMeta()
    await userEvent.type(screen.getByLabelText('Summary'), '!')
    await pickAgent('Other')
    expect(await screen.findByRole('heading', { name: /unsaved changes/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
    expect(dropdownValue('Agent')).toBe('Explainer')
    expect(screen.getByLabelText('Summary')).toHaveValue('Explains defects!')
  })

  it("opens the new document's default variant on a clean agent switch", async () => {
    renderEditor({ lang: 'en' })
    await ready()
    // 'Quick' exists in both documents, so a selection kept by name would
    // survive the switch; 'Deep' is the new document's default, not its first.
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    expect(dropdownValue('Variants')).toBe('Quick')
    await pickAgent('Other')
    await waitFor(() => expect(tree().getByRole('button', { name: 'Deep' })).toBeInTheDocument())
    expect(dropdownValue('Variants')).toBe('Deep')
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

const strip = () => within(screen.getByRole('tablist', { name: 'Open editors' }))

describe('editor tabs', () => {
  it('opens the first message as a preview tab', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    expect(strip().getAllByRole('tab')).toHaveLength(1)
    expect(strip().getByRole('tab', { name: /sys\.jinja/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('replaces the preview tab on a single click and keeps a double-clicked one', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    expect(strip().getAllByRole('tab')).toHaveLength(1)
    await userEvent.dblClick(tree().getByRole('button', { name: /Explain/ }))
    await openMeta()
    expect(strip().getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      expect.stringContaining('Explain'),
      expect.stringContaining('prompt.yaml'),
    ])
  })

  it('pins a preview tab on the first edit and marks it unsaved', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.type(screen.getByLabelText('user'), '!')
    expect(strip().getByRole('button', { name: /Close .*\(unsaved changes\)/ })).toBeInTheDocument()
    await openMeta()
    expect(strip().getAllByRole('tab')).toHaveLength(2)
  })

  it('closes a tab, activating its right neighbour, and shows the empty state after the last', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.dblClick(tree().getByRole('button', { name: /sys\.jinja/ }))
    await userEvent.dblClick(tree().getByRole('button', { name: /prompt\.yaml/ }))
    await userEvent.click(strip().getByRole('tab', { name: /sys\.jinja/ }))
    await userEvent.click(strip().getByRole('button', { name: /^Close sys\.jinja/ }))
    expect(strip().getByRole('tab', { name: /prompt\.yaml/ })).toHaveAttribute('aria-selected', 'true')
    await userEvent.click(strip().getByRole('button', { name: /^Close prompt\.yaml/ }))
    expect(screen.getByText('Open a message, prompt.yaml or the variant settings from the tree.')).toBeInTheDocument()
  })

  it('closes the tab of a deleted message', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.dblClick(tree().getByRole('button', { name: /sys\.jinja/ }))
    await userEvent.dblClick(tree().getByRole('button', { name: /Explain/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete message' }))
    expect(strip().queryByRole('tab', { name: /Explain/ })).not.toBeInTheDocument()
    expect(strip().getByRole('tab', { name: /sys\.jinja/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps each variant’s tabs and restores them on the way back', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.dblClick(tree().getByRole('button', { name: /Explain/ }))
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    expect(strip().queryByRole('tab', { name: /Explain/ })).not.toBeInTheDocument()
    await userEvent.click(tree().getByRole('button', { name: 'Thorough' }))
    expect(strip().getByRole('tab', { name: /Explain/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps the tabs of a renamed variant', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.dblClick(tree().getByRole('button', { name: /Explain/ }))
    await openVariantSettings('Thorough')
    const field = screen.getByLabelText('Variant name')
    await userEvent.clear(field)
    await userEvent.type(field, 'Deep')
    expect(field).toHaveValue('Deep')
    expect(strip().getByRole('tab', { name: /Explain/ })).toBeInTheDocument()
  })

  it('keeps the open tabs through a save', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.dblClick(tree().getByRole('button', { name: /Explain/ }))
    await userEvent.type(screen.getByLabelText('user'), '!')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('/p/de/explainer/prompt.yaml')
    await userEvent.click(within(dialog).getByRole('button', { name: /^confirm$/i }))
    await waitFor(() => expect(putCalls()).toHaveLength(1))
    expect(JSON.stringify(JSON.parse(String((putCalls()[0][1] as RequestInit).body)))).not.toContain('"uid"')
    await waitFor(() => expect(strip().getByRole('tab', { name: /Explain/ })).toHaveAttribute('aria-selected', 'true'))
  })

  it('gives each message its own editor model', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    const first = screen.getByLabelText('system (sys.jinja)').getAttribute('data-model')
    await openMessage(/Explain/)
    const second = screen.getByLabelText('user').getAttribute('data-model')
    expect(first).toMatch(/^de\/explainer\//)
    expect(second).toMatch(/^de\/explainer\//)
    expect(first).not.toBe(second)
  })

  it('shows the variant settings for a variant loaded without messages', async () => {
    docBody = { ...DOC, variants: [{ ...DOC.variants[0], messages: [] }, DOC.variants[1]] }
    renderEditor({ lang: 'en' })
    await ready()
    expect(screen.getByTestId('variant-actions')).toBeInTheDocument()
    expect(strip().getByRole('tab', { name: /Thorough/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('clears every diagnostic when the selected variant is removed', async () => {
    lintResponder = (content) =>
      content.includes('helpful')
        ? { ok: false, errors: [{ line: 1, column: 1, message: 'Unexpected end of template' }] }
        : { ok: true, errors: [] }
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
    await waitFor(() => expect(tree().getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-invalid', 'true'))
    // Same variant: opening its settings no longer clears the diagnostics.
    await openVariantSettings('Thorough')
    expect(tree().getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-invalid', 'true')
    await userEvent.click(within(screen.getByTestId('variant-actions')).getByRole('button', { name: /^remove$/i }))
    expect(treeMessages()).toHaveLength(1)
    expect(treeMessages()[0]).not.toHaveAttribute('aria-invalid')
  })

  // The render preview and the test run post the open variant's messages;
  // their client-only uids must not ride along.
  it('sends the render preview no message uids', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    const preview = await openRender()
    await userEvent.click(preview.getByRole('button', { name: /^render$/i }))
    await waitFor(() => expect(renderCalls()).toHaveLength(1))
    expect(String((renderCalls()[0][1] as RequestInit).body)).not.toContain('"uid"')
  })
})

describe('the render tab', () => {
  it('opens from the tree and shows the rendered output in the centre', async () => {
    renderResponse = { messages: [{ role: 'user', content: 'Explain the crash', error: null }] }
    renderEditor({ lang: 'en' })
    await ready()
    const preview = await openRender()

    const tab = screen.getByRole('tab', { name: /Render/ })
    expect(tab).toHaveAttribute('aria-selected', 'true')
    expect(tab).toHaveTextContent('▶')
    // A single click opens it as the preview tab, in place of the message.
    expect(screen.getAllByRole('tab')).toHaveLength(1)
    expect(tree().getByRole('button', { name: 'Render' })).toHaveAttribute('aria-current', 'true')
    // The full-height preview replaces the editor; like prompt.yaml and the
    // settings it has no variable sidebar.
    expect(screen.queryByLabelText('user')).not.toBeInTheDocument()
    expect(screen.queryByTestId('var-sidebar')).not.toBeInTheDocument()

    await userEvent.click(preview.getByRole('button', { name: /^render$/i }))
    expect(await preview.findByText('Explain the crash')).toBeInTheDocument()
    expect(String((renderCalls()[0][1] as RequestInit).body)).not.toContain('"uid"')
  })

  it('opens pinned from the button at the end of the tab strip', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(screen.getByRole('button', { name: 'Open render' }))
    // Pinned: the first message's preview tab stays open beside it.
    expect(screen.getAllByRole('tab')).toHaveLength(2)
    const tab = screen.getByRole('tab', { name: /Render/ })
    expect(tab).toHaveAttribute('aria-selected', 'true')
    expect(within(tab).getByText('Render')).toHaveStyle({ fontStyle: 'normal' })
    expect(screen.getByTestId('render-preview')).toBeInTheDocument()
  })

  it('keeps the typed agent context across a tab switch', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    const preview = await openRender()
    const context = preview.getByLabelText('Context')
    await userEvent.clear(context)
    await userEvent.type(context, '{{"defect": "x"}')
    await openMessage(/Explain/)
    await openRender()
    expect(screen.getByLabelText('Context')).toHaveValue('{"defect": "x"}')
  })

  it('leaves only the test run in the bottom pane', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    const pane = screen.getByTestId('preview-pane')
    expect(within(pane).getByTestId('test-run-panel')).toBeInTheDocument()
    expect(within(pane).queryByTestId('render-preview')).not.toBeInTheDocument()
    // Kept mounted (its typed context survives a tab switch), but out of sight
    // until its tab is active.
    expect(screen.getByTestId('render-preview')).not.toBeVisible()

    await openRender()
    expect(screen.getByTestId('render-preview')).toBeVisible()
    expect(within(pane).queryByTestId('render-preview')).not.toBeInTheDocument()
    expect(within(pane).getByTestId('test-run-panel')).toBeInTheDocument()
  })
})

describe('creating a variable from the sidebar', () => {
  const newVarField = () => within(screen.getByTestId('var-sidebar')).getByLabelText('New variable name')

  it('declares it on the variant and inserts it at the cursor', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.type(newVarField(), 'audience{Enter}')
    expect(screen.getByLabelText('user')).toHaveValue('Explain {{ agent.defect }}{{ vars.audience }}')

    await openVariantSettings('Thorough')
    expect(screen.getAllByTestId('var-row')).toHaveLength(2)
  })

  it('only inserts a name that is already declared, keeping its settings', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.type(newVarField(), 'tone{Enter}')
    expect(screen.getByLabelText('user')).toHaveValue('Explain {{ agent.defect }}{{ vars.tone }}')

    await openVariantSettings('Thorough')
    expect(screen.getAllByTestId('var-row')).toHaveLength(1)
    // A re-declare would have reset the default to null.
    expect(within(screen.getByTestId('var-row')).getByDisplayValue('neutral')).toBeInTheDocument()
  })
})

// Every test above switches to English to keep its English-text assertions
// meaningful. This is the one that exercises the real German default.
it('renders German labels by default', async () => {
  renderEditor({})
  await ready()
  expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument()
})
