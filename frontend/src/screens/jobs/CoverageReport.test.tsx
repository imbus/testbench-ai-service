import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CoverageReport } from './CoverageReport'
import type { CoverageResult } from '../../api/types'

const aspect = (id: string, statement: string) => ({
  id,
  statement,
  kind: 'happy_path' as const,
  source_quote: 'quote',
})

const REPORT: CoverageResult = {
  requirement_key: 'REQ-1',
  aspects: [
    {
      aspect: aspect('a1', 'Login works'),
      status: 'covered',
      weak_reason: null,
      evidence: [
        { set_key: 'S-1', test_case_key: 'TC-1', strength: 'full', evidence: 'logs in' },
      ],
      gap_reason: null,
      suggested_test: null,
    },
    {
      aspect: aspect('a2', 'Logout works'),
      status: 'covered',
      weak_reason: null,
      evidence: [],
      gap_reason: null,
      suggested_test: null,
    },
    {
      aspect: aspect('a3', 'Lockout after 3 tries'),
      status: 'weak',
      weak_reason: 'only_partial',
      evidence: [],
      gap_reason: null,
      suggested_test: null,
    },
    {
      aspect: aspect('a4', 'Password reset'),
      status: 'missing',
      weak_reason: null,
      evidence: [],
      gap_reason: 'Nothing tests the reset mail',
      suggested_test: { title: 'Reset mail arrives', description: 'Trigger a reset' },
    },
  ],
  sets_without_evidence: [{ set_key: 'S-9', reason: 'no_test_cases' }],
  skipped_comments: ['S-7'],
  reduced_mode: false,
  incomplete: false,
  set_paths: { 'S-1': 'Root / Login' },
}

test('summarises covered, weak and missing', () => {
  render(<CoverageReport report={REPORT} />)
  const summary = screen.getByTestId('coverage-summary')
  expect(summary).toHaveTextContent('2 Abgedeckt')
  expect(summary).toHaveTextContent('1 Schwach')
  expect(summary).toHaveTextContent('1 Fehlt')
  expect(summary).toHaveTextContent('REQ-1 · 4 Aspekte')
})

test('lists every aspect as a row with its status and evidence count', () => {
  render(<CoverageReport report={REPORT} />)
  const row = screen.getByText('Login works').closest('summary')
  expect(row).not.toBeNull()
  expect(within(row as HTMLElement).getByText('Abgedeckt')).toBeInTheDocument()
  expect(within(row as HTMLElement).getByText('1')).toBeInTheDocument()
})

test('a missing aspect starts open, a covered one opens on click', async () => {
  render(<CoverageReport report={REPORT} />)
  expect(screen.getByText('Nothing tests the reset mail')).toBeVisible()
  expect(screen.getByText(/logs in/)).not.toBeVisible()
  await userEvent.click(screen.getByText('Login works'))
  expect(screen.getByText(/logs in/)).toBeVisible()
})

test('names the weak reason in the row', () => {
  render(<CoverageReport report={REPORT} />)
  const row = screen.getByText('Lockout after 3 tries').closest('summary')
  expect(row).toHaveTextContent('nur teilweise belegt')
})

test('shows the gap and the suggested test of a missing aspect', () => {
  render(<CoverageReport report={REPORT} />)
  expect(screen.getByText('Nothing tests the reset mail')).toBeInTheDocument()
  expect(screen.getByText('Reset mail arrives')).toBeInTheDocument()
})

test('names a set by its path when known', () => {
  render(<CoverageReport report={REPORT} />)
  expect(screen.getByText(/Root \/ Login/)).toBeInTheDocument()
  expect(screen.queryByText(/S-1\b/)).not.toBeInTheDocument()
})

test('falls back to the set key without a path', () => {
  render(<CoverageReport report={REPORT} />)
  expect(screen.getByText(/S-9/)).toBeInTheDocument()
})

test('flags an incomplete report', () => {
  render(<CoverageReport report={{ ...REPORT, incomplete: true }} />)
  expect(screen.getByText(/nicht alle verknüpften/i)).toBeInTheDocument()
})

test('flags reduced mode', () => {
  render(<CoverageReport report={{ ...REPORT, reduced_mode: true }} />)
  expect(screen.getByText(/nur auf dem Titel/i)).toBeInTheDocument()
})

test('says nothing about incompleteness for a complete report', () => {
  render(<CoverageReport report={REPORT} />)
  expect(screen.queryByText(/nicht alle verknüpften/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/nur auf dem Titel/i)).not.toBeInTheDocument()
})
