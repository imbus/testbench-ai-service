import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LAYOUT_STORAGE_KEY, useEditorLayout } from './editorLayout'

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
