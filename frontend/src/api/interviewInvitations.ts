import axios from 'axios'
import type {
  CandidateInterviewAccess,
  InterviewInvitation,
  InterviewInvitationCreated,
  InterviewInvitationCreateRequest,
  InterviewInvitationVerifyRequest,
  InterviewAnswerSubmitRequest,
  InterviewRuntime,
  PublicInterviewInvitation,
} from '../types/interviewInvitation'
import { apiClient } from './client'

const publicClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 180000,
})

const invitationPath = (workspaceId: string, interviewId: string) =>
  `/workspaces/${workspaceId}/interviews/${interviewId}/invitations`

export async function getInterviewInvitations(workspaceId: string, interviewId: string) {
  const response = await apiClient.get<InterviewInvitation[]>(invitationPath(workspaceId, interviewId))
  return response.data
}

export async function createInterviewInvitation(
  workspaceId: string,
  interviewId: string,
  request: InterviewInvitationCreateRequest,
) {
  const response = await apiClient.post<InterviewInvitationCreated>(
    invitationPath(workspaceId, interviewId),
    request,
  )
  return response.data
}

export async function revokeInterviewInvitation(
  workspaceId: string,
  interviewId: string,
  invitationId: string,
) {
  await apiClient.post(`${invitationPath(workspaceId, interviewId)}/${invitationId}/revoke`)
}

export async function getPublicInterviewInvitation(token: string) {
  const response = await publicClient.get<PublicInterviewInvitation>(`/interview-invitations/${token}`)
  return response.data
}

export async function verifyPublicInterviewInvitation(
  token: string,
  request: InterviewInvitationVerifyRequest,
) {
  const response = await publicClient.post<CandidateInterviewAccess>(
    `/interview-invitations/${token}/verify`,
    request,
  )
  return response.data
}

const candidateHeaders = (accessToken: string) => ({
  headers: { 'X-Interview-Access-Token': accessToken },
})

export async function getPublicInterviewRuntime(invitationId: string, accessToken: string) {
  const response = await publicClient.get<InterviewRuntime>(
    `/candidate-interviews/${invitationId}/runtime`,
    candidateHeaders(accessToken),
  )
  return response.data
}

export async function startPublicInterview(invitationId: string, accessToken: string) {
  const response = await publicClient.post<InterviewRuntime>(
    `/candidate-interviews/${invitationId}/start`,
    undefined,
    candidateHeaders(accessToken),
  )
  return response.data
}

export async function submitPublicInterviewAnswer(
  invitationId: string,
  questionId: string,
  request: InterviewAnswerSubmitRequest,
  accessToken: string,
) {
  const response = await publicClient.post<InterviewRuntime>(
    `/candidate-interviews/${invitationId}/questions/${questionId}/answer`,
    request,
    candidateHeaders(accessToken),
  )
  return response.data
}

export async function skipPublicInterviewQuestion(
  invitationId: string,
  questionId: string,
  accessToken: string,
) {
  const response = await publicClient.post<InterviewRuntime>(
    `/candidate-interviews/${invitationId}/questions/${questionId}/skip`,
    undefined,
    candidateHeaders(accessToken),
  )
  return response.data
}

export async function finishPublicInterview(invitationId: string, accessToken: string) {
  const response = await publicClient.post<InterviewRuntime>(
    `/candidate-interviews/${invitationId}/finish`,
    undefined,
    candidateHeaders(accessToken),
  )
  return response.data
}
