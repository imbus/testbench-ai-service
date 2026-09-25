/**
 * `MetaPane`: the centre pane showing prompt.yaml's own header fields (design
 * §5.6's workbench, Task 6). Its markup and behaviour are copied verbatim
 * from `PromptEditor.tsx`'s `Header` helper and default-variant `<select>`
 * block -- this test suite pins that behaviour in its new home.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PromptDocument } from '../../api/types'
import { MetaPane } from './MetaPane'

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

describe('MetaPane', () => {
  it('edits every header field', async () => {
    const onHeader = vi.fn()
    render(<MetaPane draft={DOC} readOnly={false} defaultVariantIssue={null} lang="en" onHeader={onHeader} />)
    await userEvent.type(screen.getByLabelText('Summary'), '!')
    expect(onHeader).toHaveBeenLastCalledWith('summary', 'Explains defects!')
    await userEvent.selectOptions(screen.getByLabelText('Default variant'), 'Quick')
    expect(onHeader).toHaveBeenLastCalledWith('default_variant', 'Quick')
  })

  it('marks default_variant with the server issue', () => {
    render(
      <MetaPane
        draft={DOC}
        readOnly={false}
        defaultVariantIssue="default_variant 'X' is not a variant"
        lang="en"
        onHeader={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('Default variant')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent("default_variant 'X'")
  })

  it('is read-only for a non-admin', () => {
    render(<MetaPane draft={DOC} readOnly defaultVariantIssue={null} lang="en" onHeader={vi.fn()} />)
    expect(screen.getByLabelText('Name')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Default variant')).toBeDisabled()
  })
})
