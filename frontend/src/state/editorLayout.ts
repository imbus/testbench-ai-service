import { useCallback, useState } from 'react'

export type EditorLayout = 'split' | 'tabs'

export const LAYOUT_STORAGE_KEY = 'tbai-console-prompt-layout'

function storedLayout(): EditorLayout {
  try {
    return localStorage.getItem(LAYOUT_STORAGE_KEY) === 'tabs' ? 'tabs' : 'split'
  } catch {
    return 'split'
  }
}

/** The prompt editor's Split/Tabs choice -- a per-viewer convenience, so browser storage is enough. */
export function useEditorLayout(): [EditorLayout, (next: EditorLayout) => void] {
  const [layout, setLayout] = useState<EditorLayout>(storedLayout)
  const update = useCallback((next: EditorLayout) => {
    setLayout(next)
    try {
      localStorage.setItem(LAYOUT_STORAGE_KEY, next)
    } catch {
      // Private window or blocked storage: the choice just lasts this visit.
    }
  }, [])
  return [layout, update]
}
