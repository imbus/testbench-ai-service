import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { splitPath } from '../api/paths'
import { valueAt } from '../screens/fields'

export const DRAFT_STORAGE_KEY = 'tbai_admin_draft'
/** Who queued the stored draft, so another operator never inherits it. */
export const DRAFT_OWNER_STORAGE_KEY = 'tbai_admin_draft_owner'
/** On which screen each queued edit was made: dotted path to screen key. */
export const DRAFT_ORIGIN_STORAGE_KEY = 'tbai_admin_draft_origins'

/** The console screens that queue config edits, by the route they live under. */
const ORIGIN_SCREENS = ['service', 'llm', 'logging', 'agents', 'projects'] as const
export type DraftOrigin = (typeof ORIGIN_SCREENS)[number]

/**
 * The screen the operator is on right now, if it is one that queues edits.
 *
 * Read off the address rather than passed in by every caller: one setting can
 * be edited on more than one screen (a project's agent switch sits on Projects
 * and on Agents), so the path alone cannot say where a change was made.
 */
function currentScreen(): DraftOrigin | undefined {
  const match = /\/admin\/([a-z-]+)/.exec(window.location.pathname)
  return ORIGIN_SCREENS.find((screen) => screen === match?.[1])
}

function readOrigins(): Record<string, DraftOrigin> {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(DRAFT_ORIGIN_STORAGE_KEY) ?? '{}')
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Record<string, DraftOrigin>
  } catch {
    return {}
  }
}

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
  /** Queue a removal of a whole table, dropping edits queued inside it. */
  unsetSubtree: (path: string) => void
  revert: (path: string) => void
  discardAll: () => void
  /** The screen a queued edit was made on, when that is known. */
  originOf?: (path: string) => DraftOrigin | undefined
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

  // Where each edit was made. Kept beside the edits rather than inside them:
  // the edits object is what is sent to the server, verbatim.
  const [origins, setOrigins] = useState<Record<string, DraftOrigin>>(readOrigins)
  const noteOrigin = useCallback((path: string) => {
    const screen = currentScreen()
    if (screen) setOrigins((current) => ({ ...current, [path]: screen }))
  }, [])
  useEffect(() => {
    if (saved === undefined) return
    try {
      const kept = Object.fromEntries(Object.entries(origins).filter(([path]) => path in effective))
      if (Object.keys(kept).length === 0) window.localStorage.removeItem(DRAFT_ORIGIN_STORAGE_KEY)
      else window.localStorage.setItem(DRAFT_ORIGIN_STORAGE_KEY, JSON.stringify(kept))
    } catch {
      // Losing the origins only costs the strip its exact chip.
    }
  }, [origins, effective, saved])

  const setValue = useCallback(
    (path: string, value: unknown) => {
      noteOrigin(path)
      setEdits((current) => ({ ...current, [path]: value }))
    },
    [noteOrigin],
  )

  const unsetValue = useCallback(
    (path: string) => {
      noteOrigin(path)
      setEdits((current) => ({ ...current, [path]: null }))
    },
    [noteOrigin],
  )

  const unsetSubtree = useCallback(
    (path: string) => {
      noteOrigin(path)
      // Removing a table and editing something inside it are the same overlay
      // saying two things about one address, and the server refuses the pair
      // (`_check_path_prefix_collisions`) -- so "Remove all overrides" followed
      // by any earlier edit under that project would 400 on preview with no way
      // back except discarding the whole draft. The removal supersedes them, so
      // they go with it, in one update rather than a revert-then-unset race.
      setEdits((current) => {
        let target: string[]
        try {
          target = splitPath(path)
        } catch {
          return { ...current, [path]: null }
        }
        const next: Edits = {}
        for (const [key, value] of Object.entries(current)) {
          let segments: string[]
          try {
            segments = splitPath(key)
          } catch {
            // A path this build cannot tokenize is not one we can prove is
            // inside the subtree; leave it exactly as it is.
            next[key] = value
            continue
          }
          const inside =
            segments.length > target.length && target.every((part, i) => segments[i] === part)
          if (!inside) next[key] = value
        }
        next[path] = null
        return next
      })
    },
    [noteOrigin],
  )

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
      unsetSubtree,
      revert,
      discardAll,
      originOf: (path) => (path in effective ? origins[path] : undefined),
    }),
    [effective, origins, setValue, unsetValue, unsetSubtree, revert, discardAll],
  )

  return <DraftContext.Provider value={api}>{children}</DraftContext.Provider>
}

/** How many edits are queued; 0 where there is no draft at all (outside a provider). */
export function useDraftChangeCount(): number {
  return useContext(DraftContext)?.changeCount ?? 0
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
    window.localStorage.removeItem(DRAFT_ORIGIN_STORAGE_KEY)
    window.localStorage.removeItem(DRAFT_STORAGE_KEY)
  } catch {
    // Errors accessing storage should not break logout.
  }
}

/**
 * Make *username* the owner of the stored draft, dropping it first when it was
 * queued by someone else.
 *
 * Called by session.tsx on every sign-in. signOut already clears the draft,
 * but an expired session never signs out, so without this the next operator
 * on the same browser would see -- and, as an admin, could apply -- the
 * previous one's unapplied edits. The same operator signing in again after an
 * expiry keeps theirs.
 */
export function claimStoredDraft(username: string): void {
  try {
    if (window.localStorage.getItem(DRAFT_OWNER_STORAGE_KEY) !== username) {
      window.localStorage.removeItem(DRAFT_STORAGE_KEY)
    }
    window.localStorage.setItem(DRAFT_OWNER_STORAGE_KEY, username)
  } catch {
    // Errors accessing storage should not break sign-in.
  }
}
