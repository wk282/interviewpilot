import { useEffect, useState } from 'react'
import { CopyOutlined, DeleteOutlined, EditOutlined, EyeOutlined, FileAddOutlined, FileDoneOutlined, MailOutlined, PlayCircleOutlined, PlusOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Input, InputNumber, List, Modal, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  cancelInterviewPlan,
  createCandidate,
  createInterviewSession,
  createPosition,
  deleteCandidate,
  deleteInterviewSession,
  deletePosition,
  generateInterviewPlan,
  getCandidates,
  getInterviewPlan,
  getInterviewObservability,
  getInterviewSessions,
  getPositions,
  updateCandidate,
  updatePosition,
} from '../api/interviews'
import { getDocuments } from '../api/documents'
import { getKnowledgeBases } from '../api/knowledgeBases'
import {
  createInterviewInvitation,
  getInterviewInvitations,
  revokeInterviewInvitation,
} from '../api/interviewInvitations'
import { sendPlatformInterviewInvitation } from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import AgentExecutionTracePanel from '../components/AgentExecutionTracePanel'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type {
  CandidateProfile,
  CandidateProfileCreateRequest,
  InterviewSession,
  InterviewSessionCreateRequest,
  InterviewPlan,
  InterviewObservability,
  InterviewQuestion,
  JobPosition,
  JobPositionCreateRequest,
} from '../types/interview'
import type { KnowledgeBase, KnowledgeBasePurpose } from '../types/knowledgeBase'
import type { DocumentItem } from '../types/document'
import type {
  InterviewInvitation,
  InterviewInvitationCreated,
  InterviewInvitationCreateRequest,
} from '../types/interviewInvitation'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

type ManagementTab = 'interviews' | 'positions' | 'candidates'
type PositionFormValues = Omit<JobPositionCreateRequest, 'status'> & {
  status: 'DRAFT' | 'ACTIVE' | 'CLOSED'
}
type CandidateFormValues = CandidateProfileCreateRequest & {
  status: 'ACTIVE' | 'ARCHIVED'
}

const statusColors: Record<string, string> = {
  ACTIVE: 'green',
  READY: 'blue',
  IN_PROGRESS: 'gold',
  COMPLETED: 'green',
  FAILED: 'red',
  CANCELLED: 'default',
  CLOSED: 'default',
  PENDING: 'default',
  OPENED: 'cyan',
  VERIFIED: 'blue',
  STARTED: 'gold',
  EXPIRED: 'default',
  REVOKED: 'red',
}

const knowledgeBasePurposeLabels: Record<KnowledgeBasePurpose, string> = {
  RESUME: '简历',
  PERSONAL_LEARNING: '个人学习资料',
  ENTERPRISE_QUESTION_BANK: '企业题库',
  JOB_SPECIFIC: '岗位专项',
  SCORING_RUBRIC: '评分标准',
  TECHNICAL_STANDARD: '技术规范',
}

const ACTIVE_INVITATION_STATUSES = new Set(['PENDING', 'OPENED', 'VERIFIED', 'STARTED'])

