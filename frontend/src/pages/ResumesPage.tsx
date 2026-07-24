import { useEffect, useState } from 'react'
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Modal,
  Progress,
  Spin,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd'
import type { UploadProps } from 'antd'
import { deleteDocument, getDocumentParsedContent, getDocuments, resumeDocumentProcessing, retryDocumentProcessing, uploadDocument } from '../api/documents'
import { getCandidates, updateCandidate } from '../api/interviews'
import { createKnowledgeBase, getKnowledgeBases } from '../api/knowledgeBases'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import type { DocumentItem, DocumentParsedContent } from '../types/document'
import type { CandidateProfile } from '../types/interview'
import type { KnowledgeBase } from '../types/knowledgeBase'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const statusLabel: Record<string, string> = {
  UPLOADED: '等待处理',
  PROCESSING: '处理中',
  OCR_PENDING: '等待OCR处理',
  READY: '可使用',
  FAILED: '处理失败',
}

const statusColor: Record<string, string> = {
  UPLOADED: 'default',
  PROCESSING: 'processing',
  OCR_PENDING: 'gold',
  READY: 'success',
  FAILED: 'error',
}

const canContinueProcessing = (item: DocumentItem) => (
  (
    item.ingestion_status === 'PENDING'
    && (
      ['CHUNKING', 'EMBEDDING'].includes(item.ingestion_stage ?? '')
      || (
        item.ingestion_stage === 'PARSING'
        && ['.docx', '.pdf'].some((extension) => item.original_filename.toLowerCase().endsWith(extension))
      )
    )
  )
  || (item.ingestion_status === 'WAITING_OCR' && item.ingestion_stage === 'OCR')
)

