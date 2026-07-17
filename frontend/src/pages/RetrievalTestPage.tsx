import { useState } from 'react'
import { ArrowLeftOutlined, FileTextOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons'
import { Button, Empty, Input, InputNumber, Select, Space, Tag, Typography, message } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import { reindexKnowledgeBaseBM25, searchKnowledgeBase } from '../api/retrieval'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { RetrievalProfile, RetrievalResponse } from '../types/retrieval'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const profileLabels: Record<RetrievalProfile, string> = {
  VECTOR: '纯向量',
  VECTOR_TRIGRAM: '向量 + Trigram',
  VECTOR_RERANK: '纯向量 + Reranker',
  VECTOR_TRIGRAM_RERANK: '向量 + Trigram + Reranker',
  VECTOR_BM25: '向量 + BM25',
  VECTOR_BM25_RERANK: '向量 + BM25 + Reranker',
  VECTOR_TRIGRAM_BM25: '向量 + Trigram + BM25',
  VECTOR_TRIGRAM_BM25_RERANK: '向量 + Trigram + BM25 + Reranker',
}

function RetrievalTestPage() {
  const { knowledgeBaseId = '' } = useParams()
  const navigate = useNavigate()
  const workspace = getActiveWorkspace()
  const personal = workspace?.type === 'PERSONAL'
  const canManage = personal || workspace?.role === 'OWNER' || workspace?.role === 'ADMIN'
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [profile, setProfile] = useState<RetrievalProfile>('VECTOR_TRIGRAM_BM25_RERANK')
  const [searching, setSearching] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [response, setResponse] = useState<RetrievalResponse | null>(null)

  const search = async () => {
    const normalizedQuery = query.trim()
    if (!normalizedQuery) {
      message.warning('请输入检索问题')
      return
    }
    if (!workspace || !knowledgeBaseId) return

    setSearching(true)
    try {
      const result = await searchKnowledgeBase(workspace.id, knowledgeBaseId, normalizedQuery, topK, profile)
      setResponse(result)
    } catch (error) {
      message.error(getApiErrorMessage(error, '知识库检索失败'))
    } finally {
      setSearching(false)
    }
  }

  const reindexBM25 = async () => {
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

  const documentsPath = `${personal ? '/candidate' : '/enterprise'}/knowledge-bases/${knowledgeBaseId}/documents`

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        {personal ? <CandidateSidebar /> : <EnterpriseSidebar workspace={workspace} />}
        <section className="dashboard-main">
          <Button type="link" icon={<ArrowLeftOutlined />} className="page-back" onClick={() => navigate(documentsPath)}>返回文档管理</Button>
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">RETRIEVAL</p>
              <Typography.Title level={2}>检索测试</Typography.Title>
              <Typography.Paragraph type="secondary">查看问题召回的文档证据与父级上下文</Typography.Paragraph>
            </div>
          </div>

          <section className="content-panel retrieval-search-panel">
            <Input.TextArea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入一个技术面试问题"
              autoSize={{ minRows: 3, maxRows: 6 }}
              maxLength={1000}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault()
                  void search()
                }
              }}
            />
            <div className="retrieval-search-actions">
              <Space wrap>
                <Typography.Text type="secondary">检索策略</Typography.Text>
                <Select<RetrievalProfile>
                  value={profile}
                  onChange={setProfile}
                  popupMatchSelectWidth={false}
                  options={(Object.entries(profileLabels) as Array<[RetrievalProfile, string]>).map(([value, label]) => ({ value, label }))}
                />
                <Typography.Text type="secondary">召回数量</Typography.Text>
                <InputNumber min={1} max={20} value={topK} onChange={(value) => setTopK(value ?? 5)} />
              </Space>
              <Space wrap>
                {canManage && <Button icon={<SyncOutlined />} loading={reindexing} onClick={reindexBM25}>重建 BM25 索引</Button>}
                <Button type="primary" icon={<SearchOutlined />} loading={searching} onClick={search}>检索</Button>
              </Space>
            </div>
          </section>

          {response && (
            <section className="retrieval-results" aria-live="polite">
              <div className="retrieval-results-heading">
                <Typography.Title level={4}>召回结果</Typography.Title>
                <Typography.Text type="secondary">{response.result_count} 条 · {profileLabels[response.retrieval_profile]} · {response.embedding_model}</Typography.Text>
              </div>
              {response.results.length === 0 ? (
                <div className="content-panel"><Empty description="当前知识库没有可检索内容" /></div>
              ) : response.results.map((item, index) => (
                <article className="retrieval-result" key={item.chunk_id}>
                  <div className="retrieval-result-heading">
                    <Space>
                      <span className="retrieval-rank">{index + 1}</span>
                      <FileTextOutlined />
                      <Typography.Text strong>{item.filename}</Typography.Text>
                    </Space>
                    <Space wrap>
                      <Tag>融合 #{item.fusion_rank} · {(item.fusion_score * 100).toFixed(1)}%</Tag>
                      {item.vector_similarity !== null && <Tag color="blue">向量 {(item.vector_similarity * 100).toFixed(1)}%</Tag>}
                      {item.trigram_similarity !== null && <Tag color="green">Trigram {(item.trigram_similarity * 100).toFixed(1)}%</Tag>}
                      {item.bm25_score !== null && <Tag color="cyan">BM25 {item.bm25_score.toFixed(3)}</Tag>}
                      {item.rerank_score !== null && <Tag color="purple">重排 #{item.rerank_rank} · {item.rerank_score.toFixed(6)}</Tag>}
                    </Space>
                  </div>
                  <div className="retrieval-evidence">
                    <Typography.Text type="secondary">命中片段</Typography.Text>
                    <p>{item.child_content}</p>
                  </div>
                  <div className="retrieval-context">
                    <Typography.Text type="secondary">父级上下文</Typography.Text>
                    <p>{item.context}</p>
                  </div>
                </article>
              ))}
            </section>
          )}
        </section>
      </div>
    </main>
  )
}

export default RetrievalTestPage
