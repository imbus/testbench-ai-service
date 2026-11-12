/**
 * Test helpers for the console's own pick lists (`SearchPopover`): the "+"
 * scope tab and the agent model.
 */
import { screen, within } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'

type User = ReturnType<typeof userEvent.setup>

/** Open the pick list behind `trigger` and return its popup. */
export async function openPicker(user: User, trigger: HTMLElement): Promise<HTMLElement> {
  await user.click(trigger)
  return screen.getByRole('dialog', { name: trigger.getAttribute('aria-label') ?? undefined })
}

/** Pick the entry named `entry` from the list behind `trigger`. */
export async function pickFrom(user: User, trigger: HTMLElement, entry: string | RegExp) {
  const popup = await openPicker(user, trigger)
  await user.click(within(popup).getByRole('button', { name: entry }))
}
