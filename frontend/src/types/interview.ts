export interface JobPosition {
  id: string
  workspace_id: string
  knowledge_base_id: string | null
  title: string
  department: string | null
  description: string | null
  requirements: Record<string, unknown>
  status: 'DRAFT' | 'ACTIVE' | 'CLOSED'
  created_by: string
  created_at: string
  updated_at: string
}

export interface JobPositionCreateRequest {
  title: string
  department?: string
  description?: string
  knowledge_base_id?: string
  status: 'DRAFT' | 'ACTIVE'
}

export interface JobPositionUpdateRequest {
  title?: string
  department?: string
  description?: string
  knowledge_base_id?: string | null
  status?: 'DRAFT' | 'ACTIVE' | 'CLOSED'
}

export interface CandidateProfile {
  id: string
  workspace_id: string
  user_id: string | null
  resume_knowledge_base_id: string | null
  resume_document_id: string | null
  full_name: string
  email: string | null
  phone: string | null
  source: 'PERSONAL_ACCOUNT' | 'ENTERPRISE_IMPORT'
  status: 'ACTIVE' | 'ARCHIVED'
  profile_data: Record<string, unknown>
  created_by: string
  created_at: string
  updated_at: string
}

export interface CandidateProfileCreateRequest {
  full_name: string
  email?: string
  phone?: string
  resume_document_id: string
}

export interface CandidateProfileUpdateRequest {
  full_name?: string
  email?: string
  phone?: string
  resume_document_id?: string | null
  status?: 'ACTIVE' | 'ARCHIVED'
}

export interface InterviewSession {
  id: string
  workspace_id: string
  job_position_id: string
  job_title: string
  candidate_profile_id: string
  candidate_name: string
  interviewer_id: string | null
  application_id: string | null
  mode: 'MOCK' | 'ENTERPRISE'
  status: string
  current_question_order: number
  configuration: Record<string, unknown>
  scheduled_at: string | null
  started_at: string | null
  completed_at: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface InterviewSessionCreateRequest {
  job_position_id: string
  candidate_profile_id: string
  application_id?: string
  reference_knowledge_base_ids?: string[]
  max_question_count?: number
  question_time_limit_minutes?: number
}

export interface InterviewQuestion {
  id: string
  order_no: number
  question_type: string
  content: string
  competency: string | null
  difficulty: 'EASY' | 'MEDIUM' | 'HARD'
  generated_by: string
  status: string
  max_score: number
  expected_points: string[]
  source_evidence: Array<Record<string, unknown>>
}

export interface InterviewPlan {
  id: string
  interview_session_id: string
  version: number
  status: 'DRAFT' | 'READY' | 'FAILED'
  objectives: string[]
  sections: Array<Record<string, unknown>>
  model_name: string | null
  prompt_version: string | null
  generated_at: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  questions: InterviewQuestion[]
}

export interface InterviewRuntimeQuestion {
  id: string
  order_no: number
  question_type: string
  content: string
  competency: string | null
  difficulty: 'EASY' | 'MEDIUM' | 'HARD'
  generated_by: 'PLAN' | 'FOLLOW_UP' | 'HUMAN'
  asked_at: string | null
}

export interface InterviewRuntime {
  interview_id: string
  status: string
  current_question: InterviewRuntimeQuestion | null
  completed_question_count: number
  total_question_count: number
  max_question_count: number
  question_time_limit_seconds: number | null
  started_at: string | null
  completed_at: string | null
  follow_up_generated: boolean
  question_timed_out: boolean
}

export interface InterviewAnswerSubmitRequest {
  content: string
  duration_seconds?: number
  client_metadata?: Record<string, unknown>
}

export interface InterviewEvaluation {
  id: string
  interview_session_id: string
  status: 'PENDING' | 'GENERATING' | 'COMPLETED' | 'FAILED'
  overall_score: number | null
  dimension_scores: Record<string, number>
  strengths: string[]
  weaknesses: string[]
  evidence: Array<{
    evidence_id: number
    question_id: string
    question: string
    answer_excerpt: string
    dimension: string
    score: number
    finding: string
  }>
  report_text: string | null
  recommendation: string | null
  model_name: string | null
  prompt_version: string | null
  error_message: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
}
