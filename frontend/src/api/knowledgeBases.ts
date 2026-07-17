import type { KnowledgeBase, KnowledgeBaseCreateRequest, KnowledgeBaseRenameRequest } from '../types/knowledgeBase'
import { apiClient } from './client'

export async function getKnowledgeBases(workspaceId: string) {
  const response = await apiClient.get<KnowledgeBase[]>(`/workspaces/${workspaceId}/knowledge-bases`)
  return response.data
}

export async function createKnowledgeBase(workspaceId: string, request: KnowledgeBaseCreateRequest) {
  const response = await apiClient.post<KnowledgeBase>(`/workspaces/${workspaceId}/knowledge-bases`, request)
  return response.data
}

export async function renameKnowledgeBase(
  workspaceId: string,
  knowledgeBaseId: string,
  request: KnowledgeBaseRenameRequest,
) {
  const response = await apiClient.patch<KnowledgeBase>(
    `/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}`,
    request,
  )
  return response.data
}

export async function deleteKnowledgeBase(workspaceId: string, knowledgeBaseId: string) {
  await apiClient.delete(`/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}`)
}
