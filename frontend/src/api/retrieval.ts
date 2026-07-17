import type { RetrievalProfile, RetrievalResponse } from '../types/retrieval'
import { apiClient } from './client'

export async function searchKnowledgeBase(
  workspaceId: string,
  knowledgeBaseId: string,
  query: string,
  topK: number,
  profile: RetrievalProfile,
) {
  const response = await apiClient.post<RetrievalResponse>(
    `/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/retrieval/search`,
    { query, top_k: topK, profile },
  )
  return response.data
}

export async function reindexKnowledgeBaseBM25(workspaceId: string, knowledgeBaseId: string) {
  const response = await apiClient.post<{ indexed_count: number }>(
    `/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/retrieval/bm25/reindex`,
  )
  return response.data
}
