import type { DocumentItem } from '../types/document'
import { apiClient } from './client'

function documentsPath(workspaceId: string, knowledgeBaseId: string) {
  return `/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/documents`
}

export async function getDocuments(workspaceId: string, knowledgeBaseId: string) {
  const response = await apiClient.get<DocumentItem[]>(documentsPath(workspaceId, knowledgeBaseId))
  return response.data
}

export async function uploadDocument(workspaceId: string, knowledgeBaseId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post<DocumentItem>(documentsPath(workspaceId, knowledgeBaseId), formData)
  return response.data
}

export async function deleteDocument(workspaceId: string, knowledgeBaseId: string, documentId: string) {
  await apiClient.delete(`${documentsPath(workspaceId, knowledgeBaseId)}/${documentId}`)
}

export async function resumeDocumentProcessing(workspaceId: string, knowledgeBaseId: string, documentId: string) {
  const response = await apiClient.post<DocumentItem>(
    `${documentsPath(workspaceId, knowledgeBaseId)}/${documentId}/process`,
  )
  return response.data
}

export async function retryDocumentProcessing(
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string,
  mode: 'AUTO' | 'REEMBED',
) {
  const response = await apiClient.post<DocumentItem>(
    `${documentsPath(workspaceId, knowledgeBaseId)}/${documentId}/retry`,
    { mode },
  )
  return response.data
}
