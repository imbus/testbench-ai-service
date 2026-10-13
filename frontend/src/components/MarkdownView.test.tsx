import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { i18n } from '../i18n'
import { MarkdownView } from './MarkdownView'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

describe('MarkdownView', () => {
  it('renders Markdown as formatted content by default', () => {
    render(<MarkdownView text={'# Review\n\n- **one**\n- `two`'} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Review' })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('one').tagName).toBe('STRONG')
    expect(screen.getByText('two').tagName).toBe('CODE')
  })

  it('renders GitHub tables', () => {
    render(<MarkdownView text={'| a | b |\n|---|---|\n| 1 | 2 |'} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '2' })).toBeInTheDocument()
  })

  it('shows raw HTML as text, never as markup', () => {
    const { container } = render(<MarkdownView text={'<img src=x onerror="alert(1)"> <b>bold</b>'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  it('opens links in a new tab, away from the unsaved draft', () => {
    render(<MarkdownView text="[docs](https://example.com)" />)
    const link = screen.getByRole('link', { name: 'docs' })
    expect(link).toHaveAttribute('href', 'https://example.com')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('switches to the exact plain text the model receives', async () => {
    const text = '# Review\n\n**one**'
    render(<MarkdownView text={text} />)
    await userEvent.click(screen.getByRole('radio', { name: 'Plain text' }))
    expect(screen.queryByRole('heading')).toBeNull()
    expect(screen.getByTestId('markdown-plain')).toHaveTextContent(/^# Review\s+\*\*one\*\*$/)
    expect(screen.getByTestId('markdown-plain').textContent).toBe(text)
  })

  it('starts in the requested mode', () => {
    render(<MarkdownView text="**x**" defaultMode="plain" />)
    expect(screen.getByRole('radio', { name: 'Plain text' })).toBeChecked()
    expect(screen.getByTestId('markdown-plain')).toHaveTextContent('**x**')
  })
})
