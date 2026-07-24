import { useEffect, useState } from 'react'
import { ArrowLeftOutlined, CheckOutlined, DownloadOutlined, FileDoneOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Input, List, Modal, Progress, Space, Spin, Tag, Typography, message } from 'antd'
import axios from 'axios'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createInterviewEvaluation,
  createInterviewQualityAudit,
  downloadInterviewEvaluationPdf,
  getInterviewEvaluation,
  getInterviewQualityAudit,
} from '../api/interviews'
import { createInterviewDecision, getInterviewDecision } from '../api/recruitment'
import AppHeader from '../components/AppHeader'
import CandidateSidebar from '../components/CandidateSidebar'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { InterviewEvaluation, InterviewQualityAudit } from '../types/interview'
import type { InterviewDecision } from '../types/recruitment'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const dimensionLabel: Record<string, string> = {
  technical_depth: '技术深度',
  project_authenticity: '项目可信度',
  problem_solving: '问题解决',
  system_design: '系统设计',
  communication: '表达沟通',
}

const recommendationLabel: Record<string, string> = {
  STRONG_HIRE: '强烈推荐',
  HIRE: '推荐',
  HOLD: '待定',
  NO_HIRE: '不推荐',
  NOT_APPLICABLE: '模拟面试',
}

const criticActionLabel: Record<string, string> = {
  FOLLOW_UP: '继续追问',
  INCREASE_DIFFICULTY: '提高难度',
  DECREASE_DIFFICULTY: '降低难度',
  SWITCH_TOPIC: '切换能力点',
  END_INTERVIEW: '结束面试',
}

const difficultyLabel: Record<string, string> = {
  EASY: '基础',
  MEDIUM: '进阶',
  HARD: '深入',
}

