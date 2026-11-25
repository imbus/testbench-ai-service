import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { i18n } from '../../i18n'
import { GenericReport, humanize } from './GenericReport'

beforeEach(() => i18n.changeLanguage('en'))

describe('humanize', () => {
  it('turns field names into labels', () => {
    expect(humanize('sets_screened')).toBe('Sets screened')
    expect(humanize('setsScreened')).toBe('Sets screened')
    expect(humanize('summary')).toBe('Summary')
  })

  it('keeps keys that are not field names', () => {
    expect(humanize('iTB-TC-1')).toBe('iTB-TC-1')
    expect(humanize('REQ_42')).toBe('REQ_42')
    expect(humanize('')).toBe('')
  })
})

describe('GenericReport', () => {
  it('lists short values with their labels', () => {
    render(
      <GenericReport
        report={{ requirement_key: 'REQ-1', incomplete: false, tags: ['a', 'b'], note: null }}
      />,
    )
    expect(screen.getByText('Requirement key').tagName).toBe('DT')
    expect(screen.getByText('REQ-1')).toBeInTheDocument()
    expect(screen.getByText('✕ No')).toBeInTheDocument()
    expect(screen.getByText('a, b', { normalizer: (text) => text })).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('shows a list of objects as a table', () => {
    render(
      <GenericReport
        report={{
          ratings: [
            { key: 'TC-1', score: 3 },
            { key: 'TC-2', score: 5 },
          ],
        }}
      />,
    )
    const table = screen.getByRole('table')
    expect(within(table).getByRole('columnheader', { name: 'Key' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Score' })).toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText('TC-2')).toBeInTheDocument()
  })

  it('opens what does not fit a table cell below its row', async () => {
    render(
      <GenericReport
        report={{ ratings: [{ key: 'TC-1', evidence: [{ step: 1, text: 'checked' }] }] }}
      />,
    )
    expect(screen.queryByText('checked')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Show details' }))
    expect(screen.getByText('checked')).toBeInTheDocument()
    expect(screen.getByText('Evidence')).toBeInTheDocument()
  })

  it('offers no details for a row that has none', () => {
    render(
      <GenericReport
        report={{
          ratings: [
            { key: 'TC-1', findings: [] },
            { key: 'TC-2', findings: [{ step: 1 }] },
          ],
        }}
      />,
    )
    expect(screen.getAllByRole('button', { name: 'Show details' })).toHaveLength(1)
  })

  it('renders prose as Markdown and never as HTML', () => {
    render(
      <GenericReport report={{ summary: '# Result\n\nAll **good**.\n\n<script>x()</script>' }} />,
    )
    expect(screen.getByRole('heading', { name: 'Result' })).toBeInTheDocument()
    expect(screen.getByText('good').tagName).toBe('STRONG')
    expect(document.querySelector('script')).toBeNull()
  })

  it('nests an object under its label', () => {
    render(<GenericReport report={{ totals: { passed: 4, by_set: { 'TCS-1': 2 } } }} />)
    expect(screen.getByText('Totals')).toBeInTheDocument()
    expect(screen.getByText('Passed')).toBeInTheDocument()
    expect(screen.getByText('TCS-1')).toBeInTheDocument()
  })

  it('links a URL without loading anything from it', () => {
    render(<GenericReport report={{ source: 'https://example.com/a' }} />)
    const link = screen.getByRole('link', { name: 'https://example.com/a' })
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows a report that is not an object', () => {
    render(<GenericReport report={['one', 'two']} />)
    expect(screen.getByText(/one/)).toBeInTheDocument()
  })

  it('switches to the stored JSON', async () => {
    render(<GenericReport report={{ answer: 42 }} />)
    await userEvent.click(screen.getByRole('button', { name: 'JSON' }))
    expect(screen.getByText(/"answer": 42/)).toBeInTheDocument()
  })

  it('stops laying out at a depth no report should have', () => {
    let report: unknown = { leaf: 'x'.repeat(200) }
    for (let i = 0; i < 12; i++) report = { level: { more: report, pad: 'y'.repeat(200) } }
    render(<GenericReport report={report} />)
    expect(document.querySelector('pre')).not.toBeNull()
  })
})

describe('prose and the JSON view', () => {
  it('marks multi-line prose so that its single line breaks are kept', () => {
    const { container } = render(<GenericReport report={{ note: 'line one\nline two' }} />)

    const prose = container.querySelector('.report-prose')
    expect(prose).not.toBeNull()
    expect(prose?.textContent).toContain('line one\nline two')
  })

  it('shows the stored JSON text when it is given', async () => {
    render(
      <GenericReport
        report={{ big: 12345678901234567000 }}
        json={'{\n  "big": 12345678901234567890\n}'}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'JSON' }))

    expect(screen.getByText(/12345678901234567890/)).toBeInTheDocument()
  })

  it('falls back to its own rendering without the stored text', async () => {
    render(<GenericReport report={{ answer: 42 }} />)
    await userEvent.click(screen.getByRole('button', { name: 'JSON' }))

    expect(screen.getByText(/"answer": 42/)).toBeInTheDocument()
  })
})
