import { useEffect, useState } from 'react'
import { Button, Empty, List, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getInterviewSessions, getPositions } from '../api/interviews'
import { getEnterpriseApplications } from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { InterviewSession, JobPosition } from '../types/interview'
import type { JobApplication } from '../types/recruitment'
import { getActiveWorkspace } from '../utils/workspaceStorage'

function EnterpriseDashboardPage() {
  const workspace = getActiveWorkspace()
  const role = workspace?.role ?? 'VIEWER'
  const canRecruit = ['OWNER', 'ADMIN', 'HR'].includes(role)
  const navigate = useNavigate()
  const [positions, setPositions] = useState<JobPosition[]>([])
  const [applications, setApplications] = useState<JobApplication[]>([])
  const [interviews, setInterviews] = useState<InterviewSession[]>([])

  useEffect(() => {
    if (!workspace) return
    Promise.all([
      getPositions(workspace.id),
      canRecruit ? getEnterpriseApplications(workspace.id) : Promise.resolve([]),
      getInterviewSessions(workspace.id),
    ]).then(([positionItems, applicationItems, interviewItems]) => {
      setPositions(positionItems)
      setApplications(applicationItems)
      setInterviews(interviewItems)
    }).catch(() => undefined)
  }, [workspace?.id, canRecruit])

  const pendingApplications = applications.filter((item) => ['SUBMITTED', 'REVIEWING'].includes(item.status))

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        <EnterpriseSidebar workspace={workspace} />
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">ENTERPRISE</p>
              <Typography.Title level={2}>{workspace?.name ?? '企业工作台'}</Typography.Title>
              <Typography.Paragraph type="secondary">当前角色：<Tag color="blue">{role}</Tag></Typography.Paragraph>
            </div>
          </div>
          <div className="metric-grid">
            <div className="metric-item"><span>进行中岗位</span><strong>{positions.filter((item) => item.status === 'ACTIVE').length}</strong></div>
            <div className="metric-item"><span>待处理申请</span><strong>{pendingApplications.length}</strong></div>
            <div className="metric-item"><span>已完成面试</span><strong>{interviews.filter((item) => item.status === 'COMPLETED').length}</strong></div>
          </div>
          <section className="content-panel wide-panel">
            <div className="panel-heading"><Typography.Title level={4}>待处理岗位申请</Typography.Title>{canRecruit && <Button type="link" onClick={() => navigate('/enterprise/applications')}>全部申请</Button>}</div>
            {pendingApplications.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待处理申请" /> : (
              <List dataSource={pendingApplications.slice(0, 6)} renderItem={(item) => (
                <List.Item actions={[<Button key="view" type="link" onClick={() => navigate('/enterprise/applications')}>处理</Button>]}>
                  <List.Item.Meta title={`${item.candidate_name} · ${item.job_title}`} description={new Date(item.submitted_at).toLocaleString('zh-CN')} />
                </List.Item>
              )} />
            )}
          </section>
        </section>
      </div>
    </main>
  )
}

export default EnterpriseDashboardPage
