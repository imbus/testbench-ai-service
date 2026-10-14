import { useCallback, useState } from 'react'
import type { PromptMessageDoc } from '../api/types'

/**
 * The prompt editor's open tabs, VS Code style.
 *
 * Kept per variant: the editor always works on one variant, and switching
 * back to a variant restores the tabs it had. Message tabs are named by the
 * message's client-only `uid` (see `withMessageUids`), never its index, so a
 * reorder or delete never points a tab at a different message. `render` is
 * the variant's render preview -- one per variant, like its settings.
 */
export type TabId = 'meta' | 'variant' | 'render' | `msg:${string}`

export type VariantTabs = {
  /** In opening order -- a reorder of the messages does not reorder tabs. */
  open: TabId[]
  active: TabId | null
  /** The one italic tab the next single click in the tree replaces. */
  preview: TabId | null
}

export type TabsVariant = { name: string; messages: PromptMessageDoc[] }

export function messageTabOf(message: PromptMessageDoc, index: number): `msg:${string}` {
  return `msg:${message.uid ?? `#${index}`}`
}

export function initialTabs(first: TabId): VariantTabs {
  return { open: [first], active: first, preview: first }
}

export function openTab(tabs: VariantTabs, tab: TabId, pin: boolean): VariantTabs {
  if (tabs.open.includes(tab)) {
    return { ...tabs, active: tab, preview: pin && tabs.preview === tab ? null : tabs.preview }
  }
  if (pin) return { ...tabs, open: [...tabs.open, tab], active: tab }
  const open = tabs.preview ? tabs.open.map((id) => (id === tabs.preview ? tab : id)) : [...tabs.open, tab]
  return { open, active: tab, preview: tab }
}

export function pinTab(tabs: VariantTabs, tab: TabId): VariantTabs {
  return tabs.preview === tab ? { ...tabs, preview: null } : tabs
}

/** The tab that takes over from the one at `index`: right neighbour, else left. */
function neighbour(open: TabId[], index: number): TabId | null {
  return open[index] ?? open[index - 1] ?? null
}

export function closeTab(tabs: VariantTabs, tab: TabId): VariantTabs {
  const index = tabs.open.indexOf(tab)
  if (index < 0) return tabs
  const open = tabs.open.filter((id) => id !== tab)
  return {
    open,
    active: tabs.active === tab ? neighbour(open, index) : tabs.active,
    preview: tabs.preview === tab ? null : tabs.preview,
  }
}

/**
 * Only the tabs that still resolve. A deleted message's tab simply stops
 * resolving -- that is how deleting a message closes its tab -- and an active
 * tab that vanished hands over to its neighbour like a closed one.
 */
export function visibleTabs(tabs: VariantTabs, valid: TabId[]): VariantTabs {
  if (tabs.open.every((id) => valid.includes(id))) return tabs
  const open = tabs.open.filter((id) => valid.includes(id))
  let active = tabs.active
  if (active && !valid.includes(active)) {
    const index = tabs.open.slice(0, tabs.open.indexOf(active)).filter((id) => valid.includes(id)).length
    active = neighbour(open, index)
  }
  return { open, active, preview: tabs.preview && valid.includes(tabs.preview) ? tabs.preview : null }
}

function validTabs(variant: TabsVariant): TabId[] {
  return ['meta', 'variant', 'render', ...variant.messages.map(messageTabOf)]
}

function resolve(state: Record<string, VariantTabs>, variant: TabsVariant | undefined): VariantTabs {
  if (!variant) return initialTabs('meta')
  const first: TabId = variant.messages[0] ? messageTabOf(variant.messages[0], 0) : 'variant'
  return visibleTabs(state[variant.name] ?? initialTabs(first), validTabs(variant))
}

export function useEditorTabs() {
  const [state, setState] = useState<Record<string, VariantTabs>>({})

  const tabsFor = useCallback((variant: TabsVariant | undefined) => resolve(state, variant), [state])

  /** `variant` may already list a message the draft adds in the same event (add message). */
  const update = useCallback((variant: TabsVariant, change: (tabs: VariantTabs) => VariantTabs) => {
    setState((current) => ({ ...current, [variant.name]: change(resolve(current, variant)) }))
  }, [])

  const renameVariant = useCallback((from: string, to: string) => {
    setState((current) => {
      if (!(from in current) || from === to) return current
      const { [from]: moved, ...rest } = current
      return { ...rest, [to]: moved }
    })
  }, [])

  const removeVariant = useCallback((name: string) => {
    setState((current) => {
      if (!(name in current)) return current
      const { [name]: _removed, ...rest } = current
      return rest
    })
  }, [])

  const reset = useCallback(() => setState({}), [])

  return { tabsFor, update, renameVariant, removeVariant, reset }
}
