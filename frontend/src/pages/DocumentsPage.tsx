import { useEffect, useState } from 'react'
import { ArrowLeftOutlined, DeleteOutlined, FileTextOutlined, InboxOutlined, PlayCircleOutlined, RedoOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons'
import { Button, Empty, Input, Modal, Progress, Space, Table, Tag, Tooltip, Typography, Upload, message } from 'antd'
import type { UploadProps } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import { deleteDocument, getDocuments, resumeDocumentProcessing, retryDocumentProcessing, uploadDocument } from '../api/documents'
import { reindexKnowledgeBaseBM25 } from '../api/retrieval'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { DocumentItem } from '../types/document'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const allowedExtensions = ['.pdf', '.docx', '.md', '.txt']

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

const ingestionStatusLabel: Record<string, string> = {
  PENDING: '等待处理',
  RUNNING: '处理中',
  WAITING_OCR: '等待OCR处理',
  COMPLETED: '已完成',
  FAILED: '处理失败',
  CANCELLED: '已取消',
}

const ingestionStatusColor: Record<string, string> = {
  PENDING: 'default',
  RUNNING: 'processing',
  WAITING_OCR: 'gold',
  COMPLETED: 'green',
  FAILED: 'red',
  CANCELLED: 'default',
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function DocumentsPage() {
  const { knowledgeBaseId = '' } = useParams()
  const navigate = useNavigate()
  const workspace = getActiveWorkspace()
  const personal = workspace?.type === 'PERSONAL'
  const canManage = personal || workspace?.role === 'OWNER' || workspace?.role === 'ADMIN'
  const [items, setItems] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const loadItems = () => {
    if (!workspace || !knowledgeBaseId) return
    setLoading(true)
    getDocuments(workspace.id, knowledgeBaseId)
      .then(setItems)
      .catch((error) => message.error(getApiErrorMessage(error, '文档列表加载失败')))
      .finally(() => setLoading(false))
  }

  useEffect(loadItems, [workspace?.id, knowledgeBaseId])

  const hasActiveJob = items.some((item) =>
    ['PENDING', 'RUNNING', 'WAITING_OCR'].includes(item.ingestion_status),
  )
  const normalizedSearchQuery = searchQuery.trim().toLowerCase()
  const filteredItems = items.filter((item) => (
    !normalizedSearchQuery
    || [item.original_filename, item.name, item.status, item.ingestion_status, ingestionStatusLabel[item.ingestion_status]]
      .some((value) => value?.toLowerCase().includes(normalizedSearchQuery))
  ))
  useEffect(() => {
    if (!hasActiveJob || !workspace || !knowledgeBaseId) return
    const timer = window.setInterval(() => {
      getDocuments(workspace.id, knowledgeBaseId).then(setItems).catch(() => undefined)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [hasActiveJob, workspace?.id, knowledgeBaseId])

  const uploadProps: UploadProps = {
    accept: '.pdf,.docx,.md,.txt',
    multiple: false,
    showUploadList: false,
    beforeUpload: async (file) => {
      const extension = `.${file.name.split('.').pop()?.toLowerCase()}`
      if (!allowedExtensions.includes(extension)) {
        message.error('仅支持 PDF、DOCX、Markdown 和 TXT 文件')
        return Upload.LIST_IGNORE
      }
      if (file.size > 25 * 1024 * 1024) {
        message.error('文件不能超过 25 MB')
        return Upload.LIST_IGNORE
      }
      if (!workspace) return Upload.LIST_IGNORE

      setUploading(true)
      try {
        await uploadDocument(workspace.id, knowledgeBaseId, file as File)
        message.success('文件上传成功，已创建待处理任务')
        loadItems()
      } catch (error) {
        message.error(getApiErrorMessage(error, '文件上传失败'))
      } finally {
        setUploading(false)
      }
      return false
    },
  }

  const removeDocument = (item: DocumentItem) => {
    if (!workspace) return
    Modal.confirm({
      title: `删除“${item.original_filename}”？`,
      content: '文档、版本、任务记录、Chunk、向量和本地文件将被永久删除，无法恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocument(workspace.id, knowledgeBaseId, item.id)
          message.success('文档已删除')
          loadItems()
        } catch (error) {
          message.error(getApiErrorMessage(error, '文档删除失败'))
        }
      },
    })
  }

  const resumeProcessing = async (item: DocumentItem) => {
    if (!workspace) return
    try {
      await resumeDocumentProcessing(workspace.id, knowledgeBaseId, item.id)
      message.success('任务已重新提交')
      loadItems()
    } catch (error) {
      message.error(getApiErrorMessage(error, '任务提交失败'))
    }
  }

  const retryProcessing = (item: DocumentItem, mode: 'AUTO' | 'REEMBED') => {
    if (!workspace) return
    const vectorFailure = mode === 'AUTO' && ['EMBEDDING', 'INDEXING'].includes(item.ingestion_stage ?? '')
    Modal.confirm({
      title: mode === 'REEMBED' || vectorFailure ? `重新向量化“${item.original_filename}”？` : `重试“${item.original_filename}”？`,
      content: mode === 'REEMBED' || vectorFailure ? '将重新调用 Embedding API，并覆盖该文档现有的子块向量。' : '系统会从当前可恢复阶段继续执行。',
      okText: mode === 'REEMBED' || vectorFailure ? '重新向量化' : '重试',
      cancelText: '取消',
      onOk: async () => {
        try {
          await retryDocumentProcessing(workspace.id, knowledgeBaseId, item.id, mode)
          message.success('任务已重新提交')
          loadItems()
        } catch (error) {
          message.error(getApiErrorMessage(error, '任务重试失败'))
        }
      },
    })
  }

  const rebuildBM25Index = async () => {
    if (!workspace || !knowledgeBaseId) return
    setReindexing(true)
    try {
      const result = await reindexKnowledgeBaseBM25(workspace.id, knowledgeBaseId)
      message.success(`BM25 索引已重建，共 ${result.indexed_count} 个子块`)
    } catch (error) {
      message.error(getApiErrorMessage(error, 'BM25 索引重建失败'))
    } finally {
      setReindexing(false)
    }
  }

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        {personal ? <CandidateSidebar /> : <EnterpriseSidebar workspace={workspace} />}
        <section className="dashboard-main">
          <Button type="link" icon={<ArrowLeftOutlined />} className="page-back" onClick={() => navigate(personal ? '/candidate/knowledge-bases' : '/enterprise/knowledge-bases')}>返回知识库</Button>
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">DOCUMENTS</p>
              <Typography.Title level={2}>文档管理</Typography.Title>
              <Typography.Paragraph type="secondary">支持 PDF、DOCX、Markdown 和 TXT，单文件不超过 25 MB</Typography.Paragraph>
            </div>
            <Space>
              <Button size="large" icon={<SearchOutlined />} onClick={() => navigate(`${personal ? '/candidate' : '/enterprise'}/knowledge-bases/${knowledgeBaseId}/retrieval`)}>检索测试</Button>
              {canManage && <Button size="large" icon={<SyncOutlined />} loading={reindexing} onClick={rebuildBM25Index}>重建 BM25 索引</Button>}
              {canManage && <Upload {...uploadProps}><Button type="primary" size="large" icon={<InboxOutlined />} loading={uploading}>上传文件</Button></Upload>}
            </Space>
          </div>

          <section className="content-panel document-panel">
            <div className="list-toolbar">
              <Input allowClear prefix={<SearchOutlined />} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索文件名或处理状态" className="list-search" />
            </div>
            {filteredItems.length === 0 && !loading ? (
              <Empty description="暂无文档" />
            ) : (
              <Table<DocumentItem>
                rowKey="id"
                loading={loading}
                dataSource={filteredItems}
                pagination={false}
                scroll={{ x: 760 }}
                columns={[
                  { title: '文件', key: 'file', render: (_, item) => <div className="document-name"><FileTextOutlined /><div><strong>{item.original_filename}</strong><span>{formatSize(item.file_size)}</span></div></div> },
                  { title: '版本', dataIndex: 'version_number', key: 'version', render: (value) => `v${value}` },
                  { title: '状态', key: 'status', render: (_, item) => <Tooltip title={item.ingestion_error_message}><Tag color={ingestionStatusColor[item.ingestion_status]}>{ingestionStatusLabel[item.ingestion_status] ?? item.ingestion_status}</Tag></Tooltip> },
                  { title: '入库进度', key: 'progress', width: 180, render: (_, item) => <Progress percent={item.ingestion_progress} size="small" /> },
                  { title: '上传时间', dataIndex: 'created_at', key: 'created', render: (value) => new Date(value).toLocaleString('zh-CN') },
                  ...(canManage ? [{
                    title: '操作',
                    key: 'actions',
                    width: 110,
                    render: (_: unknown, item: DocumentItem) => (
                      <div className="document-actions">
                        {canContinueProcessing(item) && (
                          <Button type="text" icon={<PlayCircleOutlined />} onClick={() => resumeProcessing(item)} aria-label="继续处理" />
                        )}
                        {item.ingestion_status === 'FAILED' && (
                          <Button type="text" icon={<RedoOutlined />} onClick={() => retryProcessing(item, 'AUTO')} aria-label="重试失败任务" />
                        )}
                        {item.ingestion_status === 'COMPLETED' && (
                          <Button type="text" icon={<SyncOutlined />} onClick={() => retryProcessing(item, 'REEMBED')} aria-label="重新向量化" />
                        )}
                        <Button type="text" danger icon={<DeleteOutlined />} disabled={item.ingestion_status === 'RUNNING'} onClick={() => removeDocument(item)} aria-label="删除文档" />
                      </div>
                    ),
                  }] : []),
                ]}
              />
            )}
          </section>
        </section>
      </div>
    </main>
  )
}

export default DocumentsPage