function InterviewReportPage() {
  const { interviewId = '' } = useParams()
  const workspace = getActiveWorkspace()
  const personal = workspace?.type === 'PERSONAL'
  const navigate = useNavigate()
  const [evaluation, setEvaluation] = useState<InterviewEvaluation | null>(null)
  const [qualityAudit, setQualityAudit] = useState<InterviewQualityAudit | null>(null)
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditGenerating, setAuditGenerating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [interviewDecision, setInterviewDecision] = useState<InterviewDecision | null>(null)
  const [decisionStatus, setDecisionStatus] = useState<'REJECTED' | 'HIRED' | null>(null)
  const [decisionNote, setDecisionNote] = useState('')
  const [decisionSaving, setDecisionSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadEvaluation = async (showLoading = true) => {
    if (!workspace || !interviewId) return
    if (showLoading) setLoading(true)
    try {
      setEvaluation(await getInterviewEvaluation(workspace.id, interviewId))
      setError(null)
    } catch (requestError) {
      if (axios.isAxiosError(requestError) && requestError.response?.status === 404) {
        setEvaluation(null)
        setError(null)
      } else {
        setError(getApiErrorMessage(requestError, '评估报告加载失败'))
      }
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => { void loadEvaluation() }, [workspace?.id, interviewId])
  useEffect(() => {
    if (!workspace || !interviewId || evaluation?.status !== 'COMPLETED') return
    setAuditLoading(true)
    setQualityAudit(null)
    getInterviewQualityAudit(workspace.id, interviewId)
      .then(setQualityAudit)
      .catch((requestError) => {
        if (!axios.isAxiosError(requestError) || requestError.response?.status !== 404) {
          message.error(getApiErrorMessage(requestError, '业务质量审计加载失败'))
        }
      })
      .finally(() => setAuditLoading(false))
  }, [workspace?.id, interviewId, evaluation?.status])
  useEffect(() => {
    if (!workspace || personal || !interviewId) return
    getInterviewDecision(workspace.id, interviewId)
      .then(setInterviewDecision)
      .catch((requestError) => {
        if (!axios.isAxiosError(requestError) || requestError.response?.status !== 404) {
          message.error(getApiErrorMessage(requestError, '面试决策信息加载失败'))
        }
      })
  }, [workspace?.id, interviewId, personal])

  const processing = evaluation?.status === 'PENDING' || evaluation?.status === 'GENERATING'
  useEffect(() => {
    if (!processing) return
    const timer = window.setInterval(() => { void loadEvaluation(false) }, 3000)
    return () => window.clearInterval(timer)
  }, [processing, workspace?.id, interviewId])

  const generate = async () => {
    if (!workspace) return
    setGenerating(true)
    try {
      setEvaluation(await createInterviewEvaluation(workspace.id, interviewId))
      setError(null)
      message.success('评估任务已提交')
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '评估任务提交失败'))
    } finally {
      setGenerating(false)
    }
  }

  const submitDecision = async () => {
    if (!workspace || !interviewDecision || !decisionStatus) return
    setDecisionSaving(true)
    try {
      const updated = await createInterviewDecision(
        workspace.id,
        interviewId,
        decisionStatus,
        decisionNote,
      )
      setInterviewDecision(updated)
      setDecisionStatus(null)
      setDecisionNote('')
      message.success('面试决策已保存')
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '招聘决策保存失败'))
    } finally {
      setDecisionSaving(false)
    }
  }

  const generateQualityAudit = async () => {
    if (!workspace) return
    setAuditGenerating(true)
    try {
      setQualityAudit(await createInterviewQualityAudit(workspace.id, interviewId))
      message.success('业务质量审计已生成')
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '业务质量审计生成失败'))
    } finally {
      setAuditGenerating(false)
    }
  }

  const downloadReport = async () => {
    if (!workspace) return
    setDownloading(true)
    try {
      await downloadInterviewEvaluationPdf(workspace.id, interviewId)
      message.success('评估报告下载已开始')
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '评估报告下载失败'))
    } finally {
      setDownloading(false)
    }
  }

  const interviewsPath = personal ? '/candidate/interviews' : '/enterprise/interviews'

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        {personal ? <CandidateSidebar /> : <EnterpriseSidebar workspace={workspace} />}
        <section className="dashboard-main">
          <Button type="link" icon={<ArrowLeftOutlined />} className="page-back" onClick={() => navigate(interviewsPath)}>返回面试列表</Button>
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">EVALUATION</p>
              <Typography.Title level={2}>面试评估报告</Typography.Title>
              <Typography.Paragraph type="secondary">{evaluation?.status ?? 'NOT_GENERATED'}</Typography.Paragraph>
            </div>
            <Space>
              {evaluation?.status === 'COMPLETED' && <Button icon={<DownloadOutlined />} loading={downloading} onClick={() => void downloadReport()}>下载 PDF</Button>}
              {evaluation?.status === 'FAILED' && <Button icon={<ReloadOutlined />} loading={generating} onClick={generate}>重新生成</Button>}
              {evaluation?.status === 'COMPLETED' && !qualityAudit && !auditLoading && <Button loading={auditGenerating} onClick={generateQualityAudit}>生成质量审计</Button>}
              {!personal && interviewDecision?.decision && <Tag color={interviewDecision.decision === 'HIRED' ? 'green' : 'red'}>{interviewDecision.decision === 'HIRED' ? '已通过' : '未通过'}</Tag>}
              {!personal && evaluation?.status === 'COMPLETED' && interviewDecision && !interviewDecision.decision && !['REJECTED', 'HIRED', 'WITHDRAWN'].includes(interviewDecision.application_status ?? '') && (
                <>
                  <Button danger icon={<StopOutlined />} onClick={() => setDecisionStatus('REJECTED')}>不通过</Button>
                  <Button type="primary" icon={<CheckOutlined />} onClick={() => setDecisionStatus('HIRED')}>通过面试</Button>
                </>
              )}
            </Space>
          </div>

          {error && <Alert className="resume-alert" type="error" showIcon message={error} />}

          <section className="content-panel interview-report-panel">
            {loading ? (
              <div className="interview-runtime-loading"><Spin size="large" /></div>
            ) : !evaluation ? (
              <Empty description="尚未生成评估报告">
                <Button type="primary" icon={<FileDoneOutlined />} loading={generating} onClick={generate}>生成评估报告</Button>
              </Empty>
            ) : processing ? (
              <div className="interview-runtime-loading"><Spin size="large" /><Typography.Text type="secondary">正在分析面试回答</Typography.Text></div>
            ) : evaluation.status === 'FAILED' ? (
              <Alert type="error" showIcon message="评估生成失败" description={evaluation.error_message} />
            ) : (
              <div className="interview-report-content">
                <section className="report-overview">
                  <div className="report-score">
                    <strong>{evaluation.overall_score?.toFixed(1) ?? '-'}</strong>
                    <span>综合得分</span>
                  </div>
                  <div className="report-dimensions">
                    {Object.entries(evaluation.dimension_scores).map(([key, value]) => (
                      <div className="report-dimension" key={key}>
                        <span>{dimensionLabel[key] ?? key}</span>
                        <Progress percent={Math.round(value)} size="small" />
                      </div>
                    ))}
                  </div>
                  {evaluation.recommendation && <Tag color="blue">{recommendationLabel[evaluation.recommendation] ?? evaluation.recommendation}</Tag>}
                </section>

                {qualityAudit && (
                  <section className="quality-audit-section">
                    <div className="quality-audit-heading">
                      <div>
                        <Typography.Title level={5}>系统业务质量审计</Typography.Title>
                        <Typography.Text type="secondary">{qualityAudit.audit_version} · {new Date(qualityAudit.generated_at).toLocaleString('zh-CN')}</Typography.Text>
                      </div>
                      <Tag color={qualityAudit.passed ? 'green' : 'red'}>{qualityAudit.passed ? '质量门禁通过' : '质量门禁未通过'}</Tag>
                    </div>
                    <div className="quality-audit-metrics">
                      <div><span>能力覆盖率</span><strong>{Math.round(Number(qualityAudit.metrics.competency_coverage_rate ?? 0) * 100)}%</strong></div>
                      <div><span>Critic 覆盖率</span><strong>{Math.round(Number(qualityAudit.metrics.critic_coverage_rate ?? 0) * 100)}%</strong></div>
                      <div><span>动态执行一致率</span><strong>{Math.round(Number(qualityAudit.metrics.adaptive_compliance_rate ?? 0) * 100)}%</strong></div>
                      <div><span>报告证据有效率</span><strong>{Math.round(Number(qualityAudit.metrics.report_evidence_validity_rate ?? 0) * 100)}%</strong></div>
                    </div>
                    {qualityAudit.warnings.length > 0 && (
                      <Alert type="warning" showIcon message="审计发现问题" description={qualityAudit.warnings.join('；')} />
                    )}
                    <List
                      size="small"
                      dataSource={qualityAudit.quality_gates}
                      renderItem={(gate) => (
                        <List.Item>
                          <span>{gate.label}</span>
                          <Space>
                            {!gate.required && <Tag>观察项</Tag>}
                            <Tag color={gate.passed ? 'green' : 'red'}>{gate.passed ? '通过' : '未通过'}</Tag>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </section>
                )}

                <section className="report-findings">
                  <div><Typography.Title level={5}>优势</Typography.Title><ul>{evaluation.strengths.map((item, index) => <li key={index}>{item}</li>)}</ul></div>
                  <div><Typography.Title level={5}>改进项</Typography.Title><ul>{evaluation.weaknesses.map((item, index) => <li key={index}>{item}</li>)}</ul></div>
                </section>

                <section className="report-narrative">
                  <Typography.Title level={5}>综合评价</Typography.Title>
                  <p>{evaluation.report_text}</p>
                </section>

                {!personal && interviewDecision?.decided_at && (
                  <section className="report-narrative">
                    <Typography.Title level={5}>招聘决策记录</Typography.Title>
                    <p>{interviewDecision.decision === 'HIRED' ? '通过' : '不通过'} · {interviewDecision.decided_by_name ?? '企业成员'} · {new Date(interviewDecision.decided_at).toLocaleString('zh-CN')}</p>
                    {interviewDecision.internal_note && <p>{interviewDecision.internal_note}</p>}
                  </section>
                )}

                <section className="report-evidence">
                  <Typography.Title level={5}>逐轮 Critic 决策</Typography.Title>
                  <List
                    dataSource={evaluation.turn_critiques}
                    locale={{ emptyText: '该面试没有逐轮 Critic 记录' }}
                    renderItem={(item, index) => (
                      <List.Item>
                        <div className="report-evidence-item">
                          <div>
                            <Tag>第 {index + 1} 轮</Tag>
                            <Tag color="blue">{item.score.toFixed(0)} 分</Tag>
                            <Tag>{criticActionLabel[item.next_action] ?? item.next_action}</Tag>
                            {item.decision_source === 'FALLBACK_RULE' && <Tag color="orange">规则兜底</Tag>}
                          </div>
                          <p>{item.reason}</p>
                          {item.answer_evidence.map((evidence, evidenceIndex) => (
                            <blockquote key={evidenceIndex}>{evidence}</blockquote>
                          ))}
                          {item.knowledge_gaps.length > 0 && (
                            <Space wrap>{item.knowledge_gaps.map((gap) => <Tag key={gap}>{gap}</Tag>)}</Space>
                          )}
                        </div>
                      </List.Item>
                    )}
                  />
                </section>

                <section className="report-evidence">
                  <Typography.Title level={5}>动态计划修订</Typography.Title>
                  <List
                    dataSource={evaluation.plan_revisions}
                    locale={{ emptyText: '该面试没有动态计划修订记录' }}
                    renderItem={(item) => (
                      <List.Item>
                        <div className="report-evidence-item">
                          <div>
                            <Tag>计划 v{item.version}</Tag>
                            <Tag color="blue">{criticActionLabel[item.action] ?? item.action}</Tag>
                            {item.target_difficulty && <Tag>{difficultyLabel[item.target_difficulty] ?? item.target_difficulty}</Tag>}
                          </div>
                          {item.target_competency && <strong>下一能力点：{item.target_competency}</strong>}
                          <p>{item.rationale}</p>
                          <p>剩余题目预算：{item.remaining_question_budget}</p>
                          {Object.keys(item.competency_budget).length > 0 && (
                            <Space wrap>
                              <span>能力预算：</span>
                              {Object.entries(item.competency_budget).map(([competency, count]) => (
                                <Tag key={competency}>{competency} {count} 题</Tag>
                              ))}
                            </Space>
                          )}
                          {item.covered_competencies.length > 0 && (
                            <Space wrap><span>已覆盖：</span>{item.covered_competencies.map((competency) => <Tag key={competency}>{competency}</Tag>)}</Space>
                          )}
                        </div>
                      </List.Item>
                    )}
                  />
                </section>

                <section className="report-evidence">
                  <Typography.Title level={5}>回答证据</Typography.Title>
                  <List
                    dataSource={evaluation.evidence}
                    renderItem={(item) => (
                      <List.Item>
                        <div className="report-evidence-item">
                          <div><Tag>{dimensionLabel[item.dimension] ?? item.dimension}</Tag><Tag color="blue">{item.score.toFixed(0)} 分</Tag></div>
                          <strong>{item.question}</strong>
                          <blockquote>{item.answer_excerpt}</blockquote>
                          <p>{item.finding}</p>
                        </div>
                      </List.Item>
                    )}
                  />
                </section>
              </div>
            )}
          </section>
        </section>
      </div>

      <Modal
        title={decisionStatus === 'HIRED' ? '确认候选人通过面试' : '确认候选人未通过面试'}
        open={decisionStatus !== null}
        okText={decisionStatus === 'HIRED' ? '确认通过' : '确认不通过'}
        okButtonProps={{ danger: decisionStatus === 'REJECTED' }}
        confirmLoading={decisionSaving}
        onOk={() => void submitDecision()}
        onCancel={() => { setDecisionStatus(null); setDecisionNote('') }}
      >
        <Typography.Paragraph type="secondary">内部备注仅企业可见；外部候选人可通过原邀请链接查看结果。</Typography.Paragraph>
        <Input.TextArea
          value={decisionNote}
          onChange={(event) => setDecisionNote(event.target.value)}
          maxLength={5000}
          showCount
          autoSize={{ minRows: 4, maxRows: 8 }}
          placeholder="填写内部决策依据（可选）"
        />
      </Modal>
    </main>
  )
}

export default InterviewReportPage
