import { useEffect, useState } from 'react'
import { CheckOutlined, DownloadOutlined, EyeOutlined, FileAddOutlined, FileDoneOutlined, MailOutlined, MessageOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Descriptions, Drawer, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Tooltip, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  createApplicationInterview,
  downloadApplicationResume,
  getEnterpriseApplications,
  sendPlatformInterviewInvitation,
  updateJobApplicationStatus,
} from '../api/recruitment'
import { getKnowledgeBases } from '../api/knowledgeBases'
import AppHeader from '../components/AppHeader'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { ApplicationInterviewCreateRequest, JobApplication } from '../types/recruitment'
import type { KnowledgeBase, KnowledgeBasePurpose } from '../types/knowledgeBase'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const statusLabel: Record<string, string> = {
  SUBMITTED: '待处理',
  REVIEWING: '审核中',
  INTERVIEW: '面试阶段',
  REJECTED: '未通过',
  WITHDRAWN: '已撤回',
  HIRED: '已录用',
}

const statusColor: Record<string, string> = {
  SUBMITTED: 'blue',
  REVIEWING: 'gold',
  INTERVIEW: 'purple',
  REJECTED: 'red',
  WITHDRAWN: 'default',
  HIRED: 'green',
}

const knowledgeBasePurposeLabels: Record<KnowledgeBasePurpose, string> = {
  RESUME: '简历',
  PERSONAL_LEARNING: '个人学习资料',
  ENTERPRISE_QUESTION_BANK: '企业题库',
  JOB_SPECIFIC: '岗位专项',
  SCORING_RUBRIC: '评分标准',
  TECHNICAL_STANDARD: '技术规范',
}

