import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_PANE_HEIGHT, LAYOUT_STORAGE_KEY, PANE_HEIGHT_STORAGE_KEY, useEditorLayout, usePaneHeight } from './editorLayout'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('useEditorLayout', () => {
  it('defaults to split', () => {
    expect(renderHook(() => useEditorLayout()).result.current[0]).toBe('split')
  })

  it('remembers the choice across mounts', () => {
    const first = renderHook(() => useEditorLayout())
    act(() => first.result.current[1]('tabs'))
    expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).toBe('tabs')
    expect(renderHook(() => useEditorLayout()).result.current[0]).toBe('tabs')
  })

  it('ignores an unknown stored value', () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, 'grid')
    expect(renderHook(() => useEditorLayout()).result.current[0]).toBe('split')
  })

  it('still works when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    const hook = renderHook(() => useEditorLayout())
    expect(hook.result.current[0]).toBe('split')
    act(() => hook.result.current[1]('tabs'))
    expect(hook.result.current[0]).toBe('tabs')
  })
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
