/**
 * `Field`'s inherit mode — the per-project override affordance (design §5.4).
 *
 * A project override in `config.toml` is sparse: a project that says nothing
 * about a setting inherits the global value, and a project that says `false`
 * has an opinion. Those two must never look the same on screen, or the
 * operator can set an override and then never take it back off.
 *
 * Three states, and the overlay already expresses all three (design §3.8):
 * no edit + no saved value = inherit; a value = override; a queued `null` =
 * remove the key, i.e. go back to inheriting.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import type { FieldSpec } from '../screens/fields'
import { Field } from './Field'

const ENABLED: FieldSpec = {
  key: 'projects.Alpha.agents.reviewer.enabled',
  type: 'bool',
  hint: 'Run this agent for this project',
}

const VARIANT: FieldSpec = {
  key: 'projects.Alpha.agents.reviewer.prompt.variant',
  type: 'text',
  hint: 'Prompt variant',
}

function Harness({
  spec,
  saved,
  inherited,
  savedConfig = {},
}: {
  spec: FieldSpec
  saved: unknown
  inherited: { value: unknown; label: string }
  /** What the draft prunes against — the config as saved on disk. */
  savedConfig?: Record<string, unknown>
}) {
  return (
    <DraftProvider saved={savedConfig}>
      <Field spec={spec} saved={saved} inheritedFrom={inherited} lang="en" />
      <Edits />
    </DraftProvider>
  )
}

function Edits() {
  const draft = useDraft()
  return <span data-testid="edits">{JSON.stringify(draft.edits)}</span>
}

beforeEach(() => {
  window.localStorage.clear()
})

// --- the inherit state --------------------------------------------------

describe('with no override', () => {
  it('says it is inheriting, and from where, and what', () => {
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)

    const note = screen.getByTestId('inherit-note')
    expect(note).toHaveTextContent('Inherited')
    expect(note).toHaveTextContent('global')
    expect(note).toHaveTextContent('true')
  })

  it('shows the inherited value in the control, not an empty one', () => {
    // An empty control would read as "off", which is a different setting from
    // "inherits a global true".
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('marks the control as not overridden for assistive tech', () => {
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)
    expect(screen.getByTestId('field-row')).toHaveAttribute('data-overridden', 'false')
  })

  it('offers no "clear override" action — there is nothing to clear', () => {
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)
    expect(screen.queryByRole('button', { name: 'Clear override' })).not.toBeInTheDocument()
  })

  it('leaves a text input empty, offering the inherited value as a placeholder', () => {
    // An empty box is what "no override here" looks like. Pre-filling it with
    // the inherited value would make the field impossible to type over:
    // clearing it queues a removal, which is still "inheriting", which puts
    // the value straight back and the next keystroke appends to it.
    render(
      <Harness spec={VARIANT} saved={undefined} inherited={{ value: 'Thorough', label: 'global' }} />,
    )
    const input = screen.getByLabelText('variant')
    expect(input).toHaveValue('')
    expect(input).toHaveAttribute('placeholder', 'Thorough')
  })

  it('shows an em dash for an inherited value that is not set at all', () => {
    render(<Harness spec={VARIANT} saved={undefined} inherited={{ value: undefined, label: 'global' }} />)
    expect(screen.getByTestId('inherit-note')).toHaveTextContent('—')
  })
})

// --- taking an override -------------------------------------------------

