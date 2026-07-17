import type { AuthResponse } from '../types/auth'
import type {
  InvitationAcceptRequest,
  InvitationCreateRequest,
  InvitationCreateResponse,
  InvitationInfo,
  WorkspaceMember,
} from '../types/invitation'
import { apiClient } from './client'

export async function getWorkspaceMembers(workspaceId: string) {
  const response = await apiClient.get<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`)
  return response.data
}

export async function createWorkspaceInvitation(workspaceId: string, request: InvitationCreateRequest) {
  const response = await apiClient.post<InvitationCreateResponse>(`/workspaces/${workspaceId}/invitations`, request)
  return response.data
}

export async function getInvitation(token: string) {
  const response = await apiClient.get<InvitationInfo>(`/invitations/${token}`)
  return response.data
}

export async function acceptInvitation(token: string, request: InvitationAcceptRequest) {
  const response = await apiClient.post<AuthResponse>(`/invitations/${token}/accept`, request)
  return response.data
}
