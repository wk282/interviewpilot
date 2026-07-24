import type { InterviewAnswerSubmitRequest, InterviewRuntime } from './interview'

export interface InterviewInvitationCreateRequest {
  email: string
  expires_in_days: number
  max_access_count: number
}

export interface InterviewInvitation {
  id: string
  interview_session_id: string
  email: string
  status: string
  max_access_count: number
  access_count: number
  expires_at: string
  opened_at: string | null
  verified_at: string | null
  consented_at: string | null
  started_at: string | null
  completed_at: string | null
  revoked_at: string | null
  created_at: string
  invitation_token: string | null
  access_code: string | null
}

export interface InterviewInvitationCreated extends InterviewInvitation {
  invitation_token: string
  access_code: string
}

export interface PublicInterviewInvitation {
  invitation_id: string
  workspace_name: string
  job_title: string
  candidate_name: string
  masked_email: string
  scheduled_at: string | null
  expires_at: string
  status: string
  evaluation_status: 'PENDING' | 'GENERATING' | 'COMPLETED' | 'FAILED' | null
  decision: 'HIRED' | 'REJECTED' | null
  decided_at: string | null
}

export interface InterviewInvitationVerifyRequest {
  email: string
  access_code: string
  consent: boolean
}

export interface CandidateInterviewAccess {
  invitation_id: string
  interview_session_id: string
  access_token: string
  token_type: 'candidate_interview'
  expires_at: string
}

export type { InterviewAnswerSubmitRequest, InterviewRuntime }
