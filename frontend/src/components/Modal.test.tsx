import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { Modal } from './Modal'

it('closes on Escape through the handler its caller gave it', async () => {
  const onClose = vi.fn()
  render(
    <Modal label="Confirm" onClose={onClose}>
      <button type="button">inside</button>
    </Modal>,
  )
  expect(screen.getByRole('dialog', { name: 'Confirm' })).toBeInTheDocument()

  await userEvent.keyboard('{Escape}')

  expect(onClose).toHaveBeenCalledTimes(1)
})

it('ignores Escape when nobody could be told that it closed', async () => {
  render(
    <Modal label="Working">
      <button type="button">inside</button>
    </Modal>,
  )

  await userEvent.keyboard('{Escape}')

  expect(screen.getByRole('dialog', { name: 'Working' })).toBeInTheDocument()
})