function ResumesPage() {
  const workspace = getActiveWorkspace()
  const [resumeBases, setResumeBases] = useState<KnowledgeBase[]>([])
  const [resumes, setResumes] = useState<DocumentItem[]>([])
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [actionId, setActionId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [parsedContent, setParsedContent] = useState<DocumentParsedContent | null>(null)
  const [parsedContentOpen, setParsedContentOpen] = useState(false)
  const [parsedContentLoading, setParsedContentLoading] = useState(false)

  const loadData = async (showLoading = true) => {
    if (!workspace) return
    if (showLoading) setLoading(true)
    try {
      const [knowledgeBases, candidates] = await Promise.all([
        getKnowledgeBases(workspace.id),
        getCandidates(workspace.id),
      ])
      const bases = knowledgeBases.filter((item) => item.purpose === 'RESUME')
      const documentGroups = await Promise.all(
        bases.map((item) => getDocuments(workspace.id, item.id)),
      )
      setResumeBases(bases)
      setResumes(
        documentGroups
          .flat()
          .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)),
      )
      setProfile(candidates.find((item) => item.source === 'PERSONAL_ACCOUNT') ?? null)
    } catch (error) {
      message.error(getApiErrorMessage(error, '简历数据加载失败'))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => { void loadData() }, [workspace?.id])

  const processing = resumes.some((item) =>
    ['PENDING', 'RUNNING', 'WAITING_OCR'].includes(item.ingestion_status),
  )
  useEffect(() => {
    if (!processing) return
    const timer = window.setInterval(() => { void loadData(false) }, 3000)
    return () => window.clearInterval(timer)
  }, [processing, workspace?.id])

  const normalizedSearchQuery = searchQuery.trim().toLowerCase()
  const filteredResumes = resumes.filter((item) => (
    !normalizedSearchQuery
    || [item.original_filename, item.name, item.status, statusLabel[item.status]]
      .some((value) => value?.toLowerCase().includes(normalizedSearchQuery))
  ))

  const ensureResumeBase = async () => {
    if (!workspace) throw new Error('工作空间不存在')
    if (resumeBases.length > 0) return resumeBases[0]
    const knowledgeBases = await getKnowledgeBases(workspace.id)
    const existing = knowledgeBases.find((item) => item.purpose === 'RESUME')
    if (existing) {
      setResumeBases([existing])
      return existing
    }
    const usedNames = new Set(knowledgeBases.map((item) => item.name))
    let name = '我的简历'
    let suffix = 2
    while (usedNames.has(name)) {
      name = `我的简历 ${suffix}`
      suffix += 1
    }
    const created = await createKnowledgeBase(workspace.id, {
      name,
      purpose: 'RESUME',
      visibility: 'PRIVATE',
    })
    setResumeBases([created])
    return created
  }

  const uploadProps: UploadProps = {
    accept: '.pdf,.docx,.md,.txt',
    multiple: false,
    showUploadList: false,
    beforeUpload: async (file) => {
      if (!workspace) return Upload.LIST_IGNORE
      setUploading(true)
      try {
        const knowledgeBase = await ensureResumeBase()
        await uploadDocument(workspace.id, knowledgeBase.id, file as File)
        message.success('简历已上传，正在解析')
        await loadData(false)
      } catch (error) {
        message.error(getApiErrorMessage(error, '简历上传失败'))
      } finally {
        setUploading(false)
      }
      return Upload.LIST_IGNORE
    },
  }

  const setCurrentResume = async (item: DocumentItem) => {
    if (!workspace || !profile) return
    setActionId(item.id)
    try {
      const updated = await updateCandidate(workspace.id, profile.id, {
        resume_document_id: item.id,
      })
      setProfile(updated)
      message.success('当前简历已更新')
    } catch (error) {
      message.error(getApiErrorMessage(error, '当前简历设置失败'))
    } finally {
      setActionId(null)
    }
  }

  const retryResume = async (item: DocumentItem) => {
    if (!workspace) return
    setActionId(item.id)
    try {
      await retryDocumentProcessing(workspace.id, item.knowledge_base_id, item.id, 'AUTO')
      message.success('简历已重新提交处理')
      await loadData(false)
    } catch (error) {
      message.error(getApiErrorMessage(error, '重新处理失败'))
    } finally {
      setActionId(null)
    }
  }

  const continueResume = async (item: DocumentItem) => {
    if (!workspace) return
    setActionId(item.id)
    try {
      await resumeDocumentProcessing(workspace.id, item.knowledge_base_id, item.id)
      message.success('简历处理已继续')
      await loadData(false)
    } catch (error) {
      message.error(getApiErrorMessage(error, '继续处理失败'))
    } finally {
      setActionId(null)
    }
  }

  const viewParsedContent = async (item: DocumentItem) => {
    if (!workspace) return
    setParsedContent(null)
    setParsedContentOpen(true)
    setParsedContentLoading(true)
    try {
      const content = await getDocumentParsedContent(
        workspace.id,
        item.knowledge_base_id,
        item.id,
      )
      setParsedContent(content)
    } catch (error) {
      setParsedContentOpen(false)
      message.error(getApiErrorMessage(error, '解析结果加载失败'))
    } finally {
      setParsedContentLoading(false)
    }
  }

  const removeResume = (item: DocumentItem) => {
    if (!workspace) return
    const isCurrent = profile?.resume_document_id === item.id
    Modal.confirm({
      title: `删除简历“${item.original_filename}”？`,
      content: isCurrent
        ? '这是当前简历。删除后需要重新选择简历才能创建新的模拟面试。'
        : '简历文件、解析结果、切片和向量数据都会被删除。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocument(workspace.id, item.knowledge_base_id, item.id)
          message.success('简历已删除')
          await loadData(false)
        } catch (error) {
          message.error(getApiErrorMessage(error, '简历删除失败'))
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
              <p className="eyebrow dark">RESUMES</p>
              <Typography.Title level={2}>我的简历</Typography.Title>
              <Typography.Paragraph type="secondary">管理用于岗位投递和模拟面试的简历版本</Typography.Paragraph>
            </div>
            <Upload {...uploadProps}>
              <Button type="primary" size="large" icon={<InboxOutlined />} loading={uploading}>
                上传简历
              </Button>
            </Upload>
          </div>

          {!profile && resumes.length > 0 && (
            <Alert
              className="resume-alert"
              type="info"
              showIcon
              message="简历已保存"
              description="创建个人档案时选择一份状态为“可使用”的简历，即可用于生成模拟面试。"
            />
          )}

          <section className="content-panel document-panel">
            <div className="list-toolbar">
              <Input allowClear prefix={<SearchOutlined />} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索简历文件名或状态" className="list-search" />
            </div>
            {filteredResumes.length === 0 && !loading ? (
              <Empty description="尚未上传简历" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table<DocumentItem>
                rowKey="id"
                loading={loading}
                dataSource={filteredResumes}
                pagination={false}
                scroll={{ x: 760 }}
                columns={[
                  {
                    title: '简历文件',
                    key: 'file',
                    render: (_, item) => (
                      <div className="document-name">
                        <FileTextOutlined />
                        <div><strong>{item.original_filename}</strong><span>{formatSize(item.file_size)}</span></div>
                      </div>
                    ),
                  },
                  {
                    title: '处理状态',
                    key: 'status',
                    width: 190,
                    render: (_, item) => (
                      item.status === 'PROCESSING'
                        ? <Progress percent={item.ingestion_progress} size="small" status="active" />
                        : <Tag color={statusColor[item.status]}>{statusLabel[item.status] ?? item.status}</Tag>
                    ),
                  },
                  {
                    title: '用途',
                    key: 'current',
                    width: 110,
                    render: (_, item) => profile?.resume_document_id === item.id
                      ? <Tag color="blue" icon={<CheckCircleOutlined />}>当前简历</Tag>
                      : '-',
                  },
                  {
                    title: '上传时间',
                    dataIndex: 'created_at',
                    key: 'created',
                    width: 180,
                    render: (value) => new Date(value).toLocaleString('zh-CN'),
                  },
                  {
                    title: '操作',
                    key: 'actions',
                    width: 200,
                    render: (_, item) => (
                      <Space>
                        {item.status === 'READY' && (
                          <Tooltip title="查看解析文本">
                            <Button
                              type="text"
                              icon={<EyeOutlined />}
                              onClick={() => viewParsedContent(item)}
                              aria-label="查看简历解析文本"
                            />
                          </Tooltip>
                        )}
                        {canContinueProcessing(item) && (
                          <Tooltip title="继续处理">
                            <Button
                              type="text"
                              icon={<PlayCircleOutlined />}
                              loading={actionId === item.id}
                              onClick={() => continueResume(item)}
                              aria-label="继续处理简历"
                            />
                          </Tooltip>
                        )}
                        {item.status === 'READY' && profile?.resume_document_id !== item.id && (
                          <Tooltip title={profile ? '设为当前简历' : '创建个人档案后可选择'}>
                            <Button
                              type="text"
                              icon={<CheckCircleOutlined />}
                              disabled={!profile}
                              loading={actionId === item.id}
                              onClick={() => setCurrentResume(item)}
                              aria-label="设为当前简历"
                            />
                          </Tooltip>
                        )}
                        {item.status === 'FAILED' && (
                          <Tooltip title="重新处理">
                            <Button
                              type="text"
                              icon={<ReloadOutlined />}
                              loading={actionId === item.id}
                              onClick={() => retryResume(item)}
                              aria-label="重新处理简历"
                            />
                          </Tooltip>
                        )}
                        <Tooltip title="删除简历">
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            disabled={item.ingestion_status === 'RUNNING'}
                            onClick={() => removeResume(item)}
                            aria-label="删除简历"
                          />
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
      <Drawer
        title={parsedContent?.original_filename ?? '简历解析结果'}
        open={parsedContentOpen}
        width="min(760px, 100vw)"
        destroyOnHidden
        onClose={() => setParsedContentOpen(false)}
      >
        {parsedContentLoading ? (
          <div className="resume-parsed-loading"><Spin /></div>
        ) : parsedContent ? (
          <div className="resume-parsed-result">
            <Descriptions size="small" column={{ xs: 1, sm: 2 }} bordered>
              <Descriptions.Item label="解析器">
                {parsedContent.parser_name ?? '-'}
                {parsedContent.parser_version ? ` v${parsedContent.parser_version}` : ''}
              </Descriptions.Item>
              <Descriptions.Item label="文本字符">{parsedContent.character_count}</Descriptions.Item>
              <Descriptions.Item label="内容块">{parsedContent.block_count}</Descriptions.Item>
              <Descriptions.Item label="页数">{parsedContent.page_count ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="原生文本块">{parsedContent.native_block_count}</Descriptions.Item>
              <Descriptions.Item label="OCR文本块">{parsedContent.ocr_block_count}</Descriptions.Item>
              {parsedContent.page_kinds.length > 0 && (
                <Descriptions.Item label="页面类型" span={2}>
                  <Space size={[4, 6]} wrap>
                    {parsedContent.page_kinds.map((kind, index) => (
                      <Tag key={`${index}-${kind}`}>第{index + 1}页 {kind}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
              )}
              {parsedContent.ocr_processed_pages.length > 0 && (
                <Descriptions.Item label="OCR页" span={2}>
                  {parsedContent.ocr_processed_pages.join('、')}
                </Descriptions.Item>
              )}
            </Descriptions>
            <Typography.Title level={5}>解析文本</Typography.Title>
            <pre className="resume-parsed-text">{parsedContent.plain_text}</pre>
          </div>
        ) : null}
      </Drawer>
    </main>
  )
}

export default ResumesPage
