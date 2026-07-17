export interface PublishedJob {
  id: string
  workspace_id: string
  workspace_name: string
  title: string
  department: string | null
  description: string | null
  requirements: Record<string, unknown>
  created_at: string
  applied: boolean
}

export interface JobApplicationCreateRequest {
  job_position_id: string
  resume_document_id: string
  cover_letter?: string
  consent: boolean
}

export interface JobApplication {
  id: string
  workspace_id: string
  workspace_name: string
  job_position_id: string
  job_title: string
  candidate_user_id: string
  candidate_profile_id: string
  candidate_name: string
  candidate_email: string
  candidate_phone: string | null
  candidate_profile_data: Record<string, unknown>
  status: 'SUBMITTED' | 'REVIEWING' | 'INTERVIEW' | 'REJECTED' | 'WITHDRAWN' | 'HIRED'
  cover_letter: string | null
  resume_document_id: string | null
  resume_filename: string
  resume_status: string | null
  interview_session_id: string | null
  interview_status: string | null
  thread_id: string
  submitted_at: string
  reviewed_at: string | null
  withdrawn_at: string | null
  decision_note: string | null
  decided_by: string | null
  decided_by_name: string | null
  decided_at: string | null
  created_at: string
  updated_at: string
}

export interface ApplicationInterviewCreateRequest {
  max_question_count: number
  question_time_limit_minutes: number
  scheduled_at?: string
}

export interface InterviewDecision {
  interview_session_id: string
  application_id: string | null
  application_status: string | null
  decision: 'HIRED' | 'REJECTED' | null
  internal_note: string | null
  decided_by: string | null
  decided_by_name: string | null
  decided_at: string | null
}

export interface MessageThread {
  id: string
  application_id: string
  workspace_id: string
  workspace_name: string
  job_title: string
  candidate_name: string
  subject: string
  application_status: string
  unread_count: number
  latest_message: string | null
  latest_message_at: string | null
  updated_at: string
}

export interface PlatformMessage {
  id: string
  thread_id: string
  sender_type: 'CANDIDATE' | 'ENTERPRISE' | 'SYSTEM'
  sender_user_id: string | null
  sender_name: string | null
  message_type: 'TEXT' | 'INTERVIEW_INVITATION' | 'APPLICATION_STATUS'
  interview_session_id: string | null
  content: string
  message_metadata: Record<string, unknown>
  created_at: string
}
