import type { WorkspaceSummary } from '../types/workspace'
import { apiClient } from './client'

export async function getWorkspaces() {
  const response = await apiClient.get<WorkspaceSummary[]>('/workspaces')
  return response.data
}
