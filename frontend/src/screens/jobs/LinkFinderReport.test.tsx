import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LinkFinderReport } from './LinkFinderReport'
import type { LinkFinderResult } from '../../api/types'

const REPORT: LinkFinderResult = {
  requirement_key: 'REQ-1',
  aspects: { A1: 'Login works', A2: 'Lockout after 3 tries' },
  candidates: [
    {
      set_key: 'S-1',
      set_unique_id: 'iTB-TC-26',
      set_title: 'Login',
      path: '/Auth/Login',
      spec_status: 'Released',
      confidence: 'high',
      covered_aspect_ids: ['A1', 'A2'],
      evidence: [
        { aspect_id: 'A1', test_case_key: 'TC-1', strength: 'full', evidence: 'logs in' },
        { aspect_id: 'A2', test_case_key: 'TC-2', strength: 'partial', evidence: 'fails twice' },
      ],
      already_linked_to: ['REQ-7'],
    },
    {
      set_key: 'S-2',
      set_unique_id: 'iTB-TC-67',
      set_title: 'Touch',
      path: '/Auth/Touch',
      spec_status: 'InProgress',
      confidence: 'low',
      covered_aspect_ids: ['A2'],
      evidence: [
        { aspect_id: 'A2', test_case_key: 'TC-3', strength: 'partial', evidence: 'locks once' },
      ],
      already_linked_to: [],
    },
  ],
  sets_screened: 18,
  sets_detailed: 8,
  empty_sets: ['S-9'],
  failed_sets: [],
  skipped_comments: ['S-2'],
  reduced_mode: false,
  incomplete: false,
  set_paths: { 'S-1': '/Auth/Login', 'S-2': '/Auth/Touch', 'S-9': '/Auth/Empty' },
}

test('summarises the candidates per confidence and the sets searched', () => {
  render(<LinkFinderReport report={REPORT} />)
  const summary = screen.getByTestId('link-summary')
  expect(summary).toHaveTextContent('1 Hoch')
  expect(summary).toHaveTextContent('0 Mittel')
  expect(summary).toHaveTextContent('1 Niedrig')
  expect(summary).toHaveTextContent('REQ-1 · 8 von 18 Testfallsätzen im Detail gelesen')
})

test('lists every candidate as a row with its confidence and aspects touched', () => {
  render(<LinkFinderReport report={REPORT} />)
  const row = screen.getByText('/Auth/Login').closest('summary')
  expect(row).not.toBeNull()
  expect(within(row as HTMLElement).getByText('Hoch')).toBeInTheDocument()
  expect(within(row as HTMLElement).getByText('2/2')).toBeInTheDocument()
})

test('names a candidate by its unique ID', () => {
  render(<LinkFinderReport report={REPORT} />)
  const row = screen.getByText('/Auth/Login').closest('summary')
  expect(within(row as HTMLElement).getByText('iTB-TC-26')).toBeInTheDocument()
})

test('a report from before the unique ID still shows its candidates', () => {
  const { set_unique_id: _, ...older } = REPORT.candidates[0]
  render(<LinkFinderReport report={{ ...REPORT, candidates: [older] }} />)
  expect(screen.getByText('/Auth/Login')).toBeInTheDocument()
})

test('shows a candidate evidence and its other links on click', async () => {
  render(<LinkFinderReport report={REPORT} />)
  expect(screen.getByText(/logs in/)).not.toBeVisible()
  await userEvent.click(screen.getByText('/Auth/Login'))
  expect(screen.getByText(/logs in/)).toBeVisible()
  expect(screen.getByText(/Login works · TC-1/)).toBeVisible()
  expect(screen.getByText(/REQ-7/)).toBeVisible()
})

test('says plainly that nothing was found', () => {
  render(<LinkFinderReport report={{ ...REPORT, candidates: [] }} />)
  expect(screen.getByText(/keine Kandidaten gefunden/i)).toBeInTheDocument()
})

test('names empty sets and skipped comments by path', () => {
  render(<LinkFinderReport report={REPORT} />)
  expect(screen.getByText(/\/Auth\/Empty/)).toBeInTheDocument()
  expect(screen.getByText(/Review-Kommentar nicht geschrieben für: \/Auth\/Touch/)).toBeInTheDocument()
})

test('flags an incomplete report and reduced mode', () => {
  render(<LinkFinderReport report={{ ...REPORT, incomplete: true, reduced_mode: true }} />)
  expect(screen.getByText(/unvollständig/i)).toBeInTheDocument()
  expect(screen.getByText(/nur auf dem Titel/i)).toBeInTheDocument()
})

test('says nothing about incompleteness for a complete report', () => {
  render(<LinkFinderReport report={REPORT} />)
  expect(screen.queryByText(/unvollständig/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/nur auf dem Titel/i)).not.toBeInTheDocument()
})
