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
      <SavePromptDialog
        plan={PLAN}
        error={null}
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    // Scoped to each group's own testid, not a flat `getByText` anywhere in
    // the document -- a dialog that lumped all three arrays into one
    // undifferentiated list would otherwise pass this test unchanged, which
    // is exactly the behaviour this component exists to avoid.
    const created = within(screen.getByTestId('confirm-created'))
    expect(created.getByText('Neu angelegt:')).toBeInTheDocument()
    expect(created.getByText('…/de/x/fresh.jinja')).toBeInTheDocument()

    const updated = within(screen.getByTestId('confirm-updated'))
    expect(updated.getByText('Geändert:')).toBeInTheDocument()
    expect(updated.getByText('…/de/x/prompt.yaml')).toBeInTheDocument()

    const deleted = within(screen.getByTestId('confirm-deleted'))
    expect(
      deleted.getByText('Gelöscht (wird von keinem Prompt mehr verwendet):'),
    ).toBeInTheDocument()
    expect(deleted.getByText('…/de/x/old.jinja')).toBeInTheDocument()
  })

  it('explains why nothing will be deleted', () => {
    render(
      <SavePromptDialog
        plan={{
          ...PLAN,
          deleted: [],
          deletions_skipped: 'de/broken/prompt.yaml could not be parsed',
        }}
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
      <SavePromptDialog
        plan={null}
        error="nope"
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeDisabled()
  })

  it('cannot be confirmed while the plan request is still in flight', () => {
    render(
      <SavePromptDialog
        plan={null}
        error={null}
        pending={true}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
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
      <SavePromptDialog
        plan={PLAN}
        error={null}
        pending={true}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Wird gespeichert…' })).toBeDisabled()
  })

  it('names files changed on disk and asks to overwrite them', () => {
    render(
      <SavePromptDialog
        plan={{ ...PLAN, changed_on_disk: ['/p/de/x/user.jinja'] }}
        error={null}
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    const warning = within(screen.getByTestId('confirm-changed-on-disk'))
    expect(warning.getByText('…/de/x/user.jinja')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Trotzdem überschreiben' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Bestätigen' })).not.toBeInTheDocument()
  })

  it('shows no overwrite warning when nothing changed on disk', () => {
    render(
      <SavePromptDialog
        plan={{ ...PLAN, changed_on_disk: [] }}
        error={null}
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('confirm-changed-on-disk')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Trotzdem überschreiben' })).not.toBeInTheDocument()
  })

  it('shows the file name of a long server path and keeps the full path as the tooltip', () => {
    const long =
      'C:\\Users\\someone\\AppData\\Local\\Temp\\prompts\\de\\defect_explainer\\detail_user.jinja'
    render(
      <SavePromptDialog
        plan={{ ...PLAN, updated: [long] }}
        error={null}
        pending={false}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )
    const entry = screen.getByText('…/de/defect_explainer/detail_user.jinja')
    expect(entry).toHaveAttribute('title', long)
  })
})
