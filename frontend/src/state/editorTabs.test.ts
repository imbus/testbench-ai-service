import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PromptMessageDoc } from '../api/types'
import {
  closeTab, initialTabs, messageTabOf, openTab, pinTab, useEditorTabs, visibleTabs,
  type TabId, type VariantTabs,
} from './editorTabs'

const msg = (uid: string): PromptMessageDoc => ({ role: 'user', source: 'inline', file: null, content: uid, readable: true, uid })
const tabs = (open: TabId[], active: TabId | null, preview: TabId | null = null): VariantTabs => ({ open, active, preview })

describe('messageTabOf', () => {
  it('uses the uid, falling back to the index', () => {
    expect(messageTabOf(msg('a'), 3)).toBe('msg:a')
    expect(messageTabOf({ ...msg('a'), uid: undefined }, 3)).toBe('msg:#3')
  })
})

describe('openTab', () => {
  it('opens a preview tab in place of the previous preview', () => {
    const next = openTab(tabs(['meta', 'msg:a'], 'msg:a', 'msg:a'), 'msg:b', false)
    expect(next).toEqual(tabs(['meta', 'msg:b'], 'msg:b', 'msg:b'))
  })

  it('appends a preview tab when there is no preview', () => {
    expect(openTab(tabs(['meta'], 'meta'), 'msg:b', false)).toEqual(tabs(['meta', 'msg:b'], 'msg:b', 'msg:b'))
  })

  it('appends a pinned tab and leaves the preview alone', () => {
    expect(openTab(tabs(['msg:a'], 'msg:a', 'msg:a'), 'meta', true)).toEqual(tabs(['msg:a', 'meta'], 'meta', 'msg:a'))
  })

  it('only activates a tab that is already open', () => {
    expect(openTab(tabs(['msg:a', 'meta'], 'meta'), 'msg:a', false)).toEqual(tabs(['msg:a', 'meta'], 'msg:a'))
  })

  it('pins an open preview tab when opened pinned', () => {
    expect(openTab(tabs(['msg:a'], 'msg:a', 'msg:a'), 'msg:a', true)).toEqual(tabs(['msg:a'], 'msg:a', null))
  })
})

describe('pinTab', () => {
  it('pins the preview tab and ignores others', () => {
    expect(pinTab(tabs(['msg:a'], 'msg:a', 'msg:a'), 'msg:a').preview).toBeNull()
    expect(pinTab(tabs(['msg:a', 'meta'], 'meta', 'msg:a'), 'meta').preview).toBe('msg:a')
  })
})

describe('closeTab', () => {
  it('activates the right neighbour of a closed active tab', () => {
    expect(closeTab(tabs(['meta', 'msg:a', 'msg:b'], 'msg:a'), 'msg:a')).toEqual(tabs(['meta', 'msg:b'], 'msg:b'))
  })

  it('falls back to the left neighbour at the end', () => {
    expect(closeTab(tabs(['meta', 'msg:a'], 'msg:a'), 'msg:a')).toEqual(tabs(['meta'], 'meta'))
  })

  it('keeps the active tab when another one closes', () => {
    expect(closeTab(tabs(['meta', 'msg:a'], 'meta'), 'msg:a')).toEqual(tabs(['meta'], 'meta'))
  })

  it('leaves nothing active after the last tab closes', () => {
    expect(closeTab(tabs(['meta'], 'meta', 'meta'), 'meta')).toEqual(tabs([], null, null))
  })
})

describe('visibleTabs', () => {
  it('drops tabs whose message is gone and moves the active tab to a neighbour', () => {
    const valid: TabId[] = ['meta', 'variant', 'msg:a', 'msg:c']
    expect(visibleTabs(tabs(['msg:a', 'msg:b', 'msg:c'], 'msg:b', 'msg:b'), valid)).toEqual(tabs(['msg:a', 'msg:c'], 'msg:c', null))
  })

  it('returns the same object when nothing is stale', () => {
    const t = tabs(['msg:a'], 'msg:a')
    expect(visibleTabs(t, ['msg:a'])).toBe(t)
  })
})

describe('initialTabs', () => {
  it('opens one preview tab', () => {
    expect(initialTabs('variant')).toEqual(tabs(['variant'], 'variant', 'variant'))
  })
})

describe('useEditorTabs', () => {
  const A = { name: 'A', messages: [msg('a'), msg('b')] }
  const Empty = { name: 'E', messages: [] }

  it('starts a variant on its first message as a preview tab', () => {
    const { result } = renderHook(() => useEditorTabs())
    expect(result.current.tabsFor(A)).toEqual(tabs(['msg:a'], 'msg:a', 'msg:a'))
  })

  it('starts a variant without messages on its settings', () => {
    const { result } = renderHook(() => useEditorTabs())
    expect(result.current.tabsFor(Empty)).toEqual(tabs(['variant'], 'variant', 'variant'))
  })

  it('shows prompt.yaml when there is no variant at all', () => {
    const { result } = renderHook(() => useEditorTabs())
    expect(result.current.tabsFor(undefined)).toEqual(tabs(['meta'], 'meta', 'meta'))
  })

  it('remembers each variant separately', () => {
    const B = { name: 'B', messages: [msg('x')] }
    const { result } = renderHook(() => useEditorTabs())
    act(() => result.current.update(A, (t) => openTab(t, 'msg:b', true)))
    expect(result.current.tabsFor(A).open).toEqual(['msg:a', 'msg:b'])
    expect(result.current.tabsFor(B).open).toEqual(['msg:x'])
  })

  it('moves the tabs with a rename and drops them with a remove', () => {
    const { result } = renderHook(() => useEditorTabs())
    act(() => result.current.update(A, (t) => openTab(t, 'meta', true)))
    act(() => result.current.renameVariant('A', 'Z'))
    expect(result.current.tabsFor({ ...A, name: 'Z' }).open).toEqual(['msg:a', 'meta'])
    act(() => result.current.removeVariant('Z'))
    expect(result.current.tabsFor({ ...A, name: 'Z' }).open).toEqual(['msg:a'])
  })

  it('keeps a tab opened for a message the variant does not list yet (add message)', () => {
    const { result } = renderHook(() => useEditorTabs())
    act(() => result.current.update({ ...A, messages: [...A.messages, msg('new')] }, (t) => openTab(t, 'msg:new', true)))
    expect(result.current.tabsFor({ ...A, messages: [...A.messages, msg('new')] }).active).toBe('msg:new')
  })

  it('forgets the tabs of every variant on reset', () => {
    const { result } = renderHook(() => useEditorTabs())
    act(() => result.current.update(A, (t) => openTab(t, 'msg:b', true)))
    expect(result.current.tabsFor(A).open).toEqual(['msg:a', 'msg:b'])
    act(() => result.current.reset())
    expect(result.current.tabsFor(A).open).toEqual(['msg:a'])
  })
})
