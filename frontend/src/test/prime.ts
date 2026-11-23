/**
 * Test helpers for PrimeReact widgets that user-event cannot drive the way
 * it drives native form controls.
 *
 * jsdom cannot measure layout, so Prime's overlay positioning leaves popup
 * panels `display: none`: every query into an overlay passes `hidden: true`.
 */
import { screen, within } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'

type User = ReturnType<typeof userEvent.setup>
type Matcher = string | RegExp

function dropdownRoot(field: Matcher | HTMLElement): HTMLElement {
  const anchor = field instanceof HTMLElement ? field : screen.getByLabelText(field)
  return (anchor.closest('.p-dropdown') as HTMLElement | null) ?? anchor
}

/**
 * Open a `Dropdown` and return its option list. `field` is the dropdown's
 * label (wired through `inputId`) or an element inside it. The labelled
 * input is visually hidden with `pointer-events: none`, so the click goes
 * to the dropdown around it.
 */
export async function openDropdown(user: User, field: Matcher | HTMLElement): Promise<HTMLElement> {
  await user.click(dropdownRoot(field))
  return screen.findByRole('listbox', { hidden: true })
}

/**
 * Pick `option` from a `Dropdown`. Scoped to the overlay: Prime also
 * renders a hidden native `<select>` holding the current choice as an
 * option of its own.
 */
export async function chooseOption(
  user: User,
  field: Matcher | HTMLElement,
  option: Matcher,
): Promise<void> {
  const list = await openDropdown(user, field)
  await user.click(within(list).getByRole('option', { name: option, hidden: true }))
}

/** The text a `Dropdown` currently shows, found by its label. */
export function dropdownValue(field: Matcher | HTMLElement): string {
  return dropdownRoot(field).querySelector('.p-dropdown-label')?.textContent ?? ''
}
