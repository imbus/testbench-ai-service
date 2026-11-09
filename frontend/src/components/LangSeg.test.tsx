/**
 * The DE/EN switch. A click is the viewer's pick, so it is remembered for the
 * next load; see `pickLang` in ../i18n.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it } from 'vitest'
import { LangSeg } from './LangSeg'
import { i18n, storedLang } from '../i18n'

beforeEach(async () => {
  await i18n.changeLanguage('de')
  localStorage.clear()
})

it('remembers the language the viewer clicks', async () => {
  render(<LangSeg />)

  await userEvent.click(screen.getByRole('button', { name: 'EN' }))

  expect(i18n.resolvedLanguage).toBe('en')
  expect(storedLang()).toBe('en')
})
