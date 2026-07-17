export type WorkspaceType = 'PERSONAL' | 'ORGANIZATION'
export type WorkspaceRole = 'OWNER' | 'ADMIN' | 'HR' | 'INTERVIEWER' | 'VIEWER'

export interface WorkspaceSummary {
  id: string
  name: string
  type: WorkspaceType
  role: WorkspaceRole
}
