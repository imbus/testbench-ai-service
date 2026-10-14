import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PromptTreeResponse } from '../../api/types'
import { EditorToolbar } from './EditorToolbar'
import { i18n } from '../../i18n'
import { chooseOption, dropdownValue, openDropdown } from '../../test/prime'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

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
    canSave: true, showSave: true,
    onVariant: vi.fn(), onSave: vi.fn(), ...overrides,
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
    // The tree loads after the first render; the label tracks it.
    await waitFor(() => expect(dropdownValue('Agent')).toBe('Explainer'))
    const agents = await openDropdown(userEvent.setup(), 'Agent')
    expect(within(agents).getByRole('option', { name: 'Explainer', hidden: true })).toBeInTheDocument()
    expect(within(agents).queryByRole('option', { name: 'broken', hidden: true })).not.toBeInTheDocument()
  })

  it("switching language falls back to that language's first prompt", async () => {
    setup()
    const user = userEvent.setup()
    const languages = await openDropdown(user, 'Language')
    await within(languages).findByRole('option', { name: 'en', hidden: true })
    await user.keyboard('{Escape}')
    await chooseOption(user, 'Language', 'en')
    expect(await screen.findByTestId('params')).toHaveTextContent('en/reviewer')
  })

  it('steps through variants and disables the ends', async () => {
    const props = setup()
    expect(screen.getByRole('button', { name: 'Previous variant' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next variant' }))
    expect(props.onVariant).toHaveBeenCalledWith('Quick')
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
