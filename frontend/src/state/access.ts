import type { SessionInfo } from '../api/types'

/**
 * Whether this session may edit the given project's scope.
 *
 * Mirrors the server's rule (admins everything, a project admin only the
 * projects they manage) so the UI offers exactly what the server will accept.
 * It is a convenience, never the enforcement: the routes answer 403 either way.
 */
export function canEditProject(session: SessionInfo, project: string): boolean {
  return canEditScope(session.is_admin, session.managed_projects, project)
}

/**
 * `canEditProject` for screens that receive the two facts as props rather than
 * the whole session. `project` null is the global scope, which only an admin edits.
 */
export function canEditScope(
  isAdmin: boolean,
  managedProjects: readonly string[],
  project: string | null,
): boolean {
  return isAdmin || (project !== null && managedProjects.includes(project))
}

/** Whether this session can edit anything at all (so the read-only notice is wrong). */
export function isEditor(session: SessionInfo): boolean {
  return session.is_admin || session.managed_projects.length > 0
}
