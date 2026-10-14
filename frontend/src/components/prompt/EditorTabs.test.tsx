import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { EditorTabs, type EditorTab } from './EditorTabs'

beforeEach(() => i18n.changeLanguage('en'))

const TABS: EditorTab[] = [
  { id: 'meta', label: 'prompt.yaml', dirty: false, flagged: false, preview: false },
  { id: 'msg:a', label: 'sys.jinja', prefix: 'system', dirty: true, flagged: false, preview: false },
  { id: 'msg:b', label: 'Explain', prefix: 'user', dirty: false, flagged: true, preview: true },
]

function setup(active: EditorTab['id'] | null = 'msg:a') {
  const props = { tabs: TABS, active, onActivate: vi.fn(), onPin: vi.fn(), onClose: vi.fn() }
  render(<EditorTabs {...props} />)
  return props
}

describe('EditorTabs', () => {
  it('renders one tab per open editor and marks the active one', () => {
    setup()
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    expect(screen.getByRole('tab', { name: /sys\.jinja/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /prompt\.yaml/ })).toHaveAttribute('aria-selected', 'false')
  })

  it('shows the role prefix, the lint flag and the italic preview', () => {
    setup()
    const tab = screen.getByRole('tab', { name: /Explain/ })
    expect(tab).toHaveTextContent('user')
    expect(tab).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Explain')).toHaveStyle({ fontStyle: 'italic' })
  })

  it('names the close button after the tab and says when it is unsaved', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Close prompt.yaml' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close sys.jinja (unsaved changes)' })).toHaveAttribute('data-dirty', 'true')
  })

  it('activates on click, pins on double click, closes with × and middle click', async () => {
    const props = setup()
    await userEvent.click(screen.getByRole('tab', { name: /prompt\.yaml/ }))
    expect(props.onActivate).toHaveBeenCalledWith('meta')
    await userEvent.dblClick(screen.getByRole('tab', { name: /Explain/ }))
    expect(props.onPin).toHaveBeenCalledWith('msg:b')
    await userEvent.click(screen.getByRole('button', { name: 'Close prompt.yaml' }))
    expect(props.onClose).toHaveBeenCalledWith('meta')
    fireEvent(screen.getByRole('tab', { name: /Explain/ }), new MouseEvent('auxclick', { bubbles: true, button: 1 }))
    expect(props.onClose).toHaveBeenCalledWith('msg:b')
  })

  it('moves focus and activation between tabs with the arrow keys', async () => {
    const props = setup('msg:a')
    screen.getByRole('tab', { name: /sys\.jinja/ }).focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(props.onActivate).toHaveBeenLastCalledWith('msg:b')
    expect(screen.getByRole('tab', { name: /Explain/ })).toHaveFocus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(props.onActivate).toHaveBeenLastCalledWith('msg:a')
    await userEvent.keyboard('{ArrowLeft}')
    expect(props.onActivate).toHaveBeenLastCalledWith('meta')
  })

  it('closes the focused tab with Delete', async () => {
    const props = setup('msg:a')
    screen.getByRole('tab', { name: /sys\.jinja/ }).focus()
    await userEvent.keyboard('{Delete}')
    expect(props.onClose).toHaveBeenCalledWith('msg:a')
    expect(props.onActivate).not.toHaveBeenCalled()
  })

  it('keeps only the active tab in the tab order', () => {
    setup('msg:a')
    expect(screen.getByRole('tab', { name: /sys\.jinja/ })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tab', { name: /prompt\.yaml/ })).toHaveAttribute('tabindex', '-1')
  })

  it('renders a trailing slot after the tabs, outside the tablist', async () => {
    const onOpen = vi.fn()
    render(
      <EditorTabs
        tabs={TABS}
        active="meta"
        onActivate={vi.fn()}
        onPin={vi.fn()}
        onClose={vi.fn()}
        trailing={<button type="button" onClick={onOpen}>Open render</button>}
      />,
    )
    const button = screen.getByRole('button', { name: 'Open render' })
    // Not one of the tabs: arrow keys and the tab count stay the tabs' own.
    expect(screen.getByRole('tablist')).not.toContainElement(button)
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    await userEvent.click(button)
    expect(onOpen).toHaveBeenCalledOnce()
  })
})
