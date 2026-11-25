/**
 * Whether the prompt editor holds unsaved edits, for the one place outside it
 * that has to ask before throwing them away: signing out.
 *
 * In-app navigation is guarded by the editor's own router blocker and a tab
 * close by its `beforeunload` handler. Signing out is neither -- it replaces
 * the whole console with the login screen -- so the editor publishes its dirty
 * flag here and the top bar reads it at the moment of the click. A module-level
 * flag rather than context: one editor exists at a time, and nothing needs to
 * re-render when it changes.
 */
let unsavedPrompt = false

export function setUnsavedPrompt(value: boolean): void {
  unsavedPrompt = value
}

export function hasUnsavedPrompt(): boolean {
  return unsavedPrompt
}
