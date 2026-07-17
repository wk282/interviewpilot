import { useEffect, useState } from 'react'
import { MessageOutlined, PlayCircleOutlined, SendOutlined } from '@ant-design/icons'
import { Badge, Button, Empty, Input, List, Spin, Tag, Typography, message as antMessage } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getMessageThreads, getThreadMessages, sendThreadMessage } from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { MessageThread, PlatformMessage } from '../types/recruitment'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

function MessagesPage() {
  const workspace = getActiveWorkspace()
  const personal = workspace?.type === 'PERSONAL'
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [threads, setThreads] = useState<MessageThread[]>([])
  const [messages, setMessages] = useState<PlatformMessage[]>([])
  const [selectedId, setSelectedId] = useState(searchParams.get('thread') ?? '')
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [messageLoading, setMessageLoading] = useState(false)
  const [sending, setSending] = useState(false)

  const loadThreads = async (showLoading = true) => {
    if (!workspace) return
    if (showLoading) setLoading(true)
    try {
      const items = await getMessageThreads(personal ? undefined : workspace.id)
      setThreads(items)
      if (!selectedId && items.length > 0) {
        setSelectedId(items[0].id)
        setSearchParams({ thread: items[0].id }, { replace: true })
      }
    } catch (error) {
      if (showLoading) antMessage.error(getApiErrorMessage(error, '消息会话加载失败'))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  const loadMessages = async (threadId: string, showLoading = true) => {
    if (showLoading) setMessageLoading(true)
    try {
      setMessages(await getThreadMessages(threadId))
      await loadThreads(false)
    } catch (error) {
      if (showLoading) antMessage.error(getApiErrorMessage(error, '消息加载失败'))
    } finally {
      if (showLoading) setMessageLoading(false)
    }
  }

  useEffect(() => { void loadThreads() }, [workspace?.id])
  useEffect(() => {
    if (!selectedId) {
      setMessages([])
      return
    }
    void loadMessages(selectedId)
  }, [selectedId])
  useEffect(() => {
    if (!workspace) return
    const timer = window.setInterval(() => {
      void loadThreads(false)
      if (selectedId) void loadMessages(selectedId, false)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [workspace?.id, selectedId])

  const selectThread = (threadId: string) => {
    setSelectedId(threadId)
    setSearchParams({ thread: threadId }, { replace: true })
  }

  const send = async () => {
    if (!selectedId || !draft.trim()) return
    setSending(true)
    try {
      await sendThreadMessage(selectedId, draft.trim())
      setDraft('')
      await loadMessages(selectedId, false)
    } catch (error) {
      antMessage.error(getApiErrorMessage(error, '消息发送失败'))
    } finally {
      setSending(false)
    }
  }

  const openMessageRoute = (item: PlatformMessage) => {
    const route = item.message_metadata.route
    if (typeof route === 'string') navigate(route)
  }

  const selectedThread = threads.find((item) => item.id === selectedId)

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        {personal ? <CandidateSidebar /> : <EnterpriseSidebar workspace={workspace} />}
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">MESSAGES</p>
              <Typography.Title level={2}>站内消息</Typography.Title>
              <Typography.Paragraph type="secondary">围绕岗位申请与面试进行沟通</Typography.Paragraph>
            </div>
          </div>

          <section className="message-center">
            <aside className="message-thread-list">
              {loading ? <div className="message-loading"><Spin /></div> : threads.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无消息" /> : (
                <List
                  dataSource={threads}
                  renderItem={(item) => (
                    <button
                      type="button"
                      className={`message-thread-item${selectedId === item.id ? ' active' : ''}`}
                      onClick={() => selectThread(item.id)}
                    >
                      <div className="message-thread-heading">
                        <strong>{personal ? item.workspace_name : item.candidate_name}</strong>
                        {item.unread_count > 0 && <Badge count={item.unread_count} />}
                      </div>
                      <span>{item.job_title}</span>
                      <p>{item.latest_message ?? '暂无消息'}</p>
                    </button>
                  )}
                />
              )}
            </aside>

            <div className="message-conversation">
              {!selectedThread ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一个消息会话" />
              ) : (
                <>
                  <header className="message-conversation-header">
                    <div><strong>{selectedThread.subject}</strong><span>{personal ? selectedThread.workspace_name : selectedThread.candidate_name}</span></div>
                    <Tag>{selectedThread.application_status}</Tag>
                  </header>
                  <div className="message-history">
                    {messageLoading ? <div className="message-loading"><Spin /></div> : messages.map((item) => {
                      const own = personal ? item.sender_type === 'CANDIDATE' : item.sender_type === 'ENTERPRISE'
                      if (item.sender_type === 'SYSTEM') {
                        const route = item.message_metadata.route
                        return <div key={item.id} className="message-system"><MessageOutlined /> {item.content}{!personal && typeof route === 'string' && <Button type="link" onClick={() => openMessageRoute(item)}>查看评估报告</Button>}</div>
                      }
                      return (
                        <div key={item.id} className={`message-row${own ? ' own' : ''}`}>
                          <div className="message-bubble">
                            <span>{item.sender_name ?? (item.sender_type === 'CANDIDATE' ? '候选人' : '企业')}</span>
                            <p>{item.content}</p>
                            {item.message_type === 'INTERVIEW_INVITATION' && personal && (
                              <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => openMessageRoute(item)}>进入面试</Button>
                            )}
                            <time>{new Date(item.created_at).toLocaleString('zh-CN')}</time>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  <div className="message-composer">
                    <Input.TextArea value={draft} onChange={(event) => setDraft(event.target.value)} autoSize={{ minRows: 2, maxRows: 5 }} maxLength={5000} placeholder="输入消息" onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); void send() } }} />
                    <Button type="primary" icon={<SendOutlined />} loading={sending} disabled={!draft.trim()} onClick={send} aria-label="发送消息" />
                  </div>
                </>
              )}
            </div>
          </section>
        </section>
      </div>
    </main>
  )
}

export default MessagesPage
