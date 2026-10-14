/**
 * The render preview pane (design §5.6): an editable `agent_context` JSON
 * blob, rendered against a draft variant's messages through
 * `POST /prompts/render`. Admin-only -- the route is admin-gated because it
 * evaluates operator-supplied Jinja server-side.
 */
import { act, fireEvent, render, screen, waitFor, type RenderResult } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Lang } from '../i18n'
import type { PromptMessageDoc, PromptVarDecl, RenderResponse } from '../api/types'
import { RenderPreview } from './RenderPreview'
import { i18n } from '../i18n'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

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
  /** Defaults to false: the manual-render tests below predate live render. */
  active?: boolean
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
      <RenderPreview active={false} {...props} />
    </QueryClientProvider>,
  )
  return {
    ...utils,
    rerender: (next: Props) =>
      utils.rerender(
        <QueryClientProvider client={client}>
          <RenderPreview active={false} {...next} />
        </QueryClientProvider>,
      ),
  }
}

describe('RenderPreview', () => {
  it('prefills the context pane from the skeleton', () => {
    renderPreview({ messages: [], vars: {}, skeleton: { role: '' }, isAdmin: true })
    expect(screen.getByLabelText(/context/i)).toHaveValue(JSON.stringify({ role: '' }, null, 2))
  })

  it('keeps what the operator typed when the skeleton grows', async () => {
    const { rerender } = renderPreview({
      messages: [],
      vars: {},
      skeleton: { a: '' },
      isAdmin: true,
    })
    await userEvent.clear(screen.getByLabelText(/context/i))
    await userEvent.type(screen.getByLabelText(/context/i), '{{"a":"typed"}')
    rerender({ messages: [], vars: {}, skeleton: { a: '', b: '' }, isAdmin: true })
    expect(screen.getByLabelText(/context/i)).toHaveValue(
      JSON.stringify({ a: 'typed', b: '' }, null, 2),
    )
  })

  it('reports invalid JSON without rendering', async () => {
    renderPreview({ messages: [], vars: {}, skeleton: {}, isAdmin: true })
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
    renderPreview({ messages, vars: {}, skeleton: {}, isAdmin: true })
    await userEvent.click(screen.getByRole('button', { name: /render/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Undefined variable: foo/),
    )
  })

  // Every other test runs in English to keep its English-regex assertions
  // meaningful. This one exercises the German dictionary for real.
  it('renders German labels', async () => {
    await i18n.changeLanguage('de')
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
      })
      await userEvent.type(screen.getByLabelText('tone'), '!')
      await userEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))
      expect(screen.getByLabelText('tone')).toHaveValue('formal')
    })
  })

  describe('live render', () => {
    const tone: PromptVarDecl = {
      name: 'tone',
      description: null,
      value_type: 'string',
      choices: null,
      default_value: 'formal',
      required: false,
    }
    const base: Props = {
      messages: [],
      vars: { tone: 'formal' },
      decls: { tone },
      skeleton: {},
      isAdmin: true,
    }

    // Only the timeouts: the delay under test is a setTimeout.
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    const calls = () =>
      fetchMock.mock.calls.filter((call) => String(call[0]).startsWith('/admin/api/prompts/render'))
    const body = (index: number) =>
      JSON.parse(String((calls()[index][1] as RequestInit).body)) as {
        vars: Record<string, unknown>
      }
    const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
    // react-query hands results over through a setTimeout(0) of its own,
    // which the fake clock holds back -- `findBy*` alone would wait forever.
    const settle = async () => {
      for (let i = 0; i < 5; i++) await advance(0)
    }

    it('renders once when it becomes active, without a click', async () => {
      const { rerender } = renderPreview(base)
      expect(calls()).toHaveLength(0)
      rerender({ ...base, active: true })
      await settle()
      expect(screen.getByText('Hello')).toBeInTheDocument()
      expect(calls()).toHaveLength(1)
      await advance(1000)
      expect(calls()).toHaveLength(1)
    })

    it('sends nothing while inactive', async () => {
      renderPreview(base)
      fireEvent.change(screen.getByLabelText('tone'), { target: { value: 'casual' } })
      fireEvent.change(screen.getByLabelText(/context/i), { target: { value: '{"a": 1}' } })
      await advance(2000)
      expect(calls()).toHaveLength(0)
    })

    it('renders once on return when the inputs changed while away', async () => {
      const { rerender } = renderPreview({ ...base, active: true })
      await settle()
      rerender(base)
      fireEvent.change(screen.getByLabelText('tone'), { target: { value: 'casual' } })
      await advance(1000)
      expect(calls()).toHaveLength(1)
      rerender({ ...base, active: true })
      // No clock movement: the return renders without the delay.
      await advance(0)
      expect(calls()).toHaveLength(2)
      expect(body(1).vars).toEqual({ tone: 'casual' })
      // Unchanged inputs on the next return: nothing new to render.
      rerender(base)
      rerender({ ...base, active: true })
      await advance(1000)
      expect(calls()).toHaveLength(2)
    })

    it('re-renders once after a pause in the typing, not per keystroke', async () => {
      renderPreview({ ...base, active: true })
      await settle()
      const field = screen.getByLabelText('tone')
      fireEvent.change(field, { target: { value: 'c' } })
      await advance(300)
      fireEvent.change(field, { target: { value: 'ca' } })
      await advance(300)
      fireEvent.change(field, { target: { value: 'cas' } })
      await advance(499)
      expect(calls()).toHaveLength(1)
      await advance(1)
      expect(calls()).toHaveLength(2)
      expect(body(1).vars).toEqual({ tone: 'cas' })
    })

    it('sends nothing on invalid JSON and keeps the last result', async () => {
      renderPreview({ ...base, active: true })
      await settle()
      fireEvent.change(screen.getByLabelText(/context/i), { target: { value: '{ nope' } })
      await advance(500)
      expect(calls()).toHaveLength(1)
      expect(screen.getByText('The context is not valid JSON.')).toBeInTheDocument()
      expect(screen.getByText('Hello')).toBeInTheDocument()
    })

    it('ignores a stale response that lands after a newer one', async () => {
      const pending: ((body: RenderResponse) => void)[] = []
      fetchMock.mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            pending.push((value) => resolve(ok(value)))
          }),
      )
      renderPreview({ ...base, active: true })
      fireEvent.change(screen.getByLabelText('tone'), { target: { value: 'casual' } })
      await advance(500)
      expect(pending).toHaveLength(2)
      await act(async () => pending[1]({ messages: [{ role: 'user', content: 'Newer', error: null }] }))
      await settle()
      expect(screen.getByText('Newer')).toBeInTheDocument()
      await act(async () => pending[0]({ messages: [{ role: 'user', content: 'Older', error: null }] }))
      await settle()
      expect(screen.queryByText('Older')).not.toBeInTheDocument()
      expect(screen.getByText('Newer')).toBeInTheDocument()
    })

    it('renders at once from the Render button, cancelling the pending delay', async () => {
      renderPreview({ ...base, active: true })
      await settle()
      fireEvent.change(screen.getByLabelText('tone'), { target: { value: 'casual' } })
      fireEvent.click(screen.getByRole('button', { name: /^render$/i }))
      await advance(0)
      expect(calls()).toHaveLength(2)
      expect(body(1).vars).toEqual({ tone: 'casual' })
      await advance(1000)
      expect(calls()).toHaveLength(2)
    })
  })
})
