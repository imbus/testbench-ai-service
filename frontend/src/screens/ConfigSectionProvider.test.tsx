/** The LLM screen's provider packages: shown for the global scope only. */
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { i18n } from '../i18n'
import { DraftProvider } from '../state/draft'
import { ConfigSection } from './ConfigSection'
import { llmPkg, ok, packages } from './packages/fixtures'

let disk: Record<string, unknown>

beforeEach(async () => {
  await i18n.changeLanguage('en')
  window.localStorage.clear()
  disk = {}
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/admin/api/agent-packages') return ok(packages({ packages: [llmPkg()] }))
      if (url.startsWith('/admin/api/config')) {
        return ok({
          running: { llm_config: { provider: 'openai', model: null }, projects: {} },
          disk,
          config_path: 'config.toml',
        })
      }
      return ok({})
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

function renderLlm(url = '/admin/llm', section: 'llm' | 'logging' = 'llm') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[url]}>
      <QueryClientProvider client={client}>
        <DraftProvider saved={disk}>
          <ConfigSection section={section} isAdmin issues={[]} />
        </DraftProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

test('the global LLM screen lists the provider packages', async () => {
  renderLlm()
  expect(await screen.findByRole('region', { name: 'Provider packages' })).toBeInTheDocument()
  expect(await screen.findByTestId('package-acme-llm')).toBeInTheDocument()
})

test('a project scope has no provider packages', async () => {
  disk = { projects: { Alpha: { llm_config: { timeout: 5 } } } }
  renderLlm('/admin/llm?project=Alpha')
  expect(await screen.findByRole('tab', { name: 'Alpha' })).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Provider packages' })).not.toBeInTheDocument()
})

test('other config screens have no provider packages', async () => {
  renderLlm('/admin/logging', 'logging')
  await screen.findByRole('heading', { name: 'Logging' })
  expect(screen.queryByRole('region', { name: 'Provider packages' })).not.toBeInTheDocument()
})

test('says where the class path comes from while a package provides the client', async () => {
  disk = {
    llm_config: {
      provider: 'custom',
      class_path: 'acme_llm.client.AcmeClient',
      package: 'acme-llm',
    },
  }
  renderLlm()
  expect(await screen.findByText(/Comes from the uploaded package acme-llm/)).toBeInTheDocument()
})

test('says nothing about a package for a hand-written custom provider', async () => {
  disk = { llm_config: { provider: 'custom', class_path: 'my.Client' } }
  renderLlm()
  await screen.findByRole('region', { name: 'Provider packages' })
  expect(screen.queryByText(/Comes from the uploaded package/)).not.toBeInTheDocument()
})
