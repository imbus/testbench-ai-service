import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PromptTreeResponse } from '../../api/types'
import { EditorToolbar } from './EditorToolbar'

const TREE: PromptTreeResponse = { languages: [
  { lang: 'de', prompts: [
    { agent: 'explainer', file: 'de/explainer/prompt.yaml', name: 'Explainer', variants: ['Thorough', 'Quick'], ok: true, error: null, used_by: [] },
    { agent: 'broken', file: 'de/broken/prompt.yaml', name: null, variants: [], ok: false, error: 'bad yaml', used_by: [] },
  ] },
  { lang: 'en', prompts: [
    { agent: 'reviewer', file: 'en/reviewer/prompt.yaml', name: 'Reviewer', variants: ['A'], ok: true, error: null, used_by: [] },
  ] },
] }

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) =>
    url === '/admin/api/prompts'
      ? ({ ok: true, status: 200, json: async () => TREE } as Response)
      : ({ ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response)))
})
afterEach(() => vi.unstubAllGlobals())

function setup(overrides: Partial<Parameters<typeof EditorToolbar>[0]> = {}) {
  const props = {
    path: 'prompts/de/explainer/prompt.yaml', variants: ['Thorough', 'Quick'], selectedVariant: 'Thorough',
    layout: 'split' as const, canSave: true, showSave: true, lang: 'en' as const,
    onVariant: vi.fn(), onLayout: vi.fn(), onSave: vi.fn(), ...overrides,
  }
  function Screen() {
    const { lang = '', agent = '' } = useParams()
    return (
      <>
        <EditorToolbar docLang={lang} agentKey={agent} {...props} />
        <div data-testid="params">{lang}/{agent}</div>
      </>
    )
  }
  const router = createMemoryRouter([{ path: '/admin/prompts/:lang/:agent', element: <Screen /> }], {
    initialEntries: ['/admin/prompts/de/explainer'],
  })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return props
}

describe('EditorToolbar', () => {
  it('offers only prompts that parse, with the current one selected', async () => {
    setup()
    const agent = await screen.findByLabelText('Agent')
    await within(agent).findByRole('option', { name: 'Explainer' })
    expect(within(agent).queryByRole('option', { name: 'broken' })).not.toBeInTheDocument()
    expect(agent).toHaveValue('explainer')
  })

  it("switching language falls back to that language's first prompt", async () => {
    setup()
    const language = await screen.findByLabelText('Language')
    await within(language).findByRole('option', { name: 'en' })
    await userEvent.selectOptions(language, 'en')
    expect(await screen.findByTestId('params')).toHaveTextContent('en/reviewer')
  })

  it('steps through variants and disables the ends', async () => {
    const props = setup()
    expect(screen.getByRole('button', { name: 'Previous variant' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next variant' }))
    expect(props.onVariant).toHaveBeenCalledWith('Quick')
  })

  it('switches layout', async () => {
    const props = setup()
    await userEvent.click(screen.getByLabelText('Tabs'))
    expect(props.onLayout).toHaveBeenCalledWith('tabs')
  })

  it('disables Save when there is nothing saveable', () => {
    setup({ canSave: false })
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('hides Save for a non-admin', () => {
    setup({ showSave: false })
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })
})
