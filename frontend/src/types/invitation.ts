import type { WorkspaceRole } from './workspace'

export type InvitableRole = Exclude<WorkspaceRole, 'OWNER'>

export interface WorkspaceMember {
  user_id: string
  email: string
  display_name: string | null
  role: WorkspaceRole
  joined_at: string
}

export interface InvitationCreateRequest {
  email: string
  role: InvitableRole
}

export interface InvitationCreateResponse {
  id: string
  email: string
  role: InvitableRole
  expires_at: string
  invitation_token: string
}

export interface InvitationInfo {
  workspace_name: string
  email: string
  role: InvitableRole
  expires_at: string
}

export interface InvitationAcceptRequest {
  display_name: string
  password: string
}
