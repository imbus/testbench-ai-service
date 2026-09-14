import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PromptPlanResponse } from '../api/types'
import { SavePromptDialog } from './SavePromptDialog'

const PLAN: PromptPlanResponse = {
  created: ['/p/de/x/fresh.jinja'],
  updated: ['/p/de/x/prompt.yaml'],
  deleted: ['/p/de/x/old.jinja'],
  deletions_skipped: null,
}

describe('SavePromptDialog', () => {
  it('lists creations, updates and deletions as separate groups', () => {
    render(
      <SavePromptDialog plan={PLAN} error={null} pending={false} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    )
    expect(screen.getByText('Neu angelegt:')).toBeInTheDocument()
    expect(screen.getByText('/p/de/x/fresh.jinja')).toBeInTheDocument()
    expect(screen.getByText('Gelöscht (wird von keinem Prompt mehr verwendet):')).toBeInTheDocument()
    expect(screen.getByText('/p/de/x/old.jinja')).toBeInTheDocument()
  })

  it('explains why nothing will be deleted', () => {
    render(
      <SavePromptDialog
        plan={{ ...PLAN, deleted: [], deletions_skipped: 'de/broken/prompt.yaml could not be parsed' }}
        error={null}
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByText(/de\/broken\/prompt\.yaml/)).toBeInTheDocument()
  })

  it('shows a refusal inside the dialog', () => {
    render(
      <SavePromptDialog
        plan={null}
        error="default_variant names no variant"
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('default_variant names no variant')
  })

  it('cannot be confirmed while there is no plan', () => {
    render(
      <SavePromptDialog plan={null} error="nope" pending={false} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeDisabled()
  })
})