const observabilityStageLabels: Record<string, string> = {
  TOTAL: '整轮链路',
  CRITIC: 'Answer Critic',
  PLAN_REVISER: 'Plan Reviser',
  EMBEDDING: 'Embedding',
  KNOWLEDGE_RETRIEVAL: '知识库检索',
  RERANKER: 'Reranker',
  RETRIEVAL_GRADER: 'Retrieval Grader',
  QUERY_REWRITE: '查询改写',
  WEB_SEARCH: '联网搜索',
  CRAG: 'CRAG 总计',
  CONDUCTOR: 'Conductor',
  AI_QUEUE: 'AI 并发排队',
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function formatLatency(value: unknown): string | null {
  return typeof value === 'number' ? `${(value / 1000).toFixed(2)} 秒` : null
}

function questionPerformance(question: InterviewQuestion) {
  const observability = asRecord(question.decision_metadata.observability)
  const crag = asRecord(observability.crag)
  const conductor = asRecord(observability.conductor)
  const usage = asRecord(conductor.usage)
  const agentGraph = asRecord(observability.agent_graph)
  const traceSource = Array.isArray(agentGraph.trace)
    ? agentGraph.trace
    : observability.feedback_trace
  const feedbackTrace = Array.isArray(traceSource)
    ? traceSource.map(asRecord)
    : []
  const critic = feedbackTrace.find((item) => ['answer_critic', 'answer_critic_agent'].includes(String(item.node))) ?? {}
  const reviser = feedbackTrace.find((item) => ['plan_reviser', 'plan_reviser_agent'].includes(String(item.node))) ?? {}
  return {
    total: formatLatency(observability.activation_total_latency_ms ?? observability.total_latency_ms),
    crag: formatLatency(crag.latency_ms),
    embedding: formatLatency(crag.embedding_latency_ms),
    retrieval: formatLatency(crag.knowledge_base_retrieval_latency_ms),
    reranker: formatLatency(crag.reranker_latency_ms),
    critic: formatLatency(critic.latency_ms),
    reviser: formatLatency(reviser.latency_ms),
    conductor: formatLatency(conductor.latency_ms),
    tokens: typeof usage.total_tokens === 'number' ? usage.total_tokens : null,
    source: typeof conductor.source === 'string' ? conductor.source : null,
  }
}

function InterviewManagementPage() {
  const navigate = useNavigate()
  const workspace = getActiveWorkspace()
  const personal = workspace?.type === 'PERSONAL'
  const canWrite = personal || ['OWNER', 'ADMIN', 'HR'].includes(workspace?.role ?? '')
  const canPlan = personal || ['OWNER', 'ADMIN', 'HR', 'INTERVIEWER'].includes(workspace?.role ?? '')
  const [positionForm] = Form.useForm<PositionFormValues>()
  const [candidateForm] = Form.useForm<CandidateFormValues>()
  const [interviewForm] = Form.useForm<InterviewSessionCreateRequest>()
  const [invitationForm] = Form.useForm<InterviewInvitationCreateRequest>()
  const [activeTab, setActiveTab] = useState<ManagementTab>('interviews')
  const [positions, setPositions] = useState<JobPosition[]>([])
  const [candidates, setCandidates] = useState<CandidateProfile[]>([])
  const [interviews, setInterviews] = useState<InterviewSession[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [resumeDocuments, setResumeDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [modal, setModal] = useState<ManagementTab | null>(null)
  const [editingPosition, setEditingPosition] = useState<JobPosition | null>(null)
  const [editingCandidate, setEditingCandidate] = useState<CandidateProfile | null>(null)
  const [generatingId, setGeneratingId] = useState<string | null>(null)
  const [plan, setPlan] = useState<InterviewPlan | null>(null)
  const [observabilitySummary, setObservabilitySummary] = useState<InterviewObservability | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [invitationInterview, setInvitationInterview] = useState<InterviewSession | null>(null)
  const [invitations, setInvitations] = useState<InterviewInvitation[]>([])
  const [createdInvitation, setCreatedInvitation] = useState<InterviewInvitationCreated | null>(null)
  const [invitationLoading, setInvitationLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const loadData = async () => {
    if (!workspace) return
    setLoading(true)
    try {
      const [positionItems, candidateItems, interviewItems, kbItems] = await Promise.all([
        getPositions(workspace.id),
        getCandidates(workspace.id),
        getInterviewSessions(workspace.id),
        getKnowledgeBases(workspace.id),
      ])
      setPositions(positionItems)
      setCandidates(candidateItems)
      setInterviews(interviewItems)
      setKnowledgeBases(kbItems)
      const resumeDocumentGroups = await Promise.all(
        kbItems
          .filter((item) => item.purpose === 'RESUME')
          .map((item) => getDocuments(workspace.id, item.id)),
      )
      setResumeDocuments(resumeDocumentGroups.flat())
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试数据加载失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadData() }, [workspace?.id])

  const hasPlanningSession = interviews.some((item) => item.status === 'PLANNING')
  const hasActiveInterview = interviews.some((item) => item.status === 'IN_PROGRESS')
  useEffect(() => {
    if ((!hasPlanningSession && !hasActiveInterview) || !workspace) return
    const timer = window.setInterval(() => {
      getInterviewSessions(workspace.id).then(setInterviews).catch(() => undefined)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [hasPlanningSession, hasActiveInterview, workspace?.id])

  const closeModal = () => {
    setModal(null)
    setEditingPosition(null)
    setEditingCandidate(null)
    positionForm.resetFields()
    candidateForm.resetFields()
    interviewForm.resetFields()
  }

  const openCreateModal = () => {
    setEditingPosition(null)
    setEditingCandidate(null)
    positionForm.resetFields()
    candidateForm.resetFields()
    interviewForm.resetFields()
    setModal(activeTab)
  }

  const openPositionEditor = (item: JobPosition) => {
    setEditingPosition(item)
    positionForm.setFieldsValue({
      title: item.title,
      department: item.department ?? undefined,
      description: item.description ?? undefined,
      knowledge_base_id: item.knowledge_base_id ?? undefined,
      status: item.status,
    })
    setModal('positions')
  }

  const openCandidateEditor = (item: CandidateProfile) => {
    setEditingCandidate(item)
    candidateForm.setFieldsValue({
      full_name: item.full_name,
      email: item.email ?? undefined,
      phone: item.phone ?? undefined,
      resume_document_id: item.resume_document_id ?? undefined,
      status: item.status,
    })
    setModal('candidates')
  }

  const submitPosition = async (values: PositionFormValues) => {
    if (!workspace) return
    setSaving(true)
    try {
      if (editingPosition) {
        await updatePosition(workspace.id, editingPosition.id, values)
        message.success('岗位已更新')
      } else {
        await createPosition(workspace.id, {
          ...values,
          status: values.status === 'CLOSED' ? 'DRAFT' : values.status,
        })
        message.success('岗位已创建')
      }
      closeModal()
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, editingPosition ? '岗位更新失败' : '岗位创建失败'))
    } finally {
      setSaving(false)
    }
  }

  const submitCandidate = async (values: CandidateFormValues) => {
    if (!workspace) return
    setSaving(true)
    try {
      if (editingCandidate) {
        await updateCandidate(workspace.id, editingCandidate.id, values)
        message.success(personal ? '个人档案已更新' : '候选人已更新')
      } else {
        await createCandidate(workspace.id, {
          full_name: values.full_name,
          email: values.email,
          phone: values.phone,
          resume_document_id: values.resume_document_id,
        })
        message.success(personal ? '个人档案已创建' : '候选人已创建')
      }
      closeModal()
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, editingCandidate ? '档案更新失败' : '候选人创建失败'))
    } finally {
      setSaving(false)
    }
  }

  const submitInterview = async (values: InterviewSessionCreateRequest) => {
    if (!workspace) return
    setSaving(true)
    try {
      await createInterviewSession(workspace.id, values)
      message.success(personal ? '模拟面试已创建' : '企业面试已创建')
      closeModal()
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试创建失败'))
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = (title: string, action: () => Promise<void>, content = '此操作不可恢复。已有面试记录的岗位或候选人不能删除。') => {
    Modal.confirm({
      title,
      content,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await action()
          message.success('已删除')
          await loadData()
        } catch (error) {
          message.error(getApiErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  const generatePlan = async (item: InterviewSession) => {
    if (!workspace) return
    setGeneratingId(item.id)
    try {
      await generateInterviewPlan(workspace.id, item.id)
      message.success('面试计划任务已提交')
      await loadData()
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试计划生成失败'))
    } finally {
      setGeneratingId(null)
    }
  }

  const cancelPlanGeneration = (item: InterviewSession) => {
    if (!workspace) return
    Modal.confirm({
      title: '取消生成面试计划？',
      content: '取消后当前计划会标记为失败，可以重新生成。',
      okText: '取消生成',
      okButtonProps: { danger: true },
      cancelText: '继续等待',
      onOk: async () => {
        try {
          await cancelInterviewPlan(workspace.id, item.id)
          message.success('已取消计划生成')
          await loadData()
        } catch (error) {
          message.error(getApiErrorMessage(error, '取消计划失败'))
        }
      },
    })
  }

  const viewPlan = async (item: InterviewSession) => {
    if (!workspace) return
    setPlanLoading(true)
    try {
      const [interviewPlan, observability] = await Promise.all([
        getInterviewPlan(workspace.id, item.id),
        getInterviewObservability(workspace.id, item.id),
      ])
      setPlan(interviewPlan)
      setObservabilitySummary(observability)
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试计划加载失败'))
    } finally {
      setPlanLoading(false)
    }
  }

  const openInvitationManager = async (item: InterviewSession) => {
    if (!workspace) return
    const candidate = candidates.find((candidateItem) => candidateItem.id === item.candidate_profile_id)
    setInvitationInterview(item)
    setCreatedInvitation(null)
    invitationForm.setFieldsValue({
      email: candidate?.email ?? '',
      expires_in_days: 7,
      max_access_count: 5,
    })
    setInvitationLoading(true)
    try {
      setInvitations(await getInterviewInvitations(workspace.id, item.id))
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试邀请加载失败'))
    } finally {
      setInvitationLoading(false)
    }
  }

  const sendAccountInvitation = async () => {
    if (!workspace || !invitationInterview?.application_id) return
    setInvitationLoading(true)
    try {
      await sendPlatformInterviewInvitation(
        workspace.id,
        invitationInterview.application_id,
        invitationInterview.id,
      )
      message.success('面试邀请已发送到候选人消息中心')
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试邀请发送失败'))
    } finally {
      setInvitationLoading(false)
    }
  }

  const submitInvitation = async (values: InterviewInvitationCreateRequest) => {
    if (!workspace || !invitationInterview) return
    setInvitationLoading(true)
    try {
      const result = await createInterviewInvitation(
        workspace.id,
        invitationInterview.id,
        values,
      )
      setCreatedInvitation(result)
      setInvitations(await getInterviewInvitations(workspace.id, invitationInterview.id))
      message.success('候选人邀请已创建')
    } catch (error) {
      message.error(getApiErrorMessage(error, '候选人邀请创建失败'))
    } finally {
      setInvitationLoading(false)
    }
  }

  const revokeInvitation = (item: InterviewInvitation) => {
    if (!workspace || !invitationInterview) return
    Modal.confirm({
      title: '撤销该候选人邀请？',
      content: '撤销后，已发出的链接和候选人临时凭证都会失效。',
      okText: '撤销',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await revokeInterviewInvitation(workspace.id, invitationInterview.id, item.id)
          setInvitations(await getInterviewInvitations(workspace.id, invitationInterview.id))
          message.success('邀请已撤销')
        } catch (error) {
          message.error(getApiErrorMessage(error, '邀请撤销失败'))
        }
      },
    })
  }

  const copyInvitationValue = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value)
      message.success(`${label}已复制`)
    } catch {
      message.error(`无法复制${label}`)
    }
  }

  const createButtonLabel = activeTab === 'positions'
    ? '新建岗位'
    : activeTab === 'candidates'
      ? (personal ? '创建个人档案' : '添加候选人')
      : (personal ? '创建模拟面试' : '创建面试')

  const positionKnowledgeBases = knowledgeBases.filter((item) => item.purpose === 'JOB_SPECIFIC')
  const referenceKnowledgeBases = knowledgeBases.filter((item) => item.purpose !== 'RESUME')
  const normalizedSearchQuery = searchQuery.trim().toLowerCase()
  const filteredInterviews = interviews.filter((item) => (
    !normalizedSearchQuery
    || [item.job_title, item.candidate_name, item.status, item.mode]
      .some((value) => value?.toLowerCase().includes(normalizedSearchQuery))
  ))
  const filteredPositions = positions.filter((item) => (
    !normalizedSearchQuery
    || [item.title, item.department, item.status]
      .some((value) => value?.toLowerCase().includes(normalizedSearchQuery))
  ))
  const filteredCandidates = candidates.filter((item) => (
    !normalizedSearchQuery
    || [item.full_name, item.email, item.source, item.status]
      .some((value) => value?.toLowerCase().includes(normalizedSearchQuery))
  ))

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        {personal ? <CandidateSidebar /> : <EnterpriseSidebar workspace={workspace} />}
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">INTERVIEWS</p>
              <Typography.Title level={2}>{personal ? '模拟面试' : '面试管理'}</Typography.Title>
              <Typography.Paragraph type="secondary">{interviews.length} 场面试 · {positions.length} 个岗位 · {candidates.length} 名候选人</Typography.Paragraph>
            </div>
            {canWrite && !(activeTab === 'interviews' && !personal) && (
              <Button
                type="primary"
                size="large"
                icon={<PlusOutlined />}
                disabled={activeTab === 'interviews' && (positions.length === 0 || candidates.length === 0)}
                onClick={openCreateModal}
              >{createButtonLabel}</Button>
            )}
          </div>

          <section className="content-panel management-panel">
            <div className="list-toolbar">
              <Input allowClear prefix={<SearchOutlined />} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索岗位、候选人或状态" className="list-search" />
            </div>
            <Tabs
              activeKey={activeTab}
              onChange={(key) => setActiveTab(key as ManagementTab)}
              items={[
                { key: 'interviews', label: '面试会话', children: filteredInterviews.length === 0 && !loading ? <Empty description="暂无面试" /> : <Table<InterviewSession> rowKey="id" loading={loading} dataSource={filteredInterviews} pagination={false} scroll={{ x: 760 }} columns={[
                  { title: '岗位', dataIndex: 'job_title', key: 'job' },
                  { title: '候选人', dataIndex: 'candidate_name', key: 'candidate' },
                  { title: '模式', dataIndex: 'mode', key: 'mode', render: (value) => <Tag>{value === 'MOCK' ? '模拟面试' : '企业面试'}</Tag> },
                  { title: '状态', dataIndex: 'status', key: 'status', render: (value) => <Tag color={statusColors[value]}>{value}</Tag> },
                  { title: '进度', key: 'progress', width: 120, render: (_: unknown, item: InterviewSession) => item.status === 'IN_PROGRESS' ? `${item.current_question_order} / ${Number(item.configuration.max_question_count ?? 10)}` : '-' },
                  { title: '创建时间', dataIndex: 'created_at', key: 'created', render: (value) => new Date(value).toLocaleString('zh-CN') },
                  { title: '操作', key: 'actions', width: 190, render: (_: unknown, item: InterviewSession) => <Space>
                    {canPlan && item.status === 'DRAFT' && <Tooltip title="生成面试计划"><Button type="text" icon={<FileAddOutlined />} loading={generatingId === item.id} onClick={() => generatePlan(item)} aria-label="生成面试计划" /></Tooltip>}
                    {canPlan && item.status === 'FAILED' && <Button size="small" icon={<FileAddOutlined />} loading={generatingId === item.id} onClick={() => generatePlan(item)}>重新生成计划</Button>}
                    {canPlan && item.status === 'PLANNING' && <Button type="text" danger icon={<StopOutlined />} onClick={() => cancelPlanGeneration(item)}>取消生成</Button>}
                    {personal && canPlan && ['READY', 'IN_PROGRESS'].includes(item.status) && <Tooltip title={item.status === 'READY' ? '开始面试' : '继续面试'}><Button type="text" icon={<PlayCircleOutlined />} onClick={() => navigate(`/candidate/interviews/${item.id}/run`)} aria-label={item.status === 'READY' ? '开始面试' : '继续面试'} /></Tooltip>}
                    {item.status === 'COMPLETED' && <Button type="text" icon={<FileDoneOutlined />} onClick={() => navigate(`${personal ? '/candidate' : '/enterprise'}/interviews/${item.id}/report`)} aria-label="查看评估报告" />}
                    {['READY', 'IN_PROGRESS', 'COMPLETED', 'FAILED'].includes(item.status) && <Button type="text" icon={<EyeOutlined />} loading={planLoading} onClick={() => viewPlan(item)} aria-label="查看面试计划" />}
                    {!personal && canWrite && ['READY', 'IN_PROGRESS', 'COMPLETED'].includes(item.status) && <Tooltip title={item.application_id ? '发送面试邀请' : '管理候选人邀请'}><Button type="text" icon={<MailOutlined />} onClick={() => openInvitationManager(item)} aria-label={item.application_id ? '发送面试邀请' : '管理候选人邀请'} /></Tooltip>}
                    {canWrite && <Tooltip title="删除面试"><Button type="text" danger icon={<DeleteOutlined />} onClick={() => confirmDelete(`删除“${item.job_title}”面试？`, () => deleteInterviewSession(workspace!.id, item.id), ['PLANNING', 'IN_PROGRESS'].includes(item.status) ? '该面试正在处理或作答中，删除后会立即终止，并清理计划、题目、回答、评估及邀请记录。' : '将同时清理该面试的计划、题目、回答、评估及邀请记录，此操作不可恢复。')} aria-label="删除面试" /></Tooltip>}
                  </Space> },
                ]} /> },
                { key: 'positions', label: '岗位', children: filteredPositions.length === 0 && !loading ? <Empty description="暂无岗位" /> : <Table<JobPosition> rowKey="id" loading={loading} dataSource={filteredPositions} pagination={false} columns={[
                  { title: '岗位名称', dataIndex: 'title', key: 'title' },
                  { title: '部门', dataIndex: 'department', key: 'department', render: (value) => value || '-' },
                  { title: '状态', dataIndex: 'status', key: 'status', render: (value) => <Tag color={statusColors[value]}>{value}</Tag> },
                  { title: '创建时间', dataIndex: 'created_at', key: 'created', render: (value) => new Date(value).toLocaleDateString('zh-CN') },
                  ...(canWrite ? [{ title: '操作', key: 'actions', width: 110, render: (_: unknown, item: JobPosition) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openPositionEditor(item)} aria-label="编辑岗位" /><Button type="text" danger icon={<DeleteOutlined />} onClick={() => confirmDelete(`删除岗位“${item.title}”？`, () => deletePosition(workspace!.id, item.id))} aria-label="删除岗位" /></Space> }] : []),
                ]} /> },
                { key: 'candidates', label: personal ? '个人档案' : '候选人', children: filteredCandidates.length === 0 && !loading ? <Empty description={personal ? '暂无个人档案' : '暂无候选人'} /> : <Table<CandidateProfile> rowKey="id" loading={loading} dataSource={filteredCandidates} pagination={false} columns={[
                  { title: '姓名', dataIndex: 'full_name', key: 'name' },
                  { title: '邮箱', dataIndex: 'email', key: 'email', render: (value) => value || '-' },
                  { title: '来源', dataIndex: 'source', key: 'source', render: (value) => <Tag>{value === 'PERSONAL_ACCOUNT' ? '个人账号' : '企业录入'}</Tag> },
                  { title: '简历', key: 'resume', render: (_: unknown, item: CandidateProfile) => resumeDocuments.find((document) => document.id === item.resume_document_id)?.original_filename ?? '未选择' },
                  { title: '状态', dataIndex: 'status', key: 'status', render: (value) => <Tag color={statusColors[value]}>{value}</Tag> },
                  ...(canWrite ? [{ title: '操作', key: 'actions', width: 110, render: (_: unknown, item: CandidateProfile) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openCandidateEditor(item)} aria-label="编辑档案" /><Button type="text" danger icon={<DeleteOutlined />} onClick={() => confirmDelete(`删除“${item.full_name}”？`, () => deleteCandidate(workspace!.id, item.id))} aria-label="删除候选人" /></Space> }] : []),
                ]} /> },
              ]}
            />
          </section>
        </section>
      </div>

      <Modal title={editingPosition ? '编辑岗位' : '新建岗位'} open={modal === 'positions'} onCancel={closeModal} footer={null} destroyOnHidden>
        <Form<PositionFormValues> form={positionForm} layout="vertical" onFinish={submitPosition} initialValues={{ status: 'ACTIVE' }} requiredMark={false}>
          <Form.Item label="岗位名称" name="title" rules={[{ required: true, whitespace: true, message: '请输入岗位名称' }]}><Input placeholder="例如：Java 后端工程师" /></Form.Item>
          <Form.Item label="部门" name="department"><Input placeholder="例如：研发部" /></Form.Item>
          <Form.Item label="岗位知识库" name="knowledge_base_id"><Select allowClear placeholder="选择 JOB_SPECIFIC 知识库" options={positionKnowledgeBases.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          <Form.Item label="岗位描述" name="description"><Input.TextArea autoSize={{ minRows: 4, maxRows: 8 }} /></Form.Item>
          <Form.Item label="状态" name="status"><Select options={[{ value: 'ACTIVE', label: '启用' }, { value: 'DRAFT', label: '草稿' }, ...(editingPosition ? [{ value: 'CLOSED', label: '关闭' }] : [])]} /></Form.Item>
          <Button type="primary" htmlType="submit" block loading={saving}>{editingPosition ? '保存修改' : '创建岗位'}</Button>
        </Form>
      </Modal>

      <Modal title={editingCandidate ? (personal ? '编辑个人档案' : '编辑候选人') : (personal ? '创建个人档案' : '添加候选人')} open={modal === 'candidates'} onCancel={closeModal} footer={null} destroyOnHidden>
        <Form<CandidateFormValues> form={candidateForm} layout="vertical" onFinish={submitCandidate} initialValues={{ status: 'ACTIVE' }} requiredMark={false}>
          {!resumeDocuments.some((item) => item.status === 'READY') && (
            <Alert
              className="resume-alert"
              type="warning"
              showIcon
              message={personal ? '请先上传并完成简历解析' : '请先在 RESUME 知识库中上传候选人简历'}
              action={personal ? <Button size="small" onClick={() => navigate('/candidate/resumes')}>上传简历</Button> : undefined}
            />
          )}
          <Form.Item label="姓名" name="full_name" rules={[{ required: true, whitespace: true, message: '请输入姓名' }]}><Input /></Form.Item>
          <Form.Item label="邮箱" name="email" rules={[{ type: 'email', message: '请输入有效邮箱' }]}><Input /></Form.Item>
          <Form.Item label="联系电话" name="phone"><Input /></Form.Item>
          <Form.Item
            label="简历"
            name="resume_document_id"
            rules={[{ required: true, message: '请选择已解析完成的简历' }]}
          >
            <Select
              placeholder={resumeDocuments.some((item) => item.status === 'READY') ? '选择简历文件' : '请先上传并等待简历解析完成'}
              options={resumeDocuments
                .filter((item) => item.status === 'READY')
                .map((item) => ({ value: item.id, label: item.original_filename }))}
            />
          </Form.Item>
          {editingCandidate && <Form.Item label="状态" name="status"><Select options={[{ value: 'ACTIVE', label: '启用' }, { value: 'ARCHIVED', label: '归档' }]} /></Form.Item>}
          <Button type="primary" htmlType="submit" block loading={saving}>{editingCandidate ? '保存修改' : '保存档案'}</Button>
        </Form>
      </Modal>

      <Modal title={personal ? '创建模拟面试' : '创建企业面试'} open={modal === 'interviews'} onCancel={closeModal} footer={null} destroyOnHidden>
        <Form<InterviewSessionCreateRequest> form={interviewForm} layout="vertical" onFinish={submitInterview} initialValues={{ max_question_count: 10, question_time_limit_minutes: 10 }} requiredMark={false}>
          <Form.Item label="岗位" name="job_position_id" rules={[{ required: true, message: '请选择岗位' }]}><Select options={positions.filter((item) => item.status !== 'CLOSED').map((item) => ({ value: item.id, label: item.title }))} /></Form.Item>
          <Form.Item label="候选人" name="candidate_profile_id" rules={[{ required: true, message: '请选择候选人' }]}><Select options={candidates.filter((item) => item.status === 'ACTIVE').map((item) => ({ value: item.id, label: item.full_name }))} /></Form.Item>
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
          <Form.Item label="最大问题数" name="max_question_count" rules={[{ required: true, message: '请设置问题数' }]}>
            <InputNumber min={3} max={20} precision={0} className="full-width-control" />
          </Form.Item>
          <Form.Item label="每题作答时间" name="question_time_limit_minutes" rules={[{ required: true, message: '请选择作答时间' }]}>
            <Select options={[
              { value: 0, label: '不限时' },
              { value: 5, label: '5 分钟' },
              { value: 10, label: '10 分钟' },
              { value: 15, label: '15 分钟' },
              { value: 20, label: '20 分钟' },
            ]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={saving}>创建面试</Button>
        </Form>
      </Modal>

      <Modal
        title={`面试蓝图${plan ? ` v${plan.version}` : ''}`}
        open={plan !== null}
        onCancel={() => { setPlan(null); setObservabilitySummary(null) }}
        footer={null}
        width={980}
        destroyOnHidden
      >
        {plan && <Space direction="vertical" size="large" className="plan-view">
          {plan.error_message && <Alert type="error" showIcon message="计划生成失败" description={plan.error_message} />}
          {observabilitySummary && observabilitySummary.measured_turn_count > 0 && (
            <section>
              <Typography.Title level={5}>AI 性能汇总</Typography.Title>
              <div className="observability-summary-grid">
                <div><span>已测题目</span><strong>{observabilitySummary.measured_turn_count}</strong></div>
                <div><span>平均总耗时</span><strong>{formatLatency(observabilitySummary.stage_metrics.TOTAL?.average_latency_ms) ?? '-'}</strong></div>
                <div><span>P95 总耗时</span><strong>{formatLatency(observabilitySummary.stage_metrics.TOTAL?.p95_latency_ms) ?? '-'}</strong></div>
                <div><span>Token 总量</span><strong>{observabilitySummary.total_tokens}</strong></div>
              </div>
              <Space wrap className="observability-summary-tags">
                {observabilitySummary.bottleneck_stage && <Tag color="volcano">主要瓶颈 {observabilityStageLabels[observabilitySummary.bottleneck_stage] ?? observabilitySummary.bottleneck_stage}</Tag>}
                <Tag color={observabilitySummary.fallback_turn_count > 0 ? 'gold' : 'green'}>
                  降级题目 {observabilitySummary.fallback_turn_count} / {observabilitySummary.measured_turn_count}
                </Tag>
                {observabilitySummary.route_counts.query_rewrite > 0 && <Tag>查询改写 {observabilitySummary.route_counts.query_rewrite} 次</Tag>}
                {observabilitySummary.route_counts.web_search > 0 && <Tag>联网搜索 {observabilitySummary.route_counts.web_search} 次</Tag>}
                {observabilitySummary.route_counts.grader_local_fast_path > 0 && <Tag color="cyan">本地快速判定 {observabilitySummary.route_counts.grader_local_fast_path} 次</Tag>}
                {observabilitySummary.route_counts.checkpoint_resume > 0 && <Tag color="purple">断点恢复 {observabilitySummary.route_counts.checkpoint_resume} 次</Tag>}
                {observabilitySummary.route_counts.paused_for_answer > 0 && <Tag>等待回答 {observabilitySummary.route_counts.paused_for_answer} 次</Tag>}
                {observabilitySummary.route_counts.ai_queue_wait > 0 && <Tag color="gold">并发排队 {observabilitySummary.route_counts.ai_queue_wait} 次</Tag>}
              </Space>
              <List
                size="small"
                dataSource={Object.entries(observabilitySummary.stage_metrics).filter(([stage]) => stage !== 'TOTAL')}
                renderItem={([stage, metrics]) => (
                  <List.Item>
                    <span>{observabilityStageLabels[stage] ?? stage}</span>
                    <Typography.Text type="secondary">
                      平均 {formatLatency(metrics.average_latency_ms)} · P95 {formatLatency(metrics.p95_latency_ms)} · {metrics.sample_count} 次
                    </Typography.Text>
                  </List.Item>
                )}
              />
            </section>
          )}
          {!personal && <AgentExecutionTracePanel questions={plan.questions} />}
          <section>
            <Typography.Title level={5}>面试目标</Typography.Title>
            <ul>{plan.objectives.map((objective, index) => <li key={index}>{objective}</li>)}</ul>
          </section>
          <section>
            <Typography.Title level={5}>能力覆盖</Typography.Title>
            <List
              dataSource={plan.sections}
              renderItem={(section, index) => (
                <List.Item>
                  <div className="plan-question">
                    <div className="plan-question-heading">
                      <strong>{index + 1}. {String(section.name ?? section.title ?? '能力主题')}</strong>
                      <Space wrap>
                        {section.difficulty ? <Tag color="blue">{String(section.difficulty)}</Tag> : null}
                        {section.target_question_count ? <Tag>{String(section.target_question_count)} 题目标</Tag> : null}
                      </Space>
                    </div>
                    {Array.isArray(section.competencies) && <Space wrap>{section.competencies.map((item, itemIndex) => <Tag key={itemIndex}>{String(item)}</Tag>)}</Space>}
                  </div>
                </List.Item>
              )}
            />
          </section>
          {plan.questions.length > 0 && (
            <section>
              <Typography.Title level={5}>已生成题目与 AI 耗时</Typography.Title>
              <List
                dataSource={plan.questions}
                renderItem={(question) => {
                  const performance = questionPerformance(question)
                  return (
                    <List.Item>
                      <div className="plan-question">
                        <div className="plan-question-heading">
                          <strong>{question.order_no}. {question.competency || question.question_type}</strong>
                          <Space wrap>
                            <Tag>{question.difficulty}</Tag>
                            {performance.total && <Tag color="blue">总耗时 {performance.total}</Tag>}
                          </Space>
                        </div>
                        <p>{question.content}</p>
                        <Space wrap>
                          {performance.critic && <Tag>Critic {performance.critic}</Tag>}
                          {performance.reviser && <Tag>Reviser {performance.reviser}</Tag>}
                          {performance.crag && <Tag>CRAG {performance.crag}</Tag>}
                          {performance.embedding && <Tag>Embedding {performance.embedding}</Tag>}
                          {performance.retrieval && <Tag>知识库检索 {performance.retrieval}</Tag>}
                          {performance.reranker && <Tag>Reranker {performance.reranker}</Tag>}
                          {performance.conductor && <Tag>Conductor {performance.conductor}</Tag>}
                          {performance.tokens !== null && <Tag>{performance.tokens} Tokens</Tag>}
                          {performance.source && performance.source !== 'model' && <Tag color="gold">{performance.source}</Tag>}
                        </Space>
                      </div>
                    </List.Item>
                  )
                }}
              />
            </section>
          )}
        </Space>}
      </Modal>

      <Modal
        title={`候选人邀请${invitationInterview ? ` · ${invitationInterview.candidate_name}` : ''}`}
        open={invitationInterview !== null}
        onCancel={() => {
          setInvitationInterview(null)
          setCreatedInvitation(null)
          setInvitations([])
          invitationForm.resetFields()
        }}
        footer={null}
        width={720}
        destroyOnHidden
      >
        {invitationInterview?.application_id && invitationInterview.status === 'READY' && (
          <Button icon={<MailOutlined />} loading={invitationLoading} onClick={sendAccountInvitation}>发送站内邀请</Button>
        )}

        {invitationInterview && ['READY', 'IN_PROGRESS'].includes(invitationInterview.status) && (
          <Form<InterviewInvitationCreateRequest>
            form={invitationForm}
            layout="vertical"
            onFinish={submitInvitation}
            initialValues={{ expires_in_days: 7, max_access_count: 5 }}
            requiredMark={false}
          >
            <div className="invitation-form-grid">
              <Form.Item label="候选人邮箱" name="email" rules={[{ required: true, type: 'email', message: '请输入候选人邮箱' }]}>
                <Input prefix={<MailOutlined />} />
              </Form.Item>
              <Form.Item label="有效天数" name="expires_in_days" rules={[{ required: true }]}>
                <InputNumber min={1} max={30} precision={0} className="full-width-control" />
              </Form.Item>
              <Form.Item label="最多验证次数" name="max_access_count" rules={[{ required: true }]}>
                <InputNumber min={1} max={20} precision={0} className="full-width-control" />
              </Form.Item>
            </div>
            <Button type="primary" htmlType="submit" icon={<MailOutlined />} loading={invitationLoading}>创建备用链接</Button>
          </Form>
        )}

        {createdInvitation && (
          <Alert
            className="candidate-invitation-result"
            type="success"
            showIcon
            message="邀请已创建，请分别发送链接和访问码"
            description={(
              <div className="candidate-invitation-credentials">
                <div>
                  <Typography.Text type="secondary">邀请链接</Typography.Text>
                  <Typography.Text code>{`${window.location.origin}/candidate-interviews/invitations/${createdInvitation.invitation_token}`}</Typography.Text>
                  <Button type="text" icon={<CopyOutlined />} onClick={() => copyInvitationValue(`${window.location.origin}/candidate-interviews/invitations/${createdInvitation.invitation_token}`, '邀请链接')} aria-label="复制邀请链接" />
                </div>
                <div>
                  <Typography.Text type="secondary">访问码</Typography.Text>
                  <Typography.Text code>{createdInvitation.access_code}</Typography.Text>
                  <Button type="text" icon={<CopyOutlined />} onClick={() => copyInvitationValue(createdInvitation.access_code, '访问码')} aria-label="复制访问码" />
                </div>
                <Typography.Text type="secondary">凭据已加密保存，可在邀请记录中再次查看。</Typography.Text>
              </div>
            )}
          />
        )}

        <Typography.Title level={5} className="invitation-list-title">邀请记录</Typography.Title>
        <List
          loading={invitationLoading}
          dataSource={invitations}
          locale={{ emptyText: '暂无候选人邀请' }}
          renderItem={(item) => (
            <List.Item
              actions={ACTIVE_INVITATION_STATUSES.has(item.status)
                ? [<Button key="revoke" type="text" danger icon={<StopOutlined />} onClick={() => revokeInvitation(item)}>撤销</Button>]
                : undefined}
            >
              <List.Item.Meta
                title={<Space wrap><span>{item.email}</span><Tag color={statusColors[item.status]}>{item.status}</Tag></Space>}
                description={(
                  <div className="candidate-invitation-credentials candidate-invitation-record-credentials">
                    <Typography.Text type="secondary">验证 {item.access_count}/{item.max_access_count} 次 · 有效期至 {new Date(item.expires_at).toLocaleString('zh-CN')}</Typography.Text>
                    {item.invitation_token && item.access_code ? (
                      <>
                        <div>
                          <Typography.Text type="secondary">邀请链接</Typography.Text>
                          <Typography.Text code>{`${window.location.origin}/candidate-interviews/invitations/${item.invitation_token}`}</Typography.Text>
                          <Button type="text" icon={<CopyOutlined />} onClick={() => copyInvitationValue(`${window.location.origin}/candidate-interviews/invitations/${item.invitation_token}`, '邀请链接')} aria-label="复制邀请链接" />
                        </div>
                        <div>
                          <Typography.Text type="secondary">访问码</Typography.Text>
                          <Typography.Text code>{item.access_code}</Typography.Text>
                          <Button type="text" icon={<CopyOutlined />} onClick={() => copyInvitationValue(item.access_code!, '访问码')} aria-label="复制访问码" />
                        </div>
                      </>
                    ) : <Typography.Text type="warning">旧邀请凭据无法恢复，请撤销后重新创建。</Typography.Text>}
                  </div>
                )}
              />
            </List.Item>
          )}
        />
      </Modal>
    </main>
  )
}

export default InterviewManagementPage
