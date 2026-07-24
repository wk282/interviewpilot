import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ForwardOutlined,
  PlayCircleOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Alert, Button, Empty, Input, Modal, Progress, Space, Spin, Tag, Typography, message } from 'antd'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  finishInterview,
  getInterviewRuntime,
  skipInterviewQuestion,
  startInterview,
  submitInterviewAnswer,
} from '../api/interviews'
import {
  finishAssignedInterview,
  getAssignedInterviewRuntime,
  skipAssignedInterviewQuestion,
  startAssignedInterview,
  submitAssignedInterviewAnswer,
} from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { InterviewRuntime } from '../types/interview'
import { getApiErrorMessage } from '../utils/apiError'
import {
  readInterviewAnswerDraft,
  removeInterviewAnswerDraft,
  removeInterviewAnswerDrafts,
  saveInterviewAnswerDraft,
} from '../utils/interviewAnswerDraft'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const formatCountdown = (seconds: number) => {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainder = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remainder}`
}

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

const criticActionLabel: Record<string, string> = {
  FOLLOW_UP: '继续追问',
  INCREASE_DIFFICULTY: '提高难度',
  DECREASE_DIFFICULTY: '降低难度',
  SWITCH_TOPIC: '切换能力点',
  END_INTERVIEW: '结束面试',
}

function InterviewExecutionPage() {
  const { interviewId = '' } = useParams()
  const workspace = getActiveWorkspace()
  const personal = workspace?.type === 'PERSONAL'
  const location = useLocation()
  const assignedInterview = location.pathname.includes('/candidate/enterprise-interviews/')
  const navigate = useNavigate()
  const questionStartedAt = useRef(Date.now())
  const actionInFlight = useRef(false)
  const autoSkipAttemptedQuestionId = useRef<string | null>(null)
  const [runtime, setRuntime] = useState<InterviewRuntime | null>(null)
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const draftScopeId = `interview:${interviewId}`
  const currentQuestionId = runtime?.current_question?.id ?? null

  useEffect(() => {
    setAnswer(
      currentQuestionId
        ? readInterviewAnswerDraft(draftScopeId, currentQuestionId)
        : '',
    )
  }, [draftScopeId, currentQuestionId])

  useEffect(() => {
    if (runtime?.status === 'COMPLETED') {
      removeInterviewAnswerDrafts(draftScopeId)
    }
  }, [draftScopeId, runtime?.status])

  const updateAnswer = (content: string) => {
    setAnswer(content)
    if (currentQuestionId) {
      saveInterviewAnswerDraft(draftScopeId, currentQuestionId, content)
    }
  }

  const fetchRuntime = () => {
    if (assignedInterview) return getAssignedInterviewRuntime(interviewId)
    if (!workspace) throw new Error('工作空间不存在')
    return getInterviewRuntime(workspace.id, interviewId)
  }

  const beginInterview = () => {
    if (assignedInterview) return startAssignedInterview(interviewId)
    if (!workspace) throw new Error('工作空间不存在')
    return startInterview(workspace.id, interviewId)
  }

  const submitAnswer = (questionId: string, content: string, durationSeconds: number) => {
    const request = { content, duration_seconds: durationSeconds }
    if (assignedInterview) return submitAssignedInterviewAnswer(interviewId, questionId, request)
    if (!workspace) throw new Error('工作空间不存在')
    return submitInterviewAnswer(workspace.id, interviewId, questionId, request)
  }

  const skipQuestion = (questionId: string) => {
    if (assignedInterview) return skipAssignedInterviewQuestion(interviewId, questionId)
    if (!workspace) throw new Error('工作空间不存在')
    return skipInterviewQuestion(workspace.id, interviewId, questionId)
  }

  const completeInterview = () => {
    if (assignedInterview) return finishAssignedInterview(interviewId)
    if (!workspace) throw new Error('工作空间不存在')
    return finishInterview(workspace.id, interviewId)
  }

  const loadRuntime = async (showLoading = true) => {
    if ((!workspace && !assignedInterview) || !interviewId) return
    if (showLoading) setLoading(true)
    try {
      const result = await fetchRuntime()
      setRuntime(result)
      if (result.question_timed_out) message.warning('上一题已超时，已进入下一题')
      setError(null)
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, '面试状态加载失败'))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => { void loadRuntime() }, [workspace?.id, interviewId])

  useEffect(() => {
    const askedAt = runtime?.current_question?.asked_at
    questionStartedAt.current = askedAt ? Date.parse(askedAt) : Date.now()
  }, [runtime?.current_question?.id, runtime?.current_question?.asked_at])

  useEffect(() => {
    const question = runtime?.current_question
    if ((!workspace && !assignedInterview) || runtime?.status !== 'IN_PROGRESS' || !question) return
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
        skipQuestion(question.id)
          .then((result) => {
            removeInterviewAnswerDraft(draftScopeId, question.id)
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
  }, [runtime?.status, runtime?.current_question?.id, runtime?.current_question?.asked_at, runtime?.question_time_limit_seconds, workspace?.id, interviewId, draftScopeId])

  useEffect(() => {
    if (runtime?.status !== 'IN_PROGRESS' || runtime.current_question) return
    const timer = window.setInterval(() => { void loadRuntime(false) }, 2000)
    return () => window.clearInterval(timer)
  }, [runtime?.status, runtime?.current_question?.id, workspace?.id, interviewId])

  useEffect(() => {
    if (!assignedInterview || runtime?.status !== 'COMPLETED' || runtime.decision) return
    const timer = window.setInterval(() => { void loadRuntime(false) }, 5000)
    return () => window.clearInterval(timer)
  }, [assignedInterview, runtime?.status, runtime?.decision, workspace?.id, interviewId])

  const begin = async () => {
    if ((!workspace && !assignedInterview) || actionInFlight.current) return
    actionInFlight.current = true
    setSubmitting(true)
    try {
      setRuntime(await beginInterview())
      setError(null)
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '面试启动失败'))
    } finally {
      actionInFlight.current = false
      setSubmitting(false)
    }
  }

  const submit = async () => {
    if ((!workspace && !assignedInterview) || !runtime?.current_question || !answer.trim() || actionInFlight.current) return
    actionInFlight.current = true
    setSubmitting(true)
    try {
      const result = await submitAnswer(
        runtime.current_question.id,
        answer.trim(),
        Math.max(0, Math.round((Date.now() - questionStartedAt.current) / 1000)),
      )
      removeInterviewAnswerDraft(draftScopeId, runtime.current_question.id)
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
    if ((!workspace && !assignedInterview) || !runtime?.current_question) return
    const questionId = runtime.current_question.id
    Modal.confirm({
      title: '跳过当前问题？',
      content: '该问题将记录为已跳过。',
      okText: '跳过',
      cancelText: '取消',
      onOk: async () => {
        if (actionInFlight.current) return
        actionInFlight.current = true
        try {
          setSubmitting(true)
          setRuntime(await skipQuestion(questionId))
          removeInterviewAnswerDraft(draftScopeId, questionId)
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
    if (!workspace && !assignedInterview) return
    Modal.confirm({
      title: '提前结束面试？',
      content: '尚未回答的问题将记录为已跳过。',
      okText: '结束面试',
      okButtonProps: { danger: true },
      cancelText: '继续面试',
      onOk: async () => {
        if (actionInFlight.current) return
        actionInFlight.current = true
        try {
          setSubmitting(true)
          setRuntime(await completeInterview())
          removeInterviewAnswerDrafts(draftScopeId)
          setAnswer('')
        } catch (requestError) {
          message.error(getApiErrorMessage(requestError, '面试结束失败'))
        } finally {
          actionInFlight.current = false
          setSubmitting(false)
        }
      },
    })
  }

  const interviewsPath = assignedInterview
    ? '/candidate/messages'
    : personal ? '/candidate/interviews' : '/enterprise/interviews'
  const progress = runtime?.max_question_count
    ? Math.round((runtime.completed_question_count / runtime.max_question_count) * 100)
    : 0

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        {personal ? <CandidateSidebar /> : <EnterpriseSidebar workspace={workspace} />}
        <section className="dashboard-main">
          <Button type="link" icon={<ArrowLeftOutlined />} className="page-back" onClick={() => navigate(interviewsPath)}>返回面试列表</Button>
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">TEXT INTERVIEW</p>
              <Typography.Title level={2}>技术面试</Typography.Title>
              <Typography.Paragraph type="secondary">{runtime?.status ?? 'LOADING'}</Typography.Paragraph>
            </div>
            {runtime?.status === 'IN_PROGRESS' && (
              <Button danger icon={<StopOutlined />} disabled={submitting} onClick={finish}>结束面试</Button>
            )}
          </div>

          {error && <Alert className="resume-alert" type="error" showIcon message={error} action={<Button onClick={() => loadRuntime()}>重试</Button>} />}

          <section className="content-panel interview-runtime-panel">
            {loading ? (
              <div className="interview-runtime-loading"><Spin size="large" /></div>
            ) : runtime?.status === 'READY' ? (
              <div className="interview-start-state">
                <PlayCircleOutlined />
                <Typography.Title level={4}>面试计划已就绪</Typography.Title>
                <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={submitting} onClick={begin}>开始面试</Button>
              </div>
            ) : runtime?.status === 'COMPLETED' ? (
              <div className="interview-complete-state">
                <CheckCircleOutlined />
                <Typography.Title level={4}>
                  {assignedInterview && runtime.decision === 'HIRED'
                    ? '恭喜，你已通过本次面试'
                    : assignedInterview && runtime.decision === 'REJECTED'
                      ? '很遗憾，你未通过本次面试'
                      : assignedInterview && ['PENDING', 'GENERATING'].includes(runtime.evaluation_status ?? '')
                        ? '面试已完成，正在生成评估'
                        : assignedInterview
                          ? '面试已完成，结果待企业公布'
                          : '面试已完成'}
                </Typography.Title>
                <Typography.Text type="secondary">已处理 {runtime.completed_question_count} 道问题</Typography.Text>
                {runtime.decided_at && <Typography.Text type="secondary">结果公布时间：{new Date(runtime.decided_at).toLocaleString('zh-CN')}</Typography.Text>}
                <Space>
                  <Button onClick={() => navigate(interviewsPath)}>返回面试列表</Button>
                  {!assignedInterview && <Button type="primary" onClick={() => navigate(`${interviewsPath}/${interviewId}/report`)}>查看评估报告</Button>}
                </Space>
              </div>
            ) : runtime?.status === 'IN_PROGRESS' && runtime.current_question ? (
              <div className="interview-question-view">
                <div className="interview-progress-row">
                  <Typography.Text type="secondary">{runtime.completed_question_count} / {runtime.max_question_count}</Typography.Text>
                  <Progress percent={progress} showInfo={false} />
                </div>
                {runtime.last_turn_feedback && (
                  <div className="interview-turn-feedback">
                    <div className="interview-turn-feedback-header">
                      <strong>上一轮反馈 · {runtime.last_turn_feedback.score.toFixed(0)} 分</strong>
                      <Space wrap>
                        <Tag color="blue">{criticActionLabel[runtime.last_turn_feedback.next_action] ?? runtime.last_turn_feedback.next_action}</Tag>
                        {runtime.adaptive_plan_version && <Tag>计划 v{runtime.adaptive_plan_version}</Tag>}
                      </Space>
                    </div>
                    <Typography.Paragraph>{runtime.last_turn_feedback.reason}</Typography.Paragraph>
                    {runtime.last_turn_feedback.knowledge_gaps.length > 0 && (
                      <Space wrap>
                        {runtime.last_turn_feedback.knowledge_gaps.map((item) => <Tag key={item}>{item}</Tag>)}
                      </Space>
                    )}
                  </div>
                )}
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
                    onChange={(event) => updateAnswer(event.target.value)}
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
              </div>
            ) : runtime?.status === 'IN_PROGRESS' ? (
              <div className="interview-runtime-loading"><Spin /><Typography.Text type="secondary">正在准备下一题</Typography.Text></div>
            ) : (
              <Empty description="当前面试不可执行" />
            )}
          </section>
        </section>
      </div>
    </main>
  )
}

export default InterviewExecutionPage
