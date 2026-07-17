import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import type { WorkspaceRole } from '../types/workspace'
import { getActiveWorkspace } from '../utils/workspaceStorage'

function RoleRoute({ roles, children }: { roles: WorkspaceRole[]; children: ReactNode }) {
  const workspace = getActiveWorkspace()
  if (!workspace || !roles.includes(workspace.role)) {
    return <Navigate to="/enterprise/dashboard" replace />
  }
  return children
}

export default RoleRoute
