import type { SessionInfo } from '../api/types'
import { canEditProject, canRefreshProjects, isEditor } from './access'

const session = (is_admin: boolean, managed_projects: string[]): SessionInfo => ({
  username: 'u',
  roles: [],
  is_admin,
  tb_server_url: 'https://tb.example.com/api/',
  managed_projects,
})

test('admin edits every project', () => {
  expect(canEditProject(session(true, []), 'X')).toBe(true)
})

test('project admin edits only managed projects', () => {
  const projectAdmin = session(false, ['Alpha'])
  expect(canEditProject(projectAdmin, 'Alpha')).toBe(true)
  expect(canEditProject(projectAdmin, 'Beta')).toBe(false)
})

test('isEditor is true for admin or any managed project', () => {
  expect(isEditor(session(true, []))).toBe(true)
  expect(isEditor(session(false, ['Alpha']))).toBe(true)
  expect(isEditor(session(false, []))).toBe(false)
})

test('refresh is offered for either spelling of the project admin role', () => {
  expect(canRefreshProjects(false, ['ProjectAdministrator'])).toBe(true)
  expect(canRefreshProjects(false, ['Project User', 'Project Administrator'])).toBe(true)
  expect(canRefreshProjects(false, ['Project User'])).toBe(false)
})
