import { useEffect, useState } from 'react'
import { BookOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Empty, Form, Input, Modal, Select, Tag, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { createKnowledgeBase, deleteKnowledgeBase, getKnowledgeBases, updateKnowledgeBase } from '../api/knowledgeBases'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { KnowledgeBase, KnowledgeBaseCreateRequest, KnowledgeBasePurpose, KnowledgeBaseUpdateRequest } from '../types/knowledgeBase'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const purposeLabels: Record<KnowledgeBasePurpose, string> = {
  RESUME: '简历',
  PERSONAL_LEARNING: '个人学习资料',
  ENTERPRISE_QUESTION_BANK: '企业题库',
  JOB_SPECIFIC: '岗位专项',
  SCORING_RUBRIC: '评分标准',
  TECHNICAL_STANDARD: '技术规范',
}

const personalPurposes = ['RESUME', 'PERSONAL_LEARNING', 'JOB_SPECIFIC'] as const
const enterprisePurposes = ['RESUME', 'ENTERPRISE_QUESTION_BANK', 'JOB_SPECIFIC', 'SCORING_RUBRIC', 'TECHNICAL_STANDARD'] as const

function KnowledgeBasesPage() {
  const workspace = getActiveWorkspace()
  const navigate = useNavigate()
  const personal = workspace?.type === 'PERSONAL'
  const canManage = personal || workspace?.role === 'OWNER' || workspace?.role === 'ADMIN'
  const [form] = Form.useForm<KnowledgeBaseCreateRequest>()
  const [editForm] = Form.useForm<KnowledgeBaseUpdateRequest>()
  const [items, setItems] = useState<KnowledgeBase[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [editingItem, setEditingItem] = useState<KnowledgeBase | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const loadItems = () => {
    if (!workspace) return
    setLoading(true)
    getKnowledgeBases(workspace.id)
      .then(setItems)
      .catch((error) => message.error(getApiErrorMessage(error, '知识库加载失败')))
      .finally(() => setLoading(false))
  }

  useEffect(loadItems, [workspace?.id])

  const submit = async (values: KnowledgeBaseCreateRequest) => {
    if (!workspace) return
    setCreating(true)
    try {
      await createKnowledgeBase(workspace.id, values)
      message.success('知识库创建成功')
      setModalOpen(false)
      form.resetFields()
      loadItems()
    } catch (error) {
      message.error(getApiErrorMessage(error, '知识库创建失败'))
    } finally {
      setCreating(false)
    }
  }

  const remove = (item: KnowledgeBase) => {
    if (!workspace) return
    Modal.confirm({
      title: `删除“${item.name}”？`,
      content: '知识库、全部文档、处理记录、向量数据和本地文件将被永久删除，此操作不可恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteKnowledgeBase(workspace.id, item.id)
          message.success('知识库已删除')
          loadItems()
        } catch (error) {
          message.error(getApiErrorMessage(error, '知识库删除失败'))
        }
      },
    })
  }

  const openEditor = (item: KnowledgeBase) => {
    setEditingItem(item)
  }

  const submitUpdate = async (values: KnowledgeBaseUpdateRequest) => {
    if (!workspace || !editingItem) return
    setUpdating(true)
    try {
      await updateKnowledgeBase(workspace.id, editingItem.id, values)
      message.success('知识库已更新')
      setEditingItem(null)
      editForm.resetFields()
      loadItems()
    } catch (error) {
      message.error(getApiErrorMessage(error, '知识库更新失败'))
    } finally {
      setUpdating(false)
    }
  }

  const purposes = personal ? personalPurposes : enterprisePurposes
  const editablePurposes = editingItem?.purpose === 'RESUME'
    ? ['RESUME'] as const
    : purposes.filter((purpose) => purpose !== 'RESUME')
  const normalizedSearchQuery = searchQuery.trim().toLowerCase()
  const filteredItems = items.filter((item) => (
    !normalizedSearchQuery
    || [item.name, item.purpose, purposeLabels[item.purpose], item.visibility]
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
              <p className="eyebrow dark">KNOWLEDGE BASE</p>
              <Typography.Title level={2}>{personal ? '个人知识库' : '企业知识库'}</Typography.Title>
              <Typography.Paragraph type="secondary">管理用于检索、出题与评分的资料</Typography.Paragraph>
            </div>
            {canManage && <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建知识库</Button>}
          </div>

          {loading ? (
            <div className="loading-state">加载中...</div>
          ) : items.length === 0 ? (
            <section className="content-panel"><Empty description="暂无知识库" /></section>
          ) : (
            <>
              <div className="list-toolbar">
                <Input allowClear prefix={<SearchOutlined />} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索知识库名称或分类" className="list-search" />
              </div>
              {filteredItems.length === 0 ? <section className="content-panel"><Empty description="没有匹配的知识库" /></section> : <div className="knowledge-grid">
              {filteredItems.map((item) => (
                <article
                  className="knowledge-item"
                  key={item.id}
                  onClick={() => navigate(`${personal ? '/candidate' : '/enterprise'}/knowledge-bases/${item.id}/documents`)}
                >
                  <div className="knowledge-item-icon">{item.purpose === 'RESUME' ? <FileTextOutlined /> : <BookOutlined />}</div>
                  <div className="knowledge-item-heading">
                    <Typography.Title level={4}>{item.name}</Typography.Title>
                    <Tag>{purposeLabels[item.purpose]}</Tag>
                  </div>
                  <p>{item.visibility === 'PRIVATE' ? '仅创建者和管理员可见' : '工作空间成员可见'}</p>
                  <div className="knowledge-item-footer">
                    <span>{new Date(item.created_at).toLocaleDateString('zh-CN')}</span>
                    {canManage && <div className="knowledge-item-actions">
                      <Button type="text" icon={<EditOutlined />} onClick={(event) => { event.stopPropagation(); openEditor(item) }} aria-label="编辑知识库" />
                      <Button type="text" danger icon={<DeleteOutlined />} onClick={(event) => { event.stopPropagation(); remove(item) }} aria-label="删除知识库" />
                    </div>}
                  </div>
                </article>
              ))}
              </div>}
            </>
          )}
        </section>
      </div>

      <Modal title="新建知识库" open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} destroyOnHidden>
        <Form<KnowledgeBaseCreateRequest> form={form} layout="vertical" onFinish={submit} requiredMark={false} initialValues={{ purpose: purposes[0], visibility: personal ? 'PRIVATE' : 'WORKSPACE' }}>
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入知识库名称' }]}>
            <Input placeholder="例如：Java 后端面试资料" />
          </Form.Item>
          <Form.Item label="用途" name="purpose" rules={[{ required: true }]}>
            <Select options={purposes.map((purpose) => ({ value: purpose, label: purposeLabels[purpose] }))} />
          </Form.Item>
          <Form.Item label="可见范围" name="visibility" rules={[{ required: true }]}>
            <Select options={personal
              ? [{ value: 'PRIVATE', label: '私有' }]
              : [{ value: 'WORKSPACE', label: '企业成员可见' }, { value: 'PRIVATE', label: '仅创建者和管理员可见' }]}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={creating}>创建知识库</Button>
        </Form>
      </Modal>

      <Modal
        title="编辑知识库"
        open={editingItem !== null}
        onCancel={() => setEditingItem(null)}
        afterOpenChange={(open) => {
          if (open && editingItem) {
            editForm.setFieldsValue({
              name: editingItem.name,
              purpose: editingItem.purpose,
              visibility: editingItem.visibility,
            })
          }
        }}
        footer={null}
        destroyOnHidden
      >
        <Form<KnowledgeBaseUpdateRequest> form={editForm} layout="vertical" onFinish={submitUpdate} requiredMark={false}>
          <Form.Item label="名称" name="name" rules={[{ required: true, whitespace: true, message: '请输入知识库名称' }]}>
            <Input maxLength={255} autoFocus />
          </Form.Item>
          <Form.Item label="分类" name="purpose" rules={[{ required: true, message: '请选择知识库分类' }]}>
            <Select
              disabled={editingItem?.purpose === 'RESUME'}
              options={editablePurposes.map((purpose) => ({ value: purpose, label: purposeLabels[purpose] }))}
            />
          </Form.Item>
          <Form.Item label="可见范围" name="visibility" rules={[{ required: true, message: '请选择可见范围' }]}>
            <Select options={personal
              ? [{ value: 'PRIVATE', label: '私有' }]
              : [{ value: 'WORKSPACE', label: '企业成员可见' }, { value: 'PRIVATE', label: '仅创建者和管理员可见' }]}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={updating}>保存</Button>
        </Form>
      </Modal>
    </main>
  )
}

export default KnowledgeBasesPage
