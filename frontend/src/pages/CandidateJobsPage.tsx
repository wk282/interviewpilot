import { useEffect, useState } from 'react'
import { EyeOutlined, FileTextOutlined, MessageOutlined, PlayCircleOutlined, SendOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Descriptions, Empty, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getDocuments } from '../api/documents'
import { getKnowledgeBases } from '../api/knowledgeBases'
import {
  getCandidateApplications,
  getPublishedJobs,
  submitJobApplication,
  withdrawJobApplication,
} from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import type { DocumentItem } from '../types/document'
import type { JobApplication, JobApplicationCreateRequest, PublishedJob } from '../types/recruitment'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const applicationStatusLabel: Record<string, string> = {
  SUBMITTED: '已投递',
  REVIEWING: '审核中',
  INTERVIEW: '面试阶段',
  REJECTED: '未通过',
  WITHDRAWN: '已撤回',
  HIRED: '已录用',
}

const applicationStatusColor: Record<string, string> = {
  SUBMITTED: 'blue',
  REVIEWING: 'gold',
  INTERVIEW: 'purple',
  REJECTED: 'red',
  WITHDRAWN: 'default',
  HIRED: 'green',
}

function CandidateJobsPage() {
  const workspace = getActiveWorkspace()
  const navigate = useNavigate()
  const [form] = Form.useForm<JobApplicationCreateRequest>()
  const [jobs, setJobs] = useState<PublishedJob[]>([])
  const [applications, setApplications] = useState<JobApplication[]>([])
  const [resumes, setResumes] = useState<DocumentItem[]>([])
  const [selectedJob, setSelectedJob] = useState<PublishedJob | null>(null)
  const [viewingJob, setViewingJob] = useState<PublishedJob | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const loadData = async (showLoading = true) => {
    if (!workspace) return
    if (showLoading) setLoading(true)
    try {
      const [jobItems, applicationItems, knowledgeBases] = await Promise.all([
        getPublishedJobs(),
        getCandidateApplications(),
        getKnowledgeBases(workspace.id),
      ])
      const resumeGroups = await Promise.all(
        knowledgeBases
          .filter((item) => item.purpose === 'RESUME')
          .map((item) => getDocuments(workspace.id, item.id)),
      )
      setJobs(jobItems)
      setApplications(applicationItems)
      setResumes(resumeGroups.flat().filter((item) => item.status === 'READY'))
    } catch (error) {
      message.error(getApiErrorMessage(error, '求职数据加载失败'))
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

  const openApplication = (job: PublishedJob) => {
    setSelectedJob(job)
    form.setFieldsValue({
      job_position_id: job.id,
      resume_document_id: resumes[0]?.id,
      cover_letter: '',
      consent: false,
    })
  }

  const submit = async (values: JobApplicationCreateRequest) => {
    setSubmitting(true)
    try {
      await submitJobApplication(values)
      message.success('岗位申请已提交，简历快照正在同步给企业')
      setSelectedJob(null)
      form.resetFields()
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, '岗位申请提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const withdraw = (item: JobApplication) => {
    Modal.confirm({
      title: '撤回岗位申请？',
      content: '撤回后不能再次投递同一岗位。企业已获得的简历快照将按招聘数据保留策略处理。',
      okText: '撤回',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await withdrawJobApplication(item.id)
          message.success('岗位申请已撤回')
          await loadData()
        } catch (error) {
          message.error(getApiErrorMessage(error, '岗位申请撤回失败'))
        }
      },
    })
  }

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        <CandidateSidebar />
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">CAREER</p>
              <Typography.Title level={2}>岗位与申请</Typography.Title>
              <Typography.Paragraph type="secondary">选择简历版本投递企业岗位</Typography.Paragraph>
            </div>
          </div>

          <section className="content-panel management-panel">
            <Tabs items={[
              {
                key: 'jobs',
                label: `招聘岗位 ${jobs.length}`,
                children: jobs.length === 0 && !loading ? <Empty description="暂无开放岗位" /> : (
                  <Table<PublishedJob>
                    rowKey="id"
                    loading={loading}
                    dataSource={jobs}
                    pagination={{ pageSize: 10 }}
                    scroll={{ x: 760 }}
                    columns={[
                      { title: '岗位', dataIndex: 'title', key: 'title' },
                      { title: '企业', dataIndex: 'workspace_name', key: 'company' },
                      { title: '部门', dataIndex: 'department', key: 'department', render: (value) => value || '-' },
                      { title: '岗位说明', dataIndex: 'description', key: 'description', ellipsis: true, render: (value) => value || '-' },
                      { title: '发布时间', dataIndex: 'created_at', key: 'created', width: 130, render: (value) => new Date(value).toLocaleDateString('zh-CN') },
                      {
                        title: '操作',
                        key: 'action',
                        width: 150,
                        render: (_, item) => (
                          <Space>
                            <Button type="text" icon={<EyeOutlined />} onClick={() => setViewingJob(item)} aria-label="查看岗位详情" />
                            <Button
                              type="primary"
                              size="small"
                              icon={<SendOutlined />}
                              disabled={item.applied}
                              onClick={() => openApplication(item)}
                            >{item.applied ? '已投递' : '投递'}</Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                ),
              },
              {
                key: 'applications',
                label: `我的申请 ${applications.length}`,
                children: applications.length === 0 && !loading ? <Empty description="暂无岗位申请" /> : (
                  <Table<JobApplication>
                    rowKey="id"
                    loading={loading}
                    dataSource={applications}
                    pagination={false}
                    scroll={{ x: 780 }}
                    columns={[
                      { title: '岗位', dataIndex: 'job_title', key: 'job' },
                      { title: '企业', dataIndex: 'workspace_name', key: 'company' },
                      { title: '简历快照', dataIndex: 'resume_filename', key: 'resume', render: (value, item) => <Space><FileTextOutlined />{value}<Tag>{item.resume_status ?? '已归档'}</Tag></Space> },
                      { title: '状态', dataIndex: 'status', key: 'status', render: (value) => <Tag color={applicationStatusColor[value]}>{applicationStatusLabel[value] ?? value}</Tag> },
                      { title: '投递时间', dataIndex: 'submitted_at', key: 'submitted', width: 180, render: (value) => new Date(value).toLocaleString('zh-CN') },
                      {
                        title: '操作',
                        key: 'action',
                        width: 170,
                        render: (_, item) => <Space>
                          <Button type="text" icon={<MessageOutlined />} onClick={() => navigate(`/candidate/messages?thread=${item.thread_id}`)} aria-label="查看消息" />
                          {item.status === 'INTERVIEW' && item.interview_session_id && ['READY', 'IN_PROGRESS'].includes(item.interview_status ?? '') && <Tooltip title={item.interview_status === 'READY' ? '进入企业面试' : '继续企业面试'}><Button type="text" icon={<PlayCircleOutlined />} onClick={() => navigate(`/candidate/enterprise-interviews/${item.interview_session_id}/run`)} aria-label="进入企业面试" /></Tooltip>}
                          {['SUBMITTED', 'REVIEWING'].includes(item.status) && <Button type="text" danger icon={<StopOutlined />} onClick={() => withdraw(item)} aria-label="撤回申请" />}
                        </Space>,
                      },
                    ]}
                  />
                ),
              },
            ]} />
          </section>
        </section>
      </div>

      <Modal
        title={viewingJob?.title ?? '岗位详情'}
        open={viewingJob !== null}
        onCancel={() => setViewingJob(null)}
        width={760}
        footer={viewingJob ? [
          <Button key="close" onClick={() => setViewingJob(null)}>关闭</Button>,
          <Button
            key="apply"
            type="primary"
            icon={<SendOutlined />}
            disabled={viewingJob.applied}
            onClick={() => { const job = viewingJob; setViewingJob(null); openApplication(job) }}
          >{viewingJob.applied ? '已投递' : '投递该岗位'}</Button>,
        ] : null}
        destroyOnHidden
      >
        {viewingJob && (
          <div className="job-detail-view">
            <Descriptions column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="企业">{viewingJob.workspace_name}</Descriptions.Item>
              <Descriptions.Item label="部门">{viewingJob.department || '-'}</Descriptions.Item>
              <Descriptions.Item label="发布时间">{new Date(viewingJob.created_at).toLocaleDateString('zh-CN')}</Descriptions.Item>
            </Descriptions>
            <section>
              <Typography.Title level={5}>岗位说明</Typography.Title>
              <Typography.Paragraph className="job-description">{viewingJob.description || '暂无岗位说明'}</Typography.Paragraph>
            </section>
            {Object.keys(viewingJob.requirements).length > 0 && (
              <section>
                <Typography.Title level={5}>岗位要求</Typography.Title>
                <Descriptions column={1} size="small" bordered>
                  {Object.entries(viewingJob.requirements).map(([key, value]) => (
                    <Descriptions.Item key={key} label={key}>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</Descriptions.Item>
                  ))}
                </Descriptions>
              </section>
            )}
          </div>
        )}
      </Modal>

      <Modal title={selectedJob ? `投递 ${selectedJob.title}` : '投递岗位'} open={selectedJob !== null} onCancel={() => { setSelectedJob(null); form.resetFields() }} footer={null} destroyOnHidden>
        {resumes.length === 0 && (
          <Alert
            className="resume-alert"
            type="warning"
            showIcon
            message="没有可投递的简历"
            description="请先上传简历并等待解析完成。"
            action={<Button size="small" onClick={() => navigate('/candidate/resumes')}>上传简历</Button>}
          />
        )}
        <Form<JobApplicationCreateRequest> form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="job_position_id" hidden><Input /></Form.Item>
          <Form.Item label="简历版本" name="resume_document_id" rules={[{ required: true, message: '请选择简历' }]}>
            <Select placeholder="选择已解析完成的简历" options={resumes.map((item) => ({ value: item.id, label: item.original_filename }))} />
          </Form.Item>
          <Form.Item label="补充说明" name="cover_letter"><Input.TextArea maxLength={5000} showCount autoSize={{ minRows: 4, maxRows: 8 }} placeholder="可填写与岗位相关的经验或求职说明" /></Form.Item>
          <Form.Item name="consent" valuePropName="checked" rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error('请确认简历授权')) }]}>
            <Checkbox>我同意将所选简历生成不可变快照并提供给该企业用于本次招聘</Checkbox>
          </Form.Item>
          <Button type="primary" htmlType="submit" block icon={<SendOutlined />} loading={submitting} disabled={resumes.length === 0}>确认投递</Button>
        </Form>
      </Modal>
    </main>
  )
}

export default CandidateJobsPage
