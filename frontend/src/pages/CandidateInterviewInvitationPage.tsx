import { useEffect, useRef, useState } from 'react'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ForwardOutlined,
  LockOutlined,
  MailOutlined,
  PlayCircleOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Form,
  Input,
  Modal,
  Progress,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import { useParams } from 'react-router-dom'
import {
  finishPublicInterview,
  getPublicInterviewInvitation,
  getPublicInterviewRuntime,
  skipPublicInterviewQuestion,
  startPublicInterview,
  submitPublicInterviewAnswer,
  verifyPublicInterviewInvitation,
} from '../api/interviewInvitations'
import type {
  InterviewInvitationVerifyRequest,
  InterviewRuntime,
  PublicInterviewInvitation,
} from '../types/interviewInvitation'
import { getApiErrorMessage } from '../utils/apiError'

const questionTypeLabel: Record<string, string> = {
  INTRODUCTION: '自我介绍',
  TECHNICAL: '技术问题',
  PROJECT: '项目深挖',
  SYSTEM_DESIGN: '系统设计',
  BEHAVIORAL: '行为问题',
  FOLLOW_UP: '追问',
}

const difficultyLabel: Record<string, string> = {
  EASY: '基础',
  MEDIUM: '进阶',
  HARD: '深入',
}

const unavailableStatusText: Record<string, string> = {
  EXPIRED: '该面试邀请已过期',
  REVOKED: '该面试邀请已被企业撤销',
}

