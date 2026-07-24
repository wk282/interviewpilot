export type KnowledgeBasePurpose =
  | 'RESUME'
  | 'PERSONAL_LEARNING'
  | 'ENTERPRISE_QUESTION_BANK'
  | 'JOB_SPECIFIC'
  | 'SCORING_RUBRIC'
  | 'TECHNICAL_STANDARD'

export interface KnowledgeBase {
  id: string
  workspace_id: string
  name: string
  purpose: KnowledgeBasePurpose
  visibility: 'PRIVATE' | 'WORKSPACE'
  created_by: string
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseCreateRequest {
  name: string
  purpose: KnowledgeBasePurpose
  visibility: 'PRIVATE' | 'WORKSPACE'
}

export interface KnowledgeBaseUpdateRequest {
  name?: string
  purpose?: KnowledgeBasePurpose
  visibility?: 'PRIVATE' | 'WORKSPACE'
}
