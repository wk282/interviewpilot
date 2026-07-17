import type { WorkspaceSummary } from '../types/workspace'

const ACTIVE_WORKSPACE_KEY = 'interviewpilot_active_workspace'

export function saveActiveWorkspace(workspace: WorkspaceSummary) {
  sessionStorage.setItem(ACTIVE_WORKSPACE_KEY, JSON.stringify(workspace))
}

export function getActiveWorkspace(): WorkspaceSummary | null {
  const value = sessionStorage.getItem(ACTIVE_WORKSPACE_KEY)
  if (!value) return null

  try {
    return JSON.parse(value) as WorkspaceSummary
  } catch {
    clearActiveWorkspace()
    return null
  }
}

export function clearActiveWorkspace() {
  sessionStorage.removeItem(ACTIVE_WORKSPACE_KEY)
}

export function getWorkspaceHome(workspace: WorkspaceSummary) {
  return workspace.type === 'PERSONAL' ? '/candidate/dashboard' : '/enterprise/dashboard'
}