describe('taking an override', () => {
  it('records an explicit value when the switch is clicked', async () => {
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)

    await userEvent.click(screen.getByRole('switch'))

    expect(screen.getByTestId('edits')).toHaveTextContent(
      '{"projects.Alpha.agents.reviewer.enabled":false}',
    )
  })

  it('toggles away from the inherited value, not from false', async () => {
    // Clicking a switch that displays `true` must produce `false`. Reading the
    // draft value alone (undefined while inheriting) would produce `true` --
    // an "override" identical to what was already inherited, which prunes
    // straight back out and leaves the click doing nothing at all.
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)
    await userEvent.click(screen.getByRole('switch'))
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('marks the row overridden once an edit exists', async () => {
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)
    await userEvent.click(screen.getByRole('switch'))
    expect(screen.getByTestId('field-row')).toHaveAttribute('data-overridden', 'true')
  })

  it('records a typed text override', async () => {
    render(
      <Harness spec={VARIANT} saved={undefined} inherited={{ value: 'Thorough', label: 'global' }} />,
    )

    await userEvent.type(screen.getByLabelText('variant'), 'Quick')

    expect(screen.getByTestId('edits')).toHaveTextContent(
      '{"projects.Alpha.agents.reviewer.prompt.variant":"Quick"}',
    )
  })

  it('emptying a typed override goes back to inheriting, not to an empty value', async () => {
    render(
      <Harness spec={VARIANT} saved={undefined} inherited={{ value: 'Thorough', label: 'global' }} />,
    )

    await userEvent.type(screen.getByLabelText('variant'), 'Quick')
    await userEvent.clear(screen.getByLabelText('variant'))

    // The queued removal prunes away entirely -- there was no key on disk to
    // remove -- so this leaves no phantom pending change.
    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
    expect(screen.getByTestId('inherit-note')).toBeInTheDocument()
  })

  it('stops showing the inherit note once overridden', async () => {
    render(<Harness spec={ENABLED} saved={undefined} inherited={{ value: true, label: 'global' }} />)
    await userEvent.click(screen.getByRole('switch'))
    expect(screen.queryByTestId('inherit-note')).not.toBeInTheDocument()
  })
})

// --- an override already on disk ----------------------------------------

describe('with an override saved on disk', () => {
  const savedConfig = {
    projects: { Alpha: { agents: { reviewer: { enabled: false } } } },
  }

  it('shows the saved override, not the inherited value', () => {
    render(
      <Harness
        spec={ENABLED}
        saved={false}
        inherited={{ value: true, label: 'global' }}
        savedConfig={savedConfig}
      />,
    )
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByTestId('field-row')).toHaveAttribute('data-overridden', 'true')
    expect(screen.queryByTestId('inherit-note')).not.toBeInTheDocument()
  })

  it('offers "clear override", which queues a removal', async () => {
    render(
      <Harness
        spec={ENABLED}
        saved={false}
        inherited={{ value: true, label: 'global' }}
        savedConfig={savedConfig}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Clear override' }))

    // `null` is the overlay's "remove this key", which the server reads as
    // "fall back to the inherited value" -- no new overlay semantics needed.
    expect(screen.getByTestId('edits')).toHaveTextContent(
      '{"projects.Alpha.agents.reviewer.enabled":null}',
    )
  })

  it('goes back to showing the inherited value once the removal is queued', async () => {
    render(
      <Harness
        spec={ENABLED}
        saved={false}
        inherited={{ value: true, label: 'global' }}
        savedConfig={savedConfig}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Clear override' }))

    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('field-row')).toHaveAttribute('data-overridden', 'false')
    expect(screen.getByTestId('inherit-note')).toBeInTheDocument()
  })

  it('offers revert while a removal is queued, which restores the override', async () => {
    render(
      <Harness
        spec={ENABLED}
        saved={false}
        inherited={{ value: true, label: 'global' }}
        savedConfig={savedConfig}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Clear override' }))
    await userEvent.click(screen.getByRole('button', { name: 'Revert' }))

    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })
})

// --- global scope is unchanged ------------------------------------------

describe('without inheritedFrom', () => {
  it('renders exactly as before — no note, no clear-override action', () => {
    render(
      <DraftProvider saved={{ port: 8010 }}>
        <Field spec={{ key: 'port', type: 'number', hint: 'Port' }} saved={8010} lang="en" />
      </DraftProvider>,
    )
    expect(screen.queryByTestId('inherit-note')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear override' })).not.toBeInTheDocument()
  })

  it('still marks the row overridden, so global rows are not styled as inherited', () => {
    render(
      <DraftProvider saved={{ port: 8010 }}>
        <Field spec={{ key: 'port', type: 'number', hint: 'Port' }} saved={8010} lang="en" />
      </DraftProvider>,
    )
    expect(screen.getByTestId('field-row')).toHaveAttribute('data-overridden', 'true')
  })
})
