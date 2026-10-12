import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_PANE_HEIGHT, PANE_HEIGHT_STORAGE_KEY, usePaneHeight } from './editorLayout'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('usePaneHeight', () => {
  it('defaults and remembers the height across mounts', () => {
    const first = renderHook(() => usePaneHeight())
    expect(first.result.current[0]).toBe(DEFAULT_PANE_HEIGHT)
    act(() => first.result.current[1](412.4))
    expect(localStorage.getItem(PANE_HEIGHT_STORAGE_KEY)).toBe('412')
    expect(renderHook(() => usePaneHeight()).result.current[0]).toBe(412)
  })

  it('ignores a garbage or too-small stored value', () => {
    localStorage.setItem(PANE_HEIGHT_STORAGE_KEY, 'tall')
    expect(renderHook(() => usePaneHeight()).result.current[0]).toBe(DEFAULT_PANE_HEIGHT)
    localStorage.setItem(PANE_HEIGHT_STORAGE_KEY, '10')
    expect(renderHook(() => usePaneHeight()).result.current[0]).toBe(DEFAULT_PANE_HEIGHT)
  })
})
