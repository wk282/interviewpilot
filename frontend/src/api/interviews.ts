import type {
  CandidateProfile,
  CandidateProfileCreateRequest,
  CandidateProfileUpdateRequest,
  InterviewSession,
  InterviewSessionCreateRequest,
  InterviewPlan,
  InterviewAnswerSubmitRequest,
  InterviewEvaluation,
  InterviewRuntime,
  JobPosition,
  JobPositionCreateRequest,
  JobPositionUpdateRequest,
} from '../types/interview'
import { apiClient } from './client'

const workspacePath = (workspaceId: string) => `/workspaces/${workspaceId}`

export async function getPositions(workspaceId: string) {
  const response = await apiClient.get<JobPosition[]>(`${workspacePath(workspaceId)}/positions`)
  return response.data
}

export async function createPosition(workspaceId: string, request: JobPositionCreateRequest) {
  const response = await apiClient.post<JobPosition>(`${workspacePath(workspaceId)}/positions`, request)
  return response.data
}

export async function updatePosition(
  workspaceId: string,
  positionId: string,
  request: JobPositionUpdateRequest,
) {
  const response = await apiClient.patch<JobPosition>(
    `${workspacePath(workspaceId)}/positions/${positionId}`,
    request,
  )
  return response.data
}

export async function deletePosition(workspaceId: string, positionId: string) {
  await apiClient.delete(`${workspacePath(workspaceId)}/positions/${positionId}`)
}

export async function getCandidates(workspaceId: string) {
  const response = await apiClient.get<CandidateProfile[]>(`${workspacePath(workspaceId)}/candidates`)
  return response.data
}

export async function createCandidate(workspaceId: string, request: CandidateProfileCreateRequest) {
  const response = await apiClient.post<CandidateProfile>(`${workspacePath(workspaceId)}/candidates`, request)
  return response.data
}

export async function updateCandidate(
  workspaceId: string,
  candidateId: string,
  request: CandidateProfileUpdateRequest,
) {
  const response = await apiClient.patch<CandidateProfile>(
    `${workspacePath(workspaceId)}/candidates/${candidateId}`,
    request,
  )
  return response.data
}

export async function deleteCandidate(workspaceId: string, candidateId: string) {
  await apiClient.delete(`${workspacePath(workspaceId)}/candidates/${candidateId}`)
}

export async function getInterviewSessions(workspaceId: string) {
  const response = await apiClient.get<InterviewSession[]>(`${workspacePath(workspaceId)}/interviews`)
  return response.data
}

export async function createInterviewSession(
  workspaceId: string,
  request: InterviewSessionCreateRequest,
) {
  const response = await apiClient.post<InterviewSession>(
    `${workspacePath(workspaceId)}/interviews`,
    request,
  )
  return response.data
}

export async function deleteInterviewSession(workspaceId: string, interviewId: string) {
  await apiClient.delete(`${workspacePath(workspaceId)}/interviews/${interviewId}`)
}

export async function generateInterviewPlan(workspaceId: string, interviewId: string) {
  const response = await apiClient.post<InterviewPlan>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/plan`,
  )
  return response.data
}

export async function getInterviewPlan(workspaceId: string, interviewId: string) {
  const response = await apiClient.get<InterviewPlan>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/plan`,
  )
  return response.data
}

export async function getInterviewRuntime(workspaceId: string, interviewId: string) {
  const response = await apiClient.get<InterviewRuntime>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/runtime`,
    { timeout: 180000 },
  )
  return response.data
}

export async function startInterview(workspaceId: string, interviewId: string) {
  const response = await apiClient.post<InterviewRuntime>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/start`,
    undefined,
    { timeout: 180000 },
  )
  return response.data
}

export async function submitInterviewAnswer(
  workspaceId: string,
  interviewId: string,
  questionId: string,
  request: InterviewAnswerSubmitRequest,
) {
  const response = await apiClient.post<InterviewRuntime>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/questions/${questionId}/answer`,
    request,
    { timeout: 180000 },
  )
  return response.data
}

export async function skipInterviewQuestion(
  workspaceId: string,
  interviewId: string,
  questionId: string,
) {
  const response = await apiClient.post<InterviewRuntime>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/questions/${questionId}/skip`,
    undefined,
    { timeout: 180000 },
  )
  return response.data
}

export async function finishInterview(workspaceId: string, interviewId: string) {
  const response = await apiClient.post<InterviewRuntime>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/finish`,
  )
  return response.data
}

export async function createInterviewEvaluation(workspaceId: string, interviewId: string) {
  const response = await apiClient.post<InterviewEvaluation>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/evaluation`,
    undefined,
    { timeout: 30000 },
  )
  return response.data
}

export async function getInterviewEvaluation(workspaceId: string, interviewId: string) {
  const response = await apiClient.get<InterviewEvaluation>(
    `${workspacePath(workspaceId)}/interviews/${interviewId}/evaluation`,
  )
  return response.data
}
