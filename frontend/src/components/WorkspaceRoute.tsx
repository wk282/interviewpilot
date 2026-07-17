import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import type { WorkspaceType } from '../types/workspace'
import { getActiveWorkspace, getWorkspaceHome } from '../utils/workspaceStorage'

function WorkspaceRoute({ type, children }: { type: WorkspaceType; children: ReactNode }) {
  const workspace = getActiveWorkspace()
  if (!workspace) return <Navigate to="/home" replace />
  if (workspace.type !== type) return <Navigate to={getWorkspaceHome(workspace)} replace />
  return children
}

export default WorkspaceRoute