function EnterpriseApplicationsPage() {
  const workspace = getActiveWorkspace()
  const navigate = useNavigate()
  const [form] = Form.useForm<ApplicationInterviewCreateRequest>()
  const [applications, setApplications] = useState<JobApplication[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selected, setSelected] = useState<JobApplication | null>(null)
  const [detailApplication, setDetailApplication] = useState<JobApplication | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const loadData = async (showLoading = true) => {
    if (!workspace) return
    if (showLoading) setLoading(true)
    try {
      const [items, knowledgeBaseItems] = await Promise.all([
        getEnterpriseApplications(workspace.id),
        getKnowledgeBases(workspace.id),
      ])
      setApplications(items)
      setKnowledgeBases(knowledgeBaseItems)
      setDetailApplication((current) => (
        current ? items.find((item) => item.id === current.id) ?? null : null
      ))
    } catch (error) {
      message.error(getApiErrorMessage(error, '岗位申请加载失败'))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => { void loadData() }, [workspace?.id])
  useEffect(() => {
    if (!applications.some((item) => ['UPLOADED', 'PROCESSING'].includes(item.resume_status ?? ''))) return
    const timer = window.setInterval(() => { void loadData(false) }, 3000)
    return () => window.clearInterval(timer)
  }, [applications, workspace?.id])

  const changeStatus = async (
    item: JobApplication,
    nextStatus: 'REVIEWING' | 'REJECTED' | 'HIRED',
  ) => {
    if (!workspace) return
    try {
      await updateJobApplicationStatus(workspace.id, item.id, nextStatus)
      message.success('申请状态已更新，候选人将收到站内消息')
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, '申请状态更新失败'))
    }
  }

  const confirmStatus = (
    item: JobApplication,
    nextStatus: 'REJECTED' | 'HIRED',
  ) => {
    Modal.confirm({
      title: nextStatus === 'REJECTED' ? '确认不通过该申请？' : '确认标记为已录用？',
      content: '候选人会立即收到申请状态通知。',
      okText: '确认',
      okButtonProps: { danger: nextStatus === 'REJECTED' },
      cancelText: '取消',
      onOk: () => changeStatus(item, nextStatus),
    })
  }

  const openInterview = (item: JobApplication) => {
    setSelected(item)
    form.setFieldsValue({ max_question_count: 10, question_time_limit_minutes: 10 })
  }

  const createInterview = async (values: ApplicationInterviewCreateRequest) => {
    if (!workspace || !selected) return
    setSaving(true)
    try {
      await createApplicationInterview(workspace.id, selected.id, values)
      message.success('面试会话已创建，请进入面试管理生成计划')
      setSelected(null)
      form.resetFields()
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试创建失败'))
    } finally {
      setSaving(false)
    }
  }

  const referenceKnowledgeBases = knowledgeBases.filter((item) => item.purpose !== 'RESUME')
  const normalizedSearchQuery = searchQuery.trim().toLowerCase()
  const filteredApplications = applications.filter((item) => (
    !normalizedSearchQuery
    || [item.candidate_name, item.candidate_email, item.job_title, item.status, statusLabel[item.status], item.interview_status]
      .some((value) => value?.toLowerCase().includes(normalizedSearchQuery))
  ))

  const sendInvitation = async (item: JobApplication) => {
    if (!workspace || !item.interview_session_id) return
    try {
      await sendPlatformInterviewInvitation(workspace.id, item.id, item.interview_session_id)
      message.success('面试邀请已通过站内消息发送')
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试邀请发送失败'))
    }
  }

  const downloadResume = async (item: JobApplication) => {
    if (!workspace) return
    try {
      await downloadApplicationResume(workspace.id, item.id, item.resume_filename)
      message.success('简历下载已开始')
    } catch (error) {
      message.error(getApiErrorMessage(error, '简历下载失败'))
    }
  }

  const profileEntries = Object.entries(
    detailApplication?.candidate_profile_data ?? {},
  ).filter(([key]) => !['application_id', 'candidate_user_id'].includes(key))

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        <EnterpriseSidebar workspace={workspace} />
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">APPLICATIONS</p>
              <Typography.Title level={2}>岗位申请</Typography.Title>
              <Typography.Paragraph type="secondary">审核候选人投递并安排技术面试</Typography.Paragraph>
            </div>
            <Button onClick={() => navigate('/enterprise/interviews')}>面试管理</Button>
          </div>

          <section className="content-panel management-panel">
            <div className="list-toolbar">
              <Input allowClear prefix={<SearchOutlined />} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索候选人、邮箱或岗位" className="list-search" />
            </div>
            <Table<JobApplication>
              rowKey="id"
              loading={loading}
              dataSource={filteredApplications}
              pagination={{ pageSize: 12 }}
              scroll={{ x: 920 }}
              columns={[
                {
                  title: '候选人',
                  key: 'candidate',
                  width: 210,
                  render: (_, item) => (
                    <div className="application-candidate-summary">
                      <strong>{item.candidate_name}</strong>
                      <span>{item.candidate_email}</span>
                    </div>
                  ),
                },
                { title: '岗位', dataIndex: 'job_title', key: 'job' },
                {
                  title: '简历',
                  key: 'resume',
                  width: 190,
                  render: (_, item) => (
                    <div className="application-resume-summary">
                      <Button type="link" icon={<DownloadOutlined />} onClick={() => downloadResume(item)}>{item.resume_filename}</Button>
                      <Tag color={item.resume_status === 'READY' ? 'green' : 'gold'}>{item.resume_status ?? '不可用'}</Tag>
                    </div>
                  ),
                },
                { title: '申请状态', dataIndex: 'status', key: 'status', render: (value) => <Tag color={statusColor[value]}>{statusLabel[value] ?? value}</Tag> },
                { title: '面试状态', dataIndex: 'interview_status', key: 'interview', render: (value) => value ? <Tag>{value}</Tag> : '-' },
                { title: '投递时间', dataIndex: 'submitted_at', key: 'submitted', width: 150, render: (value) => new Date(value).toLocaleString('zh-CN') },
                {
                  title: '操作',
                  key: 'actions',
                  width: 220,
                  fixed: 'right',
                  render: (_, item) => <Space>
                    <Tooltip title="查看候选人详情"><Button type="text" icon={<EyeOutlined />} onClick={() => setDetailApplication(item)} aria-label="查看候选人详情" /></Tooltip>
                    <Tooltip title="联系候选人"><Button type="text" icon={<MessageOutlined />} onClick={() => navigate(`/enterprise/messages?thread=${item.thread_id}`)} aria-label="联系候选人" /></Tooltip>
                    {item.status === 'SUBMITTED' && <Tooltip title="开始审核"><Button type="text" icon={<CheckOutlined />} onClick={() => changeStatus(item, 'REVIEWING')} aria-label="开始审核" /></Tooltip>}
                    {!item.interview_session_id && item.resume_status === 'READY' && !['REJECTED', 'WITHDRAWN'].includes(item.status) && <Tooltip title="创建面试"><Button type="text" icon={<FileAddOutlined />} onClick={() => openInterview(item)} aria-label="创建面试" /></Tooltip>}
                    {item.interview_status === 'READY' && item.status !== 'INTERVIEW' && <Tooltip title="发送面试邀请"><Button type="text" icon={<MailOutlined />} onClick={() => sendInvitation(item)} aria-label="发送面试邀请" /></Tooltip>}
                    {item.interview_status === 'COMPLETED' && item.interview_session_id && <Tooltip title="查看评估报告"><Button type="text" icon={<FileDoneOutlined />} onClick={() => navigate(`/enterprise/interviews/${item.interview_session_id}/report`)} aria-label="查看评估报告" /></Tooltip>}
                    {!['REJECTED', 'WITHDRAWN', 'HIRED'].includes(item.status) && <Tooltip title="标记不通过"><Button type="text" danger icon={<StopOutlined />} onClick={() => confirmStatus(item, 'REJECTED')} aria-label="标记不通过" /></Tooltip>}
                    {item.interview_status === 'COMPLETED' && item.status !== 'HIRED' && <Tooltip title="标记录用"><Button type="text" icon={<CheckOutlined />} onClick={() => confirmStatus(item, 'HIRED')} aria-label="标记录用" /></Tooltip>}
                  </Space>,
                },
              ]}
            />
          </section>
        </section>
      </div>

      <Drawer
        title={detailApplication ? `${detailApplication.candidate_name} · ${detailApplication.job_title}` : '候选人详情'}
        open={detailApplication !== null}
        onClose={() => setDetailApplication(null)}
        width={680}
        extra={detailApplication ? <Tag color={statusColor[detailApplication.status]}>{statusLabel[detailApplication.status] ?? detailApplication.status}</Tag> : null}
      >
        {detailApplication && (
          <div className="application-detail-view">
            <section>
              <Typography.Title level={5}>候选人信息</Typography.Title>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="姓名">{detailApplication.candidate_name}</Descriptions.Item>
                <Descriptions.Item label="邮箱">{detailApplication.candidate_email}</Descriptions.Item>
                <Descriptions.Item label="联系电话">{detailApplication.candidate_phone || '未填写'}</Descriptions.Item>
                <Descriptions.Item label="投递岗位">{detailApplication.job_title}</Descriptions.Item>
                <Descriptions.Item label="投递时间">{new Date(detailApplication.submitted_at).toLocaleString('zh-CN')}</Descriptions.Item>
              </Descriptions>
            </section>

            {profileEntries.length > 0 && (
              <section>
                <Typography.Title level={5}>个人档案</Typography.Title>
                <Descriptions column={1} bordered size="small">
                  {profileEntries.map(([key, value]) => (
                    <Descriptions.Item key={key} label={key}>
                      <span className="application-profile-value">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</span>
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              </section>
            )}

            <section>
              <Typography.Title level={5}>求职说明</Typography.Title>
              <Typography.Paragraph className="application-cover-letter">{detailApplication.cover_letter || '候选人未填写补充说明。'}</Typography.Paragraph>
            </section>

            <section>
              <Typography.Title level={5}>投递简历快照</Typography.Title>
              <div className="application-resume-detail">
                <div><strong>{detailApplication.resume_filename}</strong><Tag color={detailApplication.resume_status === 'READY' ? 'green' : 'gold'}>{detailApplication.resume_status ?? '不可用'}</Tag></div>
                <Button icon={<DownloadOutlined />} onClick={() => downloadResume(detailApplication)}>下载简历</Button>
              </div>
            </section>

            {detailApplication.decided_at && (
              <section>
                <Typography.Title level={5}>招聘决策记录</Typography.Title>
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="决策结果">{statusLabel[detailApplication.status] ?? detailApplication.status}</Descriptions.Item>
                  <Descriptions.Item label="决策人">{detailApplication.decided_by_name || '-'}</Descriptions.Item>
                  <Descriptions.Item label="决策时间">{new Date(detailApplication.decided_at).toLocaleString('zh-CN')}</Descriptions.Item>
                  <Descriptions.Item label="内部备注">{detailApplication.decision_note || '未填写'}</Descriptions.Item>
                </Descriptions>
              </section>
            )}

            <section className="application-detail-actions">
              <Typography.Title level={5}>招聘操作</Typography.Title>
              <Space wrap>
                <Button icon={<MessageOutlined />} onClick={() => navigate(`/enterprise/messages?thread=${detailApplication.thread_id}`)}>联系候选人</Button>
                {detailApplication.status === 'SUBMITTED' && <Button icon={<CheckOutlined />} onClick={() => changeStatus(detailApplication, 'REVIEWING')}>开始审核</Button>}
                {!detailApplication.interview_session_id && detailApplication.resume_status === 'READY' && !['REJECTED', 'WITHDRAWN'].includes(detailApplication.status) && <Button type="primary" icon={<FileAddOutlined />} onClick={() => { setDetailApplication(null); openInterview(detailApplication) }}>创建面试</Button>}
                {detailApplication.interview_status === 'READY' && detailApplication.status !== 'INTERVIEW' && <Button type="primary" icon={<MailOutlined />} onClick={() => sendInvitation(detailApplication)}>发送面试邀请</Button>}
                {detailApplication.interview_status === 'COMPLETED' && detailApplication.interview_session_id && <Button icon={<FileDoneOutlined />} onClick={() => navigate(`/enterprise/interviews/${detailApplication.interview_session_id}/report`)}>查看评估报告</Button>}
                {!['REJECTED', 'WITHDRAWN', 'HIRED'].includes(detailApplication.status) && <Button danger icon={<StopOutlined />} onClick={() => confirmStatus(detailApplication, 'REJECTED')}>标记不通过</Button>}
                {detailApplication.interview_status === 'COMPLETED' && detailApplication.status !== 'HIRED' && <Button icon={<CheckOutlined />} onClick={() => confirmStatus(detailApplication, 'HIRED')}>标记录用</Button>}
              </Space>
            </section>
          </div>
        )}
      </Drawer>

      <Modal title={selected ? `为 ${selected.candidate_name} 创建面试` : '创建面试'} open={selected !== null} onCancel={() => { setSelected(null); form.resetFields() }} footer={null} destroyOnHidden>
        <Form<ApplicationInterviewCreateRequest> form={form} layout="vertical" onFinish={createInterview} initialValues={{ max_question_count: 10, question_time_limit_minutes: 10 }} requiredMark={false}>
          <Form.Item
            label="面试参考知识库"
            name="reference_knowledge_base_ids"
            rules={[{ type: 'array', max: 5, message: '最多选择 5 个知识库' }]}
          >
            <Select
              mode="multiple"
              maxTagCount="responsive"
              placeholder={referenceKnowledgeBases.length > 0 ? '选择参考知识库（可选）' : '暂无可用的非简历知识库'}
              options={referenceKnowledgeBases.map((item) => ({ value: item.id, label: `${item.name} · ${knowledgeBasePurposeLabels[item.purpose]}` }))}
            />
          </Form.Item>
          <Form.Item label="最大问题数" name="max_question_count" rules={[{ required: true }]}><InputNumber min={3} max={20} precision={0} className="full-width-control" /></Form.Item>
          <Form.Item label="每题作答时间" name="question_time_limit_minutes" rules={[{ required: true }]}>
            <Select options={[
              { value: 0, label: '不限时' },
              { value: 5, label: '5 分钟' },
              { value: 10, label: '10 分钟' },
              { value: 15, label: '15 分钟' },
              { value: 20, label: '20 分钟' },
            ]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={saving}>创建面试会话</Button>
        </Form>
      </Modal>
    </main>
  )
}

export default EnterpriseApplicationsPage
