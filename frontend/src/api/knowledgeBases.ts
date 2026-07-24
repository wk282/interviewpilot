import type { KnowledgeBase, KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest } from '../types/knowledgeBase'
import { apiClient } from './client'

export async function getKnowledgeBases(workspaceId: string) {
  const response = await apiClient.get<KnowledgeBase[]>(`/workspaces/${workspaceId}/knowledge-bases`)
  return response.data
}

export async function createKnowledgeBase(workspaceId: string, request: KnowledgeBaseCreateRequest) {
  const response = await apiClient.post<KnowledgeBase>(`/workspaces/${workspaceId}/knowledge-bases`, request)
  return response.data
}

export async function updateKnowledgeBase(
  workspaceId: string,
  knowledgeBaseId: string,
  request: KnowledgeBaseUpdateRequest,
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
