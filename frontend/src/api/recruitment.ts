import type { InterviewAnswerSubmitRequest, InterviewRuntime, InterviewSession } from '../types/interview'
import type {
  ApplicationInterviewCreateRequest,
  JobApplication,
  JobApplicationCreateRequest,
  InterviewDecision,
  MessageThread,
  PlatformMessage,
  PublishedJob,
} from '../types/recruitment'
import { apiClient } from './client'

export async function getPublishedJobs() {
  const response = await apiClient.get<PublishedJob[]>('/candidate/jobs')
  return response.data
}

export async function submitJobApplication(request: JobApplicationCreateRequest) {
  const response = await apiClient.post<JobApplication>('/candidate/applications', request, { timeout: 30000 })
  return response.data
}

export async function getCandidateApplications() {
  const response = await apiClient.get<JobApplication[]>('/candidate/applications')
  return response.data
}

export async function withdrawJobApplication(applicationId: string) {
  const response = await apiClient.post<JobApplication>(`/candidate/applications/${applicationId}/withdraw`)
  return response.data
}

export async function getEnterpriseApplications(workspaceId: string) {
  const response = await apiClient.get<JobApplication[]>(`/workspaces/${workspaceId}/applications`)
  return response.data
}

export async function downloadApplicationResume(
  workspaceId: string,
  applicationId: string,
  filename: string,
) {
  const response = await apiClient.get<Blob>(
    `/workspaces/${workspaceId}/applications/${applicationId}/resume`,
    { responseType: 'blob' },
  )
  const objectUrl = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    anchor.remove()
    URL.revokeObjectURL(objectUrl)
  }, 1000)
}

export async function updateJobApplicationStatus(
    workspaceId: string,
    applicationId: string,
    applicationStatus: 'REVIEWING' | 'REJECTED' | 'HIRED',
    decisionNote?: string,
) {
  const response = await apiClient.patch<JobApplication>(
    `/workspaces/${workspaceId}/applications/${applicationId}/status`,
    { status: applicationStatus, decision_note: decisionNote?.trim() || null },
  )
  return response.data
}

export async function getInterviewApplication(workspaceId: string, interviewId: string) {
  const response = await apiClient.get<JobApplication>(
    `/workspaces/${workspaceId}/interviews/${interviewId}/application`,
  )
  return response.data
}

export async function getInterviewDecision(workspaceId: string, interviewId: string) {
  const response = await apiClient.get<InterviewDecision>(
    `/workspaces/${workspaceId}/interviews/${interviewId}/decision`,
  )
  return response.data
}

export async function createInterviewDecision(
  workspaceId: string,
  interviewId: string,
  decision: 'HIRED' | 'REJECTED',
  internalNote?: string,
) {
  const response = await apiClient.post<InterviewDecision>(
    `/workspaces/${workspaceId}/interviews/${interviewId}/decision`,
    { decision, internal_note: internalNote?.trim() || null },
  )
  return response.data
}

export async function createApplicationInterview(
  workspaceId: string,
  applicationId: string,
  request: ApplicationInterviewCreateRequest,
) {
  const response = await apiClient.post<InterviewSession>(
    `/workspaces/${workspaceId}/applications/${applicationId}/interview`,
    request,
  )
  return response.data
}

export async function sendPlatformInterviewInvitation(
  workspaceId: string,
  applicationId: string,
  interviewId: string,
) {
  const response = await apiClient.post<PlatformMessage>(
    `/workspaces/${workspaceId}/applications/${applicationId}/interview-invitation`,
    undefined,
    { params: { interview_id: interviewId } },
  )
  return response.data
}

export async function getMessageThreads(workspaceId?: string) {
  const response = await apiClient.get<MessageThread[]>('/message-threads', {
    params: workspaceId ? { workspace_id: workspaceId } : undefined,
  })
  return response.data
}

export async function getThreadMessages(threadId: string) {
  const response = await apiClient.get<PlatformMessage[]>(`/message-threads/${threadId}/messages`)
  return response.data
}

export async function sendThreadMessage(threadId: string, content: string) {
  const response = await apiClient.post<PlatformMessage>(`/message-threads/${threadId}/messages`, { content })
  return response.data
}

const assignedPath = (interviewId: string) => `/candidate/assigned-interviews/${interviewId}`

export async function getAssignedInterviewRuntime(interviewId: string) {
  const response = await apiClient.get<InterviewRuntime>(`${assignedPath(interviewId)}/runtime`, { timeout: 180000 })
  return response.data
}

export async function startAssignedInterview(interviewId: string) {
  const response = await apiClient.post<InterviewRuntime>(`${assignedPath(interviewId)}/start`, undefined, { timeout: 180000 })
  return response.data
}

export async function submitAssignedInterviewAnswer(
  interviewId: string,
  questionId: string,
  request: InterviewAnswerSubmitRequest,
) {
  const response = await apiClient.post<InterviewRuntime>(
    `${assignedPath(interviewId)}/questions/${questionId}/answer`,
    request,
    { timeout: 180000 },
  )
  return response.data
}

export async function skipAssignedInterviewQuestion(interviewId: string, questionId: string) {
  const response = await apiClient.post<InterviewRuntime>(
    `${assignedPath(interviewId)}/questions/${questionId}/skip`,
    undefined,
    { timeout: 180000 },
  )
  return response.data
}

export async function finishAssignedInterview(interviewId: string) {
  const response = await apiClient.post<InterviewRuntime>(`${assignedPath(interviewId)}/finish`)
  return response.data
}
