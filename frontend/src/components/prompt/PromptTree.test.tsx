import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PromptVariantDoc } from '../../api/types'
import { PromptTree } from './PromptTree'
import { i18n } from '../../i18n'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

const VARIANTS: PromptVariantDoc[] = [
  { name: 'Thorough', description: null, model: 'gpt-5.5', vars: {}, messages: [
    { role: 'system', source: 'file', file: 'sys.jinja', content: 'x', readable: true, uid: 's' },
    { role: 'user', source: 'inline', file: null, content: 'Explain {{ agent.defect }}', readable: true, uid: 'u' },
  ] },
  { name: 'Quick', description: null, model: null, vars: {}, messages: [] },
]

function setup(overrides = {}) {
  const props = {
    variants: VARIANTS, selectedVariant: 'Thorough', activeTab: 'msg:u' as const,
    flagged: [], readOnly: false,
    onOpenMeta: vi.fn(), onPickVariant: vi.fn(), onOpenVariantSettings: vi.fn(),
    onPickMessage: vi.fn(), onAddVariant: vi.fn(), onAddMessage: vi.fn(), onOpenRender: vi.fn(), ...overrides,
  }
  render(<PromptTree {...props} />)
  return props
}

describe('PromptTree', () => {
  it("lists only the selected variant's messages, by file or first line", () => {
    setup()
    const tree = screen.getByTestId('prompt-tree')
    expect(within(tree).getByRole('button', { name: /sys\.jinja/ })).toBeInTheDocument()
    expect(within(tree).getByRole('button', { name: /Explain \{\{ agent\.defect \}\}/ })).toHaveAttribute('aria-current', 'true')
  })

  it('picks a variant, a message, the meta row and the settings', async () => {
    const props = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Quick' }))
    expect(props.onPickVariant).toHaveBeenCalledWith('Quick')
    await userEvent.click(screen.getByRole('button', { name: /sys\.jinja/ }))
    expect(props.onPickMessage).toHaveBeenCalledWith(0, false)
    await userEvent.click(screen.getByRole('button', { name: /prompt\.yaml/ }))
    expect(props.onOpenMeta).toHaveBeenCalledWith(false)
    await userEvent.click(screen.getByRole('button', { name: 'Variant settings: Thorough' }))
    expect(props.onOpenVariantSettings).toHaveBeenCalledWith('Thorough', false)
  })

  it('pins on a double click', async () => {
    const props = setup()
    await userEvent.dblClick(screen.getByRole('button', { name: /sys\.jinja/ }))
    expect(props.onPickMessage).toHaveBeenLastCalledWith(0, true)
    await userEvent.dblClick(screen.getByRole('button', { name: /prompt\.yaml/ }))
    expect(props.onOpenMeta).toHaveBeenLastCalledWith(true)
  })

  it('marks the row of the active tab', () => {
    setup({ activeTab: 'meta' })
    expect(screen.getByRole('button', { name: /prompt\.yaml/ })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /Explain/ })).not.toHaveAttribute('aria-current')
  })

  it('flags a message with lint errors', () => {
    setup({ flagged: [0] })
    expect(screen.getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-invalid', 'true')
  })

  it('marks a variant a save refusal named', () => {
    setup({ invalidVariants: ['Quick'] })
    expect(screen.getByRole('button', { name: 'Quick' })).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('button', { name: 'Thorough' })).not.toHaveAttribute('aria-invalid')
  })

  it('renders a selected variant with no messages', () => {
    setup({ selectedVariant: 'Quick', activeTab: 'variant' })
    expect(screen.getByRole('button', { name: '+ message' })).toBeInTheDocument()
  })

  it('lists the referenced template files', () => {
    setup()
    expect(screen.getByText('sys.jinja', { selector: '[data-testid="tree-files"] *' })).toBeInTheDocument()
  })

  it('hides every add button in a read-only session', () => {
    setup({ readOnly: true })
    expect(screen.queryByRole('button', { name: '+ message' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New variant' })).not.toBeInTheDocument()
  })

  // Rendering is not an edit, so a read-only session sees the row too.
  it('opens the render tab from a row under the open variant', async () => {
    const props = setup({ readOnly: true })
    const row = screen.getByRole('button', { name: 'Render' })
    await userEvent.click(row)
    expect(props.onOpenRender).toHaveBeenLastCalledWith(false)
    await userEvent.dblClick(row)
    expect(props.onOpenRender).toHaveBeenLastCalledWith(true)
    expect(row).not.toHaveAttribute('aria-current')
  })

  it('marks the render row while the render tab is active', () => {
    setup({ activeTab: 'render' })
    expect(screen.getByRole('button', { name: 'Render' })).toHaveAttribute('aria-current', 'true')
  })

  it('has no render row without a handler', () => {
    setup({ onOpenRender: undefined })
    expect(screen.queryByRole('button', { name: 'Render' })).not.toBeInTheDocument()
  })
})
