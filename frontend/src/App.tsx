import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import RoleRoute from './components/RoleRoute'
import WorkspaceRoute from './components/WorkspaceRoute'
import CandidateDashboardPage from './pages/CandidateDashboardPage'
import CandidateInterviewInvitationPage from './pages/CandidateInterviewInvitationPage'
import CandidateEnterpriseInterviewsPage from './pages/CandidateEnterpriseInterviewsPage'
import CandidateJobsPage from './pages/CandidateJobsPage'
import EnterpriseDashboardPage from './pages/EnterpriseDashboardPage'
import DocumentsPage from './pages/DocumentsPage'
import EnterpriseMembersPage from './pages/EnterpriseMembersPage'
import EnterpriseApplicationsPage from './pages/EnterpriseApplicationsPage'
import HomeResolverPage from './pages/HomeResolverPage'
import InvitationAcceptPage from './pages/InvitationAcceptPage'
import InterviewManagementPage from './pages/InterviewManagementPage'
import InterviewExecutionPage from './pages/InterviewExecutionPage'
import InterviewReportPage from './pages/InterviewReportPage'
import KnowledgeBasesPage from './pages/KnowledgeBasesPage'
import LoginPage from './pages/LoginPage'
import MessagesPage from './pages/MessagesPage'
import RegisterPage from './pages/RegisterPage'
import ResumesPage from './pages/ResumesPage'
import RetrievalTestPage from './pages/RetrievalTestPage'

const protectedPage = (page: ReactNode) => <ProtectedRoute>{page}</ProtectedRoute>
const workspacePage = (type: 'PERSONAL' | 'ORGANIZATION', page: ReactNode) => (
  <ProtectedRoute><WorkspaceRoute type={type}>{page}</WorkspaceRoute></ProtectedRoute>
)

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/invitations/:token" element={<InvitationAcceptPage />} />
      <Route path="/candidate-interviews/invitations/:token" element={<CandidateInterviewInvitationPage />} />
      <Route path="/home" element={protectedPage(<HomeResolverPage />)} />
      <Route path="/candidate/dashboard" element={workspacePage('PERSONAL', <CandidateDashboardPage />)} />
      <Route path="/candidate/interviews" element={workspacePage('PERSONAL', <InterviewManagementPage />)} />
      <Route path="/candidate/interviews/:interviewId/run" element={workspacePage('PERSONAL', <InterviewExecutionPage />)} />
      <Route path="/candidate/interviews/:interviewId/report" element={workspacePage('PERSONAL', <InterviewReportPage />)} />
      <Route path="/candidate/enterprise-interviews" element={workspacePage('PERSONAL', <CandidateEnterpriseInterviewsPage />)} />
      <Route path="/candidate/enterprise-interviews/:interviewId/run" element={workspacePage('PERSONAL', <InterviewExecutionPage />)} />
      <Route path="/candidate/jobs" element={workspacePage('PERSONAL', <CandidateJobsPage />)} />
      <Route path="/candidate/messages" element={workspacePage('PERSONAL', <MessagesPage />)} />
      <Route path="/candidate/resumes" element={workspacePage('PERSONAL', <ResumesPage />)} />
      <Route path="/candidate/knowledge-bases" element={workspacePage('PERSONAL', <KnowledgeBasesPage />)} />
      <Route path="/candidate/knowledge-bases/:knowledgeBaseId/documents" element={workspacePage('PERSONAL', <DocumentsPage />)} />
      <Route path="/candidate/knowledge-bases/:knowledgeBaseId/retrieval" element={workspacePage('PERSONAL', <RetrievalTestPage />)} />
      <Route path="/enterprise/dashboard" element={workspacePage('ORGANIZATION', <EnterpriseDashboardPage />)} />
      <Route path="/enterprise/interviews" element={workspacePage('ORGANIZATION', <InterviewManagementPage />)} />
      <Route path="/enterprise/interviews/:interviewId/run" element={workspacePage('ORGANIZATION', <InterviewExecutionPage />)} />
      <Route path="/enterprise/interviews/:interviewId/report" element={workspacePage('ORGANIZATION', <InterviewReportPage />)} />
      <Route path="/enterprise/applications" element={workspacePage('ORGANIZATION', <RoleRoute roles={['OWNER', 'ADMIN', 'HR']}><EnterpriseApplicationsPage /></RoleRoute>)} />
      <Route path="/enterprise/messages" element={workspacePage('ORGANIZATION', <MessagesPage />)} />
      <Route path="/enterprise/knowledge-bases" element={workspacePage('ORGANIZATION', <KnowledgeBasesPage />)} />
      <Route path="/enterprise/knowledge-bases/:knowledgeBaseId/documents" element={workspacePage('ORGANIZATION', <DocumentsPage />)} />
      <Route path="/enterprise/knowledge-bases/:knowledgeBaseId/retrieval" element={workspacePage('ORGANIZATION', <RetrievalTestPage />)} />
      <Route
        path="/enterprise/members"
        element={workspacePage('ORGANIZATION', <RoleRoute roles={['OWNER', 'ADMIN']}><EnterpriseMembersPage /></RoleRoute>)}
      />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  )
}

export default App
