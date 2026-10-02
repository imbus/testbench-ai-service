/**
 * The render preview pane (design §5.6): an editable `agent_context` JSON
 * blob, rendered against a draft variant's messages through
 * `POST /prompts/render`. Admin-only -- the route is admin-gated because it
 * evaluates operator-supplied Jinja server-side.
 */
import { render, screen, waitFor, type RenderResult } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Lang } from '../i18n'
import type { PromptMessageDoc, PromptVarDecl, RenderResponse } from '../api/types'
import { RenderPreview } from './RenderPreview'

let fetchMock: ReturnType<typeof vi.fn>
let renderBody: RenderResponse

beforeEach(() => {
  renderBody = { messages: [{ role: 'user', content: 'Hello', error: null }] }
  fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/admin/api/prompts/render')) return ok(renderBody)
    return { ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

type Props = {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  decls?: Record<string, PromptVarDecl>
  skeleton: Record<string, unknown>
  isAdmin: boolean
  lang?: Lang
}

/** Keeps one QueryClient across a render/rerender pair, like the other screen tests. */
function renderPreview(
  props: Props,
): Omit<RenderResult, 'rerender'> & { rerender: (next: Props) => void } {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const utils = render(
    <QueryClientProvider client={client}>
      <RenderPreview {...props} />
    </QueryClientProvider>,
  )
  return {
    ...utils,
    rerender: (next: Props) =>
      utils.rerender(
        <QueryClientProvider client={client}>
          <RenderPreview {...next} />
        </QueryClientProvider>,
      ),
  }
}

describe('RenderPreview', () => {
  it('prefills the context pane from the skeleton', () => {
    renderPreview({ messages: [], vars: {}, skeleton: { role: '' }, isAdmin: true, lang: 'en' })
    expect(screen.getByLabelText(/context/i)).toHaveValue(JSON.stringify({ role: '' }, null, 2))
  })

  it('keeps what the operator typed when the skeleton grows', async () => {
    const { rerender } = renderPreview({
      messages: [],
      vars: {},
      skeleton: { a: '' },
      isAdmin: true,
      lang: 'en',
    })
    await userEvent.clear(screen.getByLabelText(/context/i))
    await userEvent.type(screen.getByLabelText(/context/i), '{{"a":"typed"}')
    rerender({ messages: [], vars: {}, skeleton: { a: '', b: '' }, isAdmin: true, lang: 'en' })
    expect(screen.getByLabelText(/context/i)).toHaveValue(
      JSON.stringify({ a: 'typed', b: '' }, null, 2),
    )
  })

  it('reports invalid JSON without rendering', async () => {
    renderPreview({ messages: [], vars: {}, skeleton: {}, isAdmin: true, lang: 'en' })
    await userEvent.clear(screen.getByLabelText(/context/i))
    await userEvent.type(screen.getByLabelText(/context/i), '{{ not json')
    await userEvent.click(screen.getByRole('button', { name: /render/i }))
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).startsWith('/admin/api/prompts/render')),
    ).toBe(false)
  })

  it('renders nothing at all for a non-admin', () => {
    // Design D3: the render route is admin-only, so do not offer it and 403.
    const { container } = renderPreview({
      messages: [],
      vars: {},
      skeleton: {},
      isAdmin: false,
      lang: 'en',
    })
    expect(screen.queryByRole('button', { name: /render/i })).not.toBeInTheDocument()
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a per-message error beside its output', async () => {
    renderBody = {
      messages: [{ role: 'user', content: '', error: 'Undefined variable: foo' }],
    }
    const messages: PromptMessageDoc[] = [
      { role: 'user', source: 'inline', file: null, content: '{{ foo }}', readable: true },
    ]
    renderPreview({ messages, vars: {}, skeleton: {}, isAdmin: true, lang: 'en' })
    await userEvent.click(screen.getByRole('button', { name: /render/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Undefined variable: foo/),
    )
  })

  // The component defaults to German (Field.tsx/AgentSwitch.tsx's own `lang = 'de'`
  // default) -- every other test above pins lang="en" to keep its English-regex
  // assertions meaningful. This one exercises the German dictionary for real.
  it('renders German labels by default', () => {
    renderPreview({ messages: [], vars: {}, skeleton: {}, isAdmin: true })
    expect(screen.getByRole('button', { name: 'Rendern' })).toBeInTheDocument()
  })

  describe('variables', () => {
    function decl(overrides: Partial<PromptVarDecl>): PromptVarDecl {
      return {
        name: 'x',
        description: null,
        value_type: 'string',
        choices: null,
        default_value: null,
        required: false,
        ...overrides,
      }
    }

    function sentVars(): Record<string, unknown> {
      const call = fetchMock.mock.calls.find((c) =>
        String(c[0]).startsWith('/admin/api/prompts/render'),
      )
      return JSON.parse(String((call?.[1] as RequestInit).body)).vars
    }

    it('prefills one control per declared var and sends what the operator typed', async () => {
      renderPreview({
        messages: [],
        vars: { tone: 'formal', strict: false },
        decls: {
          tone: decl({ name: 'tone', default_value: 'formal' }),
          strict: decl({ name: 'strict', value_type: 'boolean' }),
        },
        skeleton: {},
        isAdmin: true,
        lang: 'en',
      })
      const tone = screen.getByLabelText('tone')
      expect(tone).toHaveValue('formal')
      await userEvent.clear(tone)
      await userEvent.type(tone, 'casual')
      await userEvent.click(screen.getByRole('button', { name: /^render$/i }))
      await waitFor(() => expect(sentVars()).toEqual({ tone: 'casual', strict: false }))
    })

    it('omits a cleared required var and sends a cleared optional one as empty', async () => {
      renderPreview({
        messages: [],
        vars: { must: 'a', may: 'b' },
        decls: {
          must: decl({ name: 'must', required: true, default_value: 'a' }),
          may: decl({ name: 'may', default_value: 'b' }),
        },
        skeleton: {},
        isAdmin: true,
        lang: 'en',
      })
      await userEvent.clear(screen.getByLabelText(/must/))
      await userEvent.clear(screen.getByLabelText('may'))
      await userEvent.click(screen.getByRole('button', { name: /^render$/i }))
      await waitFor(() => expect(sentVars()).toEqual({ may: '' }))
    })

    it('resets edits back to the declared defaults', async () => {
      renderPreview({
        messages: [],
        vars: { tone: 'formal' },
        decls: { tone: decl({ name: 'tone', default_value: 'formal' }) },
        skeleton: {},
        isAdmin: true,
        lang: 'en',
      })
      await userEvent.type(screen.getByLabelText('tone'), '!')
      await userEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))
      expect(screen.getByLabelText('tone')).toHaveValue('formal')
    })
  })
})
