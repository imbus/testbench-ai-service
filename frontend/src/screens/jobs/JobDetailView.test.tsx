import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import type { JobSummary } from '../../api/types'
import { i18n } from '../../i18n'
import { formatDuration, jobSeconds, StatusLabel } from './JobDetailView'

beforeEach(() => i18n.changeLanguage('en'))

const job: JobSummary = {
  job_id: 'j1',
  agent_key: 'link_finder',
  project_key: 'p-1',
  project_name: 'Shop',
  root_key: null,
  root_uid: null,
  item_ids: [],
  status: 'succeeded',
  progress: null,
  error: null,
  warnings: [],
  report_type: null,
  created_at: '2026-10-13T10:00:00+00:00',
  updated_at: '2026-10-13T10:01:38+00:00',
  finished_at: '2026-10-13T10:01:38+00:00',
}

describe('formatDuration', () => {
  it('shows seconds alone under a minute', () => {
    expect(formatDuration(42)).toBe('42s')
  })

  it('pads seconds once minutes show, so the column lines up', () => {
    expect(formatDuration(98)).toBe('1m 38s')
    expect(formatDuration(120)).toBe('2m 00s')
  })

  it('drops seconds once hours show', () => {
    expect(formatDuration(3900)).toBe('1h 05m')
  })

  it('never shows a negative duration', () => {
    expect(formatDuration(-3)).toBe('0s')
  })
})

describe('jobSeconds', () => {
  it('measures a finished job from start to finish', () => {
    expect(jobSeconds(job, new Date('2030-01-01T00:00:00Z'))).toBe(98)
  })

  it('measures a running job up to now', () => {
    const running = { ...job, status: 'running' as const, finished_at: null }
    expect(jobSeconds(running, new Date('2026-10-13T10:00:42+00:00'))).toBe(42)
  })
})

describe('StatusLabel', () => {
  it.each([
    ['running', 'Running', '●'],
    ['succeeded', 'Succeeded', '✓'],
    ['failed', 'Failed', '✕'],
  ] as const)('marks %s with an icon as well as a color', (status, label, icon) => {
    render(<StatusLabel job={{ ...job, status }} />)
    const pill = screen.getByText(label).closest('[data-status]')!
    expect(pill).toHaveAttribute('data-status', status)
    // The icon is decoration for sighted users; the text carries the meaning.
    const glyph = pill.querySelector('[aria-hidden="true"]')
    expect(glyph).toHaveTextContent(icon)
  })
})
