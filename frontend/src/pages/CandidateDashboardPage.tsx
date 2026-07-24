import { useEffect, useState } from 'react'
import { MessageOutlined, PlayCircleOutlined, RobotOutlined } from '@ant-design/icons'
import { Button, Empty, List, Progress, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getCandidates, getInterviewSessions } from '../api/interviews'
import { getCandidateApplications } from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import type { CandidateProfile, InterviewSession } from '../types/interview'
import type { JobApplication } from '../types/recruitment'
import { getStoredUser } from '../utils/authStorage'
import { getActiveWorkspace } from '../utils/workspaceStorage'

function CandidateDashboardPage() {
  const user = getStoredUser()
  const workspace = getActiveWorkspace()
  const navigate = useNavigate()
  const [applications, setApplications] = useState<JobApplication[]>([])
  const [interviews, setInterviews] = useState<InterviewSession[]>([])
  const [profile, setProfile] = useState<CandidateProfile | null>(null)

  useEffect(() => {
    if (!workspace) return
    Promise.all([
      getCandidateApplications(),
      getInterviewSessions(workspace.id),
      getCandidates(workspace.id),
    ]).then(([applicationItems, interviewItems, candidateItems]) => {
      setApplications(applicationItems)
      setInterviews(interviewItems)
      setProfile(candidateItems.find((item) => item.source === 'PERSONAL_ACCOUNT') ?? null)
    }).catch(() => undefined)
  }, [workspace?.id])

  const assignedInterviews = applications.filter((item) => (
    item.interview_session_id
    && ['INTERVIEW', 'HIRED', 'REJECTED'].includes(item.status)
  ))
  const completedMocks = interviews.filter((item) => item.status === 'COMPLETED').length
  const resumeProgress = profile?.resume_document_id ? 100 : 0

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        <CandidateSidebar />

        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">CANDIDATE</p>
              <Typography.Title level={2}>你好，{user?.display_name ?? '求职者'}</Typography.Title>
              <Typography.Paragraph type="secondary">准备下一次技术面试</Typography.Paragraph>
            </div>
            <Button type="primary" size="large" icon={<RobotOutlined />} onClick={() => navigate('/candidate/interviews')}>开始模拟面试</Button>
          </div>

          <div className="metric-grid">
            <div className="metric-item"><span>企业面试阶段</span><strong>{assignedInterviews.length}</strong></div>
            <div className="metric-item"><span>已完成模拟面试</span><strong>{completedMocks}</strong></div>
            <div className="metric-item"><span>简历完整度</span><strong>{resumeProgress}%</strong></div>
          </div>

          <div className="dashboard-columns">
            <section className="content-panel">
              <div className="panel-heading"><Typography.Title level={4}>企业面试</Typography.Title><Button type="link" onClick={() => navigate('/candidate/enterprise-interviews')}>查看全部</Button></div>
              {assignedInterviews.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无企业面试邀请" /> : (
                <List dataSource={assignedInterviews.slice(0, 5)} renderItem={(item) => (
                  <List.Item actions={[
                    ...(['READY', 'IN_PROGRESS'].includes(item.interview_status ?? '') && item.interview_session_id
                      ? [<Button key="enter" type="primary" icon={<PlayCircleOutlined />} onClick={() => navigate(`/candidate/enterprise-interviews/${item.interview_session_id}/run`)}>进入面试</Button>]
                      : []),
                    <Button key="message" type="text" icon={<MessageOutlined />} onClick={() => navigate(`/candidate/messages?thread=${item.thread_id}`)}>查看消息</Button>,
                  ]}>
                    <List.Item.Meta title={`${item.workspace_name} · ${item.job_title}`} description={item.interview_status ?? '等待面试计划'} />
                  </List.Item>
                )} />
              )}
            </section>
            <section className="content-panel">
              <div className="panel-heading"><Typography.Title level={4}>准备进度</Typography.Title></div>
              <div className="progress-row"><span>简历</span><Progress percent={resumeProgress} /></div>
              <div className="progress-row"><span>岗位投递</span><Progress percent={applications.length > 0 ? 100 : 0} /></div>
              <div className="progress-row"><span>模拟面试</span><Progress percent={interviews.length > 0 ? 100 : 0} /></div>
            </section>
          </div>
        </section>
      </div>
    </main>
  )
}

export default CandidateDashboardPage
