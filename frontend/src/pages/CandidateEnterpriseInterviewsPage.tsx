import { useEffect, useState } from 'react'
import { MessageOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Empty, Progress, Space, Table, Tag, Tooltip, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getCandidateApplications } from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import type { JobApplication } from '../types/recruitment'
import { getApiErrorMessage } from '../utils/apiError'

const interviewStatusLabel: Record<string, string> = {
  DRAFT: '等待生成计划',
  PLANNING: '计划生成中',
  READY: '待开始',
  IN_PROGRESS: '进行中',
  COMPLETED: '已完成',
  FAILED: '计划生成失败',
  CANCELLED: '已取消',
}

const interviewStatusColor: Record<string, string> = {
  READY: 'blue',
  IN_PROGRESS: 'gold',
  COMPLETED: 'green',
  FAILED: 'red',
  CANCELLED: 'default',
}

function CandidateEnterpriseInterviewsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<JobApplication[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const applications = await getCandidateApplications()
      setItems(applications.filter((item) => (
        item.interview_session_id !== null
        && ['INTERVIEW', 'HIRED', 'REJECTED'].includes(item.status)
      )))
    } catch (error) {
      message.error(getApiErrorMessage(error, '企业面试加载失败'))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => { void loadData() }, [])
  const hasPendingResult = items.some((item) => (
    ['DRAFT', 'PLANNING', 'READY', 'IN_PROGRESS'].includes(item.interview_status ?? '')
    || (item.interview_status === 'COMPLETED' && item.status === 'INTERVIEW')
  ))
  useEffect(() => {
    if (!hasPendingResult) return
    const timer = window.setInterval(() => { void loadData(false) }, 5000)
    return () => window.clearInterval(timer)
  }, [hasPendingResult])

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        <CandidateSidebar />
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">ENTERPRISE INTERVIEWS</p>
              <Typography.Title level={2}>企业面试</Typography.Title>
              <Typography.Paragraph type="secondary">查看企业邀请并进入对应的技术面试</Typography.Paragraph>
            </div>
            <Tooltip title="刷新">
              <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadData()} aria-label="刷新企业面试" />
            </Tooltip>
          </div>

          <section className="content-panel management-panel">
            {!loading && items.length === 0 ? <Empty description="暂无企业面试邀请" /> : (
              <Table<JobApplication>
                rowKey="id"
                loading={loading}
                dataSource={items}
                pagination={false}
                scroll={{ x: 720 }}
                columns={[
                  { title: '企业', dataIndex: 'workspace_name', key: 'company' },
                  { title: '岗位', dataIndex: 'job_title', key: 'job' },
                  {
                    title: '面试状态',
                    dataIndex: 'interview_status',
                    key: 'status',
                    render: (value: string | null) => value
                      ? <Tag color={interviewStatusColor[value]}>{interviewStatusLabel[value] ?? value}</Tag>
                      : '-',
                  },
                  {
                    title: '进度/结果',
                    key: 'result',
                    width: 160,
                    render: (_: unknown, item: JobApplication) => {
                      if (item.status === 'HIRED') return <Tag color="green">已通过</Tag>
                      if (item.status === 'REJECTED') return <Tag color="red">未通过</Tag>
                      if (item.interview_status === 'COMPLETED') return <Tag color="gold">结果待公布</Tag>
                      if (item.interview_status === 'IN_PROGRESS') {
                        const completed = item.interview_current_question_order ?? 0
                        const maximum = item.interview_max_question_count ?? 10
                        return <Progress percent={Math.min(100, Math.round((completed / maximum) * 100))} size="small" />
                      }
                      return '-'
                    },
                  },
                  { title: '邀请时间', dataIndex: 'updated_at', key: 'updated', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
                  {
                    title: '操作',
                    key: 'actions',
                    width: 150,
                    render: (_: unknown, item: JobApplication) => (
                      <Space>
                        {item.interview_session_id && ['READY', 'IN_PROGRESS'].includes(item.interview_status ?? '') && (
                          <Tooltip title={item.interview_status === 'READY' ? '进入面试' : '继续面试'}>
                            <Button
                              type="primary"
                              icon={<PlayCircleOutlined />}
                              onClick={() => navigate(`/candidate/enterprise-interviews/${item.interview_session_id}/run`)}
                              aria-label={item.interview_status === 'READY' ? '进入面试' : '继续面试'}
                            />
                          </Tooltip>
                        )}
                        <Tooltip title="查看消息">
                          <Button type="text" icon={<MessageOutlined />} onClick={() => navigate(`/candidate/messages?thread=${item.thread_id}`)} aria-label="查看消息" />
                        </Tooltip>
                      </Space>
                    ),
                  },
                ]}
              />
            )}
          </section>
        </section>
      </div>
    </main>
  )
}

export default CandidateEnterpriseInterviewsPage
