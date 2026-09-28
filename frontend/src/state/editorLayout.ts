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

export const PANE_HEIGHT_STORAGE_KEY = 'tbai-console-prompt-pane-height'
export const DEFAULT_PANE_HEIGHT = 230
export const MIN_PANE_HEIGHT = 120

function storedPaneHeight(): number {
  try {
    const stored = Number(localStorage.getItem(PANE_HEIGHT_STORAGE_KEY))
    return Number.isFinite(stored) && stored >= MIN_PANE_HEIGHT ? stored : DEFAULT_PANE_HEIGHT
  } catch {
    return DEFAULT_PANE_HEIGHT
  }
}

/** The Split layout's Preview/Test run pane height -- dragged by the viewer, remembered like the layout. */
export function usePaneHeight(): [number, (next: number) => void] {
  const [height, setHeight] = useState<number>(storedPaneHeight)
  const update = useCallback((next: number) => {
    setHeight(next)
    try {
      localStorage.setItem(PANE_HEIGHT_STORAGE_KEY, String(Math.round(next)))
    } catch {
      // Private window or blocked storage: the height just lasts this visit.
    }
  }, [])
  return [height, update]
}
