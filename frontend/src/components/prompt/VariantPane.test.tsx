/**
 * `VariantPane`: the centre pane showing a variant's own settings (name,
 * model, its `VarDeclTable`) -- design §5.6's workbench, Task 6. Its
 * variant-actions markup is copied verbatim from `PromptEditor.tsx`'s
 * `isAdmin && selectedVariantObj` block.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PromptDocument } from '../../api/types'
import { VariantPane } from './VariantPane'

const DOC: PromptDocument = {
  lang: 'de',
  agent: 'explainer',
  file: 'de/explainer/prompt.yaml',
  name: 'Explainer',
  summary: 'Explains defects',
  description: 'The full description',
  default_model: 'gpt-5.5',
  default_variant: 'Thorough',
  variants: [
    {
      name: 'Thorough',
      description: 'The careful one',
      model: null,
      vars: {
        tone: {
          name: 'tone',
          description: null,
          value_type: 'string',
          choices: null,
          default_value: 'neutral',
          required: false,
        },
      },
      messages: [
        { role: 'system', source: 'file', file: 'sys.jinja', content: 'You are helpful.', readable: true },
        { role: 'user', source: 'inline', file: null, content: 'Explain {{ agent.defect }}', readable: true },
      ],
    },
    {
      name: 'Quick',
      description: null,
      model: null,
      vars: {},
      messages: [{ role: 'user', source: 'inline', file: null, content: 'Quick', readable: true }],
    },
  ],
  agent_context_skeleton: { defect: '' },
}

const V = DOC.variants[0]

describe('VariantPane', () => {
  it('renames, sets the model and removes', async () => {
    const props = {
      onRename: vi.fn(),
      onModel: vi.fn(),
      onRemove: vi.fn(),
      onAddVar: vi.fn(),
      onEditVar: vi.fn(),
      onRemoveVar: vi.fn(),
    }
    render(<VariantPane variant={V} readOnly={false} lang="en" {...props} />)
    await userEvent.type(screen.getByLabelText('Variant name'), 'X')
    expect(props.onRename).toHaveBeenLastCalledWith('ThoroughX')
    await userEvent.type(screen.getByLabelText('Variant model'), 'g')
    expect(props.onModel).toHaveBeenLastCalledWith('g')
    // Scoped: VarDeclTable renders its own per-row "Remove" button, and this
    // variant's one var means there is one on screen at the same time (R1).
    await userEvent.click(within(screen.getByTestId('variant-actions')).getByRole('button', { name: /^remove$/i }))
    expect(props.onRemove).toHaveBeenCalled()
    expect(screen.getAllByTestId('var-row')).toHaveLength(1)
  })

  it('sends a cleared model as null', async () => {
    const onModel = vi.fn()
    render(
      <VariantPane
        variant={{ ...V, model: 'm' }}
        readOnly={false}
        lang="en"
        onRename={vi.fn()}
        onModel={onModel}
        onRemove={vi.fn()}
        onAddVar={vi.fn()}
        onEditVar={vi.fn()}
        onRemoveVar={vi.fn()}
      />,
    )
    await userEvent.clear(screen.getByLabelText('Variant model'))
    expect(onModel).toHaveBeenLastCalledWith(null)
  })

  it('shows only the declarations for a non-admin', () => {
    render(
      <VariantPane
        variant={V}
        readOnly
        lang="en"
        onRename={vi.fn()}
        onModel={vi.fn()}
        onRemove={vi.fn()}
        onAddVar={vi.fn()}
        onEditVar={vi.fn()}
        onRemoveVar={vi.fn()}
      />,
    )
    expect(screen.queryByLabelText('Variant name')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('var-row')).toHaveLength(1)
  })
})