const formatCountdown = (seconds: number) => {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainder = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remainder}`
}

function CandidateInterviewInvitationPage() {
  const { token = '' } = useParams()
  const questionStartedAt = useRef(Date.now())
  const actionInFlight = useRef(false)
  const autoSkipAttemptedQuestionId = useRef<string | null>(null)
  const [invitation, setInvitation] = useState<PublicInterviewInvitation | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [runtime, setRuntime] = useState<InterviewRuntime | null>(null)
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(true)
  const [runtimeLoading, setRuntimeLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const accessStorageKey = invitation
    ? `interviewpilot:candidate-access:${invitation.invitation_id}`
    : null

  const loadRuntime = async (
    invitationId: string,
    candidateToken: string,
    showLoading = true,
  ) => {
    if (showLoading) setRuntimeLoading(true)
    try {
      const result = await getPublicInterviewRuntime(invitationId, candidateToken)
      setRuntime(result)
      setAccessToken(candidateToken)
      if (result.question_timed_out) message.warning('上一题已超时，已进入下一题')
      setError(null)
      return true
    } catch (requestError) {
      sessionStorage.removeItem(`interviewpilot:candidate-access:${invitationId}`)
      setAccessToken(null)
      setRuntime(null)
      setError(getApiErrorMessage(requestError, '候选人面试凭证已失效，请重新验证'))
      return false
    } finally {
      if (showLoading) setRuntimeLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    getPublicInterviewInvitation(token)
      .then(async (result) => {
        setInvitation(result)
        const storedToken = sessionStorage.getItem(
          `interviewpilot:candidate-access:${result.invitation_id}`,
        )
        if (storedToken && !unavailableStatusText[result.status]) {
          await loadRuntime(result.invitation_id, storedToken)
        }
      })
      .catch((requestError) => {
        setError(getApiErrorMessage(requestError, '面试邀请加载失败'))
      })
      .finally(() => setLoading(false))
  }, [token])

  useEffect(() => {
    const askedAt = runtime?.current_question?.asked_at
    questionStartedAt.current = askedAt ? Date.parse(askedAt) : Date.now()
  }, [runtime?.current_question?.id, runtime?.current_question?.asked_at])

  useEffect(() => {
    const question = runtime?.current_question
    if (!invitation || !accessToken || runtime?.status !== 'IN_PROGRESS' || !question) return
    const timeLimitSeconds = runtime.question_time_limit_seconds
    if (!timeLimitSeconds) {
      setRemainingSeconds(0)
      return
    }
    const askedAt = question.asked_at ? Date.parse(question.asked_at) : Date.now()
    const deadline = askedAt + timeLimitSeconds * 1000
    const updateCountdown = () => {
      const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
      setRemainingSeconds(remaining)
      if (
        remaining === 0
        && !actionInFlight.current
        && autoSkipAttemptedQuestionId.current !== question.id
      ) {
        autoSkipAttemptedQuestionId.current = question.id
        actionInFlight.current = true
        setSubmitting(true)
        skipPublicInterviewQuestion(
          invitation.invitation_id,
          question.id,
          accessToken,
        )
          .then((result) => {
            setRuntime(result)
            setAnswer('')
            message.warning('当前问题已超时，已进入下一题')
          })
          .catch((requestError) => {
            message.error(getApiErrorMessage(requestError, '超时自动跳题失败'))
          })
          .finally(() => {
            actionInFlight.current = false
            setSubmitting(false)
          })
      }
    }
    updateCountdown()
    const timer = window.setInterval(updateCountdown, 1000)
    return () => window.clearInterval(timer)
  }, [runtime?.status, runtime?.current_question?.id, runtime?.current_question?.asked_at, runtime?.question_time_limit_seconds, invitation?.invitation_id, accessToken])

  const verify = async (values: InterviewInvitationVerifyRequest) => {
    if (!invitation) return
    setSubmitting(true)
    try {
      const access = await verifyPublicInterviewInvitation(token, values)
      const storageKey = `interviewpilot:candidate-access:${access.invitation_id}`
      sessionStorage.setItem(storageKey, access.access_token)
      setAccessToken(access.access_token)
      setError(null)
      await loadRuntime(access.invitation_id, access.access_token)
      message.success('身份验证成功')
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '身份验证失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const begin = async () => {
    if (!invitation || !accessToken || actionInFlight.current) return
    actionInFlight.current = true
    setSubmitting(true)
    try {
      setRuntime(await startPublicInterview(invitation.invitation_id, accessToken))
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '面试启动失败'))
    } finally {
      actionInFlight.current = false
      setSubmitting(false)
    }
  }

  const submit = async () => {
    if (
      !invitation
      || !accessToken
      || !runtime?.current_question
      || !answer.trim()
      || actionInFlight.current
    ) return
    actionInFlight.current = true
    setSubmitting(true)
    try {
      const result = await submitPublicInterviewAnswer(
        invitation.invitation_id,
        runtime.current_question.id,
        {
          content: answer.trim(),
          duration_seconds: Math.max(
            0,
            Math.round((Date.now() - questionStartedAt.current) / 1000),
          ),
        },
        accessToken,
      )
      setAnswer('')
      setRuntime(result)
      if (result.question_timed_out) message.warning('当前问题已超时，回答未提交')
      else if (result.follow_up_generated) message.info('面试官进行了追问')
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '回答提交失败'))
    } finally {
      actionInFlight.current = false
      setSubmitting(false)
    }
  }

  const skip = () => {
    if (!invitation || !accessToken || !runtime?.current_question) return
    const questionId = runtime.current_question.id
    Modal.confirm({
      title: '跳过当前问题？',
      content: '该问题将记录为已跳过。',
      okText: '跳过',
      cancelText: '取消',
      onOk: async () => {
        if (actionInFlight.current) return
        actionInFlight.current = true
        setSubmitting(true)
        try {
          setRuntime(await skipPublicInterviewQuestion(
            invitation.invitation_id,
            questionId,
            accessToken,
          ))
          setAnswer('')
        } catch (requestError) {
          message.error(getApiErrorMessage(requestError, '问题跳过失败'))
        } finally {
          actionInFlight.current = false
          setSubmitting(false)
        }
      },
    })
  }

  const finish = () => {
    if (!invitation || !accessToken) return
    Modal.confirm({
      title: '提前结束面试？',
      content: '尚未回答的问题将记录为已跳过，提交后不能继续作答。',
      okText: '结束面试',
      okButtonProps: { danger: true },
      cancelText: '继续面试',
      onOk: async () => {
        if (actionInFlight.current) return
        actionInFlight.current = true
        setSubmitting(true)
        try {
          setRuntime(await finishPublicInterview(invitation.invitation_id, accessToken))
          setAnswer('')
          if (accessStorageKey) sessionStorage.removeItem(accessStorageKey)
        } catch (requestError) {
          message.error(getApiErrorMessage(requestError, '面试结束失败'))
        } finally {
          actionInFlight.current = false
          setSubmitting(false)
        }
      },
    })
  }

  if (loading) {
    return <main className="candidate-invitation-page candidate-invitation-loading"><Spin size="large" /></main>
  }
  if (!invitation) {
    return (
      <main className="candidate-invitation-page candidate-invitation-loading">
        <Alert type="error" showIcon message="无法打开面试邀请" description={error ?? '邀请不存在'} />
      </main>
    )
  }

  const unavailableText = invitation.status === 'COMPLETED'
    ? invitation.decision === 'HIRED'
      ? '恭喜，你已通过本次面试'
      : invitation.decision === 'REJECTED'
        ? '很遗憾，你未通过本次面试'
        : '面试已完成，结果待企业公布'
    : unavailableStatusText[invitation.status]
  const progress = runtime?.max_question_count
    ? Math.round((runtime.completed_question_count / runtime.max_question_count) * 100)
    : 0

  return (
    <main className="candidate-invitation-page">
      <header className="candidate-invitation-header">
        <div className="topbar-brand"><span className="brand-mark small">IP</span><strong>InterviewPilot</strong></div>
        <Tag color="blue">企业技术面试</Tag>
      </header>
      <div className="candidate-invitation-shell">
        <section className="candidate-invitation-summary">
          <div>
            <p className="eyebrow dark">CANDIDATE INTERVIEW</p>
            <Typography.Title level={2}>{invitation.job_title}</Typography.Title>
            <Typography.Paragraph type="secondary">{invitation.workspace_name}</Typography.Paragraph>
          </div>
          <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
            <Descriptions.Item label="候选人">{invitation.candidate_name}</Descriptions.Item>
            <Descriptions.Item label="验证邮箱">{invitation.masked_email}</Descriptions.Item>
            <Descriptions.Item label="计划时间">{invitation.scheduled_at ? new Date(invitation.scheduled_at).toLocaleString('zh-CN') : '未指定'}</Descriptions.Item>
            <Descriptions.Item label="邀请有效期">{new Date(invitation.expires_at).toLocaleString('zh-CN')}</Descriptions.Item>
          </Descriptions>
        </section>

        {unavailableText ? (
          <section className="candidate-interview-surface candidate-interview-result">
            {invitation.decision === 'REJECTED' ? <StopOutlined /> : <CheckCircleOutlined />}
            <Typography.Title level={4}>{unavailableText}</Typography.Title>
            {invitation.decided_at && <Typography.Paragraph type="secondary">结果公布时间：{new Date(invitation.decided_at).toLocaleString('zh-CN')}</Typography.Paragraph>}
          </section>
        ) : !accessToken || !runtime ? (
          <section className="candidate-interview-surface candidate-verification-panel">
            <Typography.Title level={4}>验证候选人身份</Typography.Title>
            <Typography.Paragraph type="secondary">请输入邀请邮箱和企业提供的 6 位访问码。</Typography.Paragraph>
            {error && <Alert type="warning" showIcon message={error} />}
            <Form<InterviewInvitationVerifyRequest>
              layout="vertical"
              size="large"
              onFinish={verify}
              requiredMark={false}
            >
              <Form.Item label="邀请邮箱" name="email" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
                <Input prefix={<MailOutlined />} autoComplete="email" />
              </Form.Item>
              <Form.Item label="访问码" name="access_code" rules={[{ required: true, len: 6, message: '请输入 6 位访问码' }]}>
                <Input prefix={<LockOutlined />} inputMode="numeric" maxLength={6} autoComplete="one-time-code" />
              </Form.Item>
              <Form.Item
                name="consent"
                valuePropName="checked"
                rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error('请先同意数据处理说明')) }]}
              >
                <Checkbox>我同意企业为本次招聘面试处理并保存我的回答与评估数据</Checkbox>
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={submitting}>验证并进入面试</Button>
            </Form>
          </section>
        ) : runtimeLoading ? (
          <section className="candidate-interview-surface candidate-interview-result"><Spin size="large" /></section>
        ) : runtime.status === 'READY' ? (
          <section className="candidate-interview-surface candidate-interview-result">
            <PlayCircleOutlined />
            <Typography.Title level={4}>面试已准备就绪</Typography.Title>
            <Typography.Paragraph type="secondary">开始后将动态生成第一道问题。</Typography.Paragraph>
            <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={submitting} onClick={begin}>开始面试</Button>
          </section>
        ) : runtime.status === 'COMPLETED' ? (
          <section className="candidate-interview-surface candidate-interview-result">
            <CheckCircleOutlined />
            <Typography.Title level={4}>回答已提交</Typography.Title>
            <Typography.Paragraph type="secondary">企业将根据本次面试生成评估结果，你可以关闭此页面。</Typography.Paragraph>
          </section>
        ) : runtime.status === 'IN_PROGRESS' && runtime.current_question ? (
          <section className="candidate-interview-surface">
            <div className="candidate-interview-toolbar">
              <div className="interview-progress-row">
                <Typography.Text type="secondary">{runtime.completed_question_count} / {runtime.max_question_count}</Typography.Text>
                <Progress percent={progress} showInfo={false} />
              </div>
              <Button danger type="text" icon={<StopOutlined />} disabled={submitting} onClick={finish}>结束面试</Button>
            </div>
            <div className="interview-question-heading">
              <div className="interview-question-meta">
                <Space wrap>
                  <Tag color={runtime.current_question.generated_by === 'FOLLOW_UP' ? 'gold' : 'blue'}>{questionTypeLabel[runtime.current_question.question_type] ?? runtime.current_question.question_type}</Tag>
                  <Tag>{difficultyLabel[runtime.current_question.difficulty] ?? runtime.current_question.difficulty}</Tag>
                  {runtime.current_question.competency && <Tag>{runtime.current_question.competency}</Tag>}
                </Space>
                <span className={`interview-countdown${runtime.question_time_limit_seconds && remainingSeconds <= 60 ? ' warning' : ''}`}>
                  <ClockCircleOutlined /> {runtime.question_time_limit_seconds ? formatCountdown(remainingSeconds) : '不限时'}
                </span>
              </div>
              <Typography.Title level={3}>{runtime.current_question.content}</Typography.Title>
            </div>
            <div className="interview-answer-area">
              <Input.TextArea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                autoSize={{ minRows: 8, maxRows: 16 }}
                maxLength={20000}
                showCount
                placeholder="请输入回答"
                disabled={submitting}
              />
              <div className="interview-answer-actions">
                <Button icon={<ForwardOutlined />} disabled={submitting} onClick={skip}>跳过</Button>
                <Button type="primary" icon={<SendOutlined />} loading={submitting} disabled={!answer.trim()} onClick={submit}>提交回答</Button>
              </div>
            </div>
          </section>
        ) : (
          <section className="candidate-interview-surface candidate-interview-result">
            <Spin />
            <Typography.Text type="secondary">正在准备下一题</Typography.Text>
          </section>
        )}
      </div>
    </main>
  )
}

export default CandidateInterviewInvitationPage
