import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PromptMessageDoc } from '../../api/types'
import { TabsLayout } from './TabsLayout'

const MESSAGES: PromptMessageDoc[] = [
  { role: 'system', source: 'file', file: 'sys.jinja', content: 'x', readable: true },
  { role: 'user', source: 'inline', file: null, content: 'Explain it', readable: true },
]
const clean = { running: false, checked: true, error: null, errors: [] }

function setup(overrides: Partial<Parameters<typeof TabsLayout>[0]> = {}) {
  const props = {
    messages: MESSAGES, selection: { kind: 'message' as const, index: 0 }, flagged: [], readOnly: false,
    centre: <div>CENTRE</div>, variablesDrawer: <div>VARIABLES</div>, preview: <div>PREVIEW</div>, testRun: <div>TESTRUN</div>,
    status: { lint: clean, usedDeclared: 1, declared: 2, undeclared: 0 }, lang: 'en' as const,
    variantName: 'Thorough', onOpenMeta: vi.fn(), onOpenVariantSettings: vi.fn(), onPickMessage: vi.fn(), onAddMessage: vi.fn(), onLint: vi.fn(), ...overrides,
  }
  render(<TabsLayout {...props} />)
  return props
}

describe('TabsLayout', () => {
  it('renders prompt.yaml plus one tab per message, and picks them', async () => {
    const props = setup()
    expect(screen.getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /Explain it/ }))
    expect(props.onPickMessage).toHaveBeenCalledWith(1)
    await userEvent.click(screen.getByRole('button', { name: 'prompt.yaml' }))
    expect(props.onOpenMeta).toHaveBeenCalled()
    expect(screen.getByText('CENTRE')).toBeInTheDocument()
  })

  it('opens the variant settings from its own tab', async () => {
    const props = setup()
    const tab = screen.getByRole('button', { name: 'Variant settings: Thorough' })
    expect(tab).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(tab)
    expect(props.onOpenVariantSettings).toHaveBeenCalled()
  })

  it('presses the variant settings tab for a variant selection', () => {
    setup({ selection: { kind: 'variant' } })
    expect(screen.getByRole('button', { name: 'Variant settings: Thorough' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('marks a flagged message tab', () => {
    setup({ flagged: [0] })
    expect(screen.getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-invalid', 'true')
  })

  it('switches the drawer between Variables, Preview and Test run', async () => {
    setup()
    expect(screen.getByText('VARIABLES')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(screen.getByText('PREVIEW')).toBeInTheDocument()
    expect(screen.queryByText('VARIABLES')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Test run' }))
    expect(screen.getByText('TESTRUN')).toBeInTheDocument()
  })

  it('shows lint and usage in the status bar, and runs lint', async () => {
    const props = setup()
    expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument()
    expect(screen.getByText('1/2 declared vars used · 0 undeclared')).toBeInTheDocument()
    expect(screen.getByText('jinja · UTF-8')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
    expect(props.onLint).toHaveBeenCalled()
  })

  it('shows lint errors by line in the status bar', () => {
    setup({ status: { lint: { ...clean, errors: [{ line: 2, column: 1, message: 'bad' }] }, usedDeclared: 0, declared: 0, undeclared: 0 } })
    expect(screen.getByText('Line 2: bad')).toBeInTheDocument()
  })

  it('hides + message in a read-only session', () => {
    setup({ readOnly: true })
    expect(screen.queryByRole('button', { name: '+ message' })).not.toBeInTheDocument()
  })
})
