import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { valueAt } from '../screens/fields'

export const DRAFT_STORAGE_KEY = 'tbai_admin_draft'

/**
 * The operator's uncommitted edits: dotted config path to new value.
 *
 * A `null` value means "remove this key", which is a change like any other —
 * the server reads it as "fall back to the model default". Absence of a key
 * means "no opinion", which is not a change at all. The distinction is the
 * whole reason `unsetValue` and `revert` are separate operations.
 */
export type Edits = Record<string, unknown>

export interface DraftApi {
  edits: Edits
  changeCount: number
  isChanged: (path: string) => boolean
  valueOf: (path: string, fallback: unknown) => unknown
  setValue: (path: string, value: unknown) => void
  unsetValue: (path: string) => void
  revert: (path: string) => void
  discardAll: () => void
}

const DraftContext = createContext<DraftApi | null>(null)

function readStored(): Edits {
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    // An array is an object too, and a stored array would make every consumer
    // that iterates keys behave strangely rather than visibly break.
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Edits
  } catch {
    // A corrupt or unavailable localStorage must never take the console down:
    // an operator who cannot load the console cannot fix the config either.
    return {}
  }
}

function sameValue(left: unknown, right: unknown): boolean {
  // Structural, not referential: a re-fetched config hands back new array and
  // object identities for values that have not changed at all.
  return JSON.stringify(left) === JSON.stringify(right)
}

/**
 * Drop edits whose value already matches what is saved.
 *
 * Runs on every change and whenever `saved` arrives, which is what keeps a
 * concurrent save by another operator from leaving a phantom "1 unapplied
 * change" the diff would show as empty.
 *
 * While `saved` is undefined (config not yet loaded), do not prune: an
 * undefined saved state means "we have not read the file yet", whereas an
 * empty object means "the file has no such key". Pruning against undefined
 * throws away the operator's queued removals (null values).
 */
function prune(edits: Edits, saved: Record<string, unknown> | undefined): Edits {
  if (saved === undefined) return edits
  const pruned: Edits = {}
  for (const [path, value] of Object.entries(edits)) {
    const savedValue = valueAt(saved, path)
    if (value === null) {
      // "Remove the key" is only a change if the key is actually there.
      if (savedValue !== undefined) pruned[path] = null
      continue
    }
    if (!sameValue(value, savedValue)) pruned[path] = value
  }
  return pruned
}

export function DraftProvider({
  saved,
  children,
}: {
  /** The configuration as saved on disk — what edits are measured against.
   *
   * If undefined, the config has not been loaded yet. In this state, edits are
   * not pruned and storage is not modified, preserving queued removals through
   * the loading phase.
   */
  saved: Record<string, unknown> | undefined
  children: ReactNode
}) {
  const [edits, setEdits] = useState<Edits>(readStored)

  // `saved` arrives asynchronously and changes after every apply, so the
  // pruning has to be re-run rather than done once at mount.
  const effective = useMemo(() => prune(edits, saved), [edits, saved])

  useEffect(() => {
    // Only persist if we have a loaded config to measure against. While `saved`
    // is undefined, storage is left alone to avoid destroying queued removals.
    if (saved === undefined) return

    try {
      if (Object.keys(effective).length === 0) {
        window.localStorage.removeItem(DRAFT_STORAGE_KEY)
      } else {
        window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(effective))
      }
    } catch {
      // Private-browsing quota errors are not worth a broken console.
    }
  }, [effective, saved])

  const setValue = useCallback((path: string, value: unknown) => {
    setEdits((current) => ({ ...current, [path]: value }))
  }, [])

  const unsetValue = useCallback((path: string) => {
    setEdits((current) => ({ ...current, [path]: null }))
  }, [])

  const revert = useCallback((path: string) => {
    setEdits((current) => {
      const next = { ...current }
      delete next[path]
      return next
    })
  }, [])

  const discardAll = useCallback(() => setEdits({}), [])

  const api = useMemo<DraftApi>(
    () => ({
      edits: effective,
      changeCount: Object.keys(effective).length,
      isChanged: (path) => path in effective,
      valueOf: (path, fallback) => (path in effective ? effective[path] : fallback),
      setValue,
      unsetValue,
      revert,
      discardAll,
    }),
    [effective, setValue, unsetValue, revert, discardAll],
  )

  return <DraftContext.Provider value={api}>{children}</DraftContext.Provider>
}

export function useDraft(): DraftApi {
  const api = useContext(DraftContext)
  if (api === null) throw new Error('useDraft must be used inside a DraftProvider')
  return api
}

/**
 * Clear the stored draft from localStorage. Wrapped in try/catch like all
 * storage access so errors cannot crash the console.
 *
 * Called by session.tsx's signOut to prevent the draft from persisting across
 * logout, which would expose one operator's queued edits to another on a
 * shared machine.
 */
export function clearStoredDraft(): void {
  try {
    window.localStorage.removeItem(DRAFT_STORAGE_KEY)
  } catch {
    // Errors accessing storage should not break logout.
  }
}
