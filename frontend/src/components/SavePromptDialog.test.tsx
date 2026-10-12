import { render, screen, within } from '@testing-library/react'
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
    // Scoped to each group's own testid, not a flat `getByText` anywhere in
    // the document -- a dialog that lumped all three arrays into one
    // undifferentiated list would otherwise pass this test unchanged, which
    // is exactly the behaviour this component exists to avoid.
    const created = within(screen.getByTestId('confirm-created'))
    expect(created.getByText('Neu angelegt:')).toBeInTheDocument()
    expect(created.getByText('/p/de/x/fresh.jinja')).toBeInTheDocument()

    const updated = within(screen.getByTestId('confirm-updated'))
    expect(updated.getByText('Geändert:')).toBeInTheDocument()
    expect(updated.getByText('/p/de/x/prompt.yaml')).toBeInTheDocument()

    const deleted = within(screen.getByTestId('confirm-deleted'))
    expect(deleted.getByText('Gelöscht (wird von keinem Prompt mehr verwendet):')).toBeInTheDocument()
    expect(deleted.getByText('/p/de/x/old.jinja')).toBeInTheDocument()
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

  it('cannot be confirmed while the plan request is still in flight', () => {
    render(
      <SavePromptDialog plan={null} error={null} pending={true} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Wird geprüft …' })).toBeDisabled()
  })

  it('cannot be confirmed while a save is in flight, even once a plan is in hand', () => {
    // The other test above leaves `plan === null` alone able to explain a
    // disabled Confirm; this isolates the `pending` half of
    // `disabled={pending || plan === null}` on its own, with a resolved,
    // non-null plan already in hand -- the state the dialog is actually in
    // once the operator has clicked Confirm and the PUT is in flight.
    render(
      <SavePromptDialog plan={PLAN} error={null} pending={true} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Wird gespeichert…' })).toBeDisabled()
  })
})
