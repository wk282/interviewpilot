import { RobotOutlined, WarningOutlined } from '@ant-design/icons'
import { Alert, Collapse, Empty, Space, Tag, Timeline, Typography } from 'antd'
import type { InterviewQuestion } from '../types/interview'

type TraceRecord = Record<string, unknown>

interface AgentExecutionTracePanelProps {
  questions: InterviewQuestion[]
}

const nodeLabels: Record<string, string> = {
  request_router: '请求路由',
  wait_for_answer: '断点恢复',
  answer_critic: 'Answer Critic',
  answer_critic_agent: 'Answer Critic',
  plan_reviser: 'Plan Reviser',
  plan_reviser_agent: 'Plan Reviser',
  interviewer_agent: 'Interviewer',
  retrieve: '本地混合检索',
  retrieval_grader: 'Retrieval Grader',
  rewrite_query: '查询改写',
  web_search: 'Web Search',
  fallback: '流程降级',
  crag_total: 'CRAG 完成',
}

const actionLabels: Record<string, string> = {
  ANSWER: '提交回答',
  SKIP: '跳过题目',
  ASK: '生成下一题',
  FINISH: '结束面试',
  FOLLOW_UP: '继续追问',
  INCREASE_DIFFICULTY: '提高难度',
  DECREASE_DIFFICULTY: '降低难度',
  SWITCH_TOPIC: '切换主题',
  END_INTERVIEW: '结束面试',
  sufficient: '证据充分',
  partial: '证据部分充分',
  irrelevant: '证据不相关',
}

const sourceLabels: Record<string, string> = {
  model: '模型决策',
  MODEL: '模型决策',
  local_fast_path: '本地快速判定',
  persisted_result: '复用持久化结果',
  fallback_rule: '规则降级',
  FALLBACK_RULE: '规则降级',
  invalid_output_fallback: '输出校验降级',
  empty_evidence_rule: '空证据规则',
}

function asRecord(value: unknown): TraceRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as TraceRecord
    : {}
}

function recordArray(value: unknown): TraceRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : []
}

function textValue(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  return null
}

function numericValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatLatency(value: unknown): string | null {
  const milliseconds = numericValue(value)
  if (milliseconds === null) return null
  return milliseconds < 1000
    ? `${Math.round(milliseconds)} ms`
    : `${(milliseconds / 1000).toFixed(2)} 秒`
}

function usageTokens(value: unknown): number {
  const total = asRecord(value).total_tokens
  return typeof total === 'number' && total > 0 ? total : 0
}

function maxMetric(rows: TraceRecord[], key: string): number | null {
  const values = rows
    .map((row) => numericValue(row[key]))
    .filter((value): value is number => value !== null)
  return values.length > 0 ? Math.max(...values) : null
}

function sourceTagColor(source: string): string {
  return source.toLowerCase().includes('fallback') || source.includes('RULE')
    ? 'gold'
    : source === 'local_fast_path'
      ? 'cyan'
      : 'green'
}

function nodeColor(node: TraceRecord): string {
  if (node.error || node.node === 'fallback') return 'red'
  const source = String(node.decision_source ?? node.grading_source ?? node.rewrite_source ?? '')
  if (source.toLowerCase().includes('fallback')) return 'orange'
  if (node.node === 'retrieval_grader') {
    return node.status === 'sufficient' ? 'green' : node.status === 'partial' ? 'orange' : 'red'
  }
  return 'blue'
}

function TraceNode({ node }: { node: TraceRecord }) {
  const nodeName = textValue(node.node) ?? 'unknown'
  const observability = asRecord(node.observability)
  const conductor = asRecord(observability.conductor)
  const reranker = asRecord(observability.reranker)
  const concurrency = asRecord(
    node.concurrency
      ?? observability.concurrency
      ?? conductor.concurrency
      ?? reranker.concurrency,
  )
  const source = textValue(
    node.decision_source
      ?? node.grading_source
      ?? node.rewrite_source
      ?? observability.source
      ?? conductor.source,
  )
  const model = textValue(node.model ?? observability.model ?? conductor.model)
  const action = textValue(node.next_action ?? node.action ?? node.resume_action ?? node.status)
  const routeReason = textValue(node.route_reason)
  const role = textValue(node.role)
  const latency = formatLatency(node.latency_ms ?? observability.latency_ms ?? observability.total_latency_ms)
  const usage = usageTokens(node.usage) || usageTokens(observability.usage) || usageTokens(conductor.usage)
  const confidence = numericValue(node.confidence)
  const score = numericValue(node.score)
  const resultCount = numericValue(node.result_count)
  const remainingBudget = numericValue(node.remaining_question_budget)
  const queueWait = numericValue(concurrency.queue_wait_ms)
  const activeAtAcquire = numericValue(concurrency.active_at_acquire)
  const concurrencyLimit = numericValue(concurrency.limit)
  const concurrencyTimedOut = concurrency.timed_out === true
  const tools = Array.isArray(node.tools) ? node.tools.map(String) : []
  const missingAspects = Array.isArray(node.missing_aspects) ? node.missing_aspects.map(String) : []
  const changeSet = asRecord(node.change_set)
  const query = textValue(node.query)
  const originalQuery = textValue(node.original_query)
  const rewrittenQuery = textValue(node.rewritten_query)
  const promptVersion = textValue(node.prompt_version ?? observability.prompt_version)

  return (
    <div className="agent-trace-node">
      <div className="agent-trace-node-heading">
        <Typography.Text strong>{nodeLabels[nodeName] ?? nodeName}</Typography.Text>
        {latency && <Typography.Text type="secondary">{latency}</Typography.Text>}
      </div>
      <Space wrap size={[4, 6]}>
        {action && <Tag color={nodeName === 'retrieval_grader' ? nodeColor(node) : 'blue'}>{actionLabels[action] ?? action}</Tag>}
        {routeReason && <Tag color="purple">路由到 {nodeLabels[routeReason] ?? routeReason}</Tag>}
        {source && <Tag color={sourceTagColor(source)}>{sourceLabels[source] ?? source}</Tag>}
        {score !== null && <Tag color={score >= 60 ? 'green' : 'gold'}>回答评分 {score.toFixed(0)}</Tag>}
        {confidence !== null && <Tag>置信度 {(confidence * 100).toFixed(0)}%</Tag>}
        {resultCount !== null && <Tag>召回 {resultCount} 条</Tag>}
        {remainingBudget !== null && <Tag>剩余 {remainingBudget} 题</Tag>}
        {queueWait !== null && queueWait >= 10 && <Tag color="gold">排队 {formatLatency(queueWait)}</Tag>}
        {activeAtAcquire !== null && concurrencyLimit !== null && <Tag>并发 {activeAtAcquire}/{concurrencyLimit}</Tag>}
        {concurrencyTimedOut && <Tag color="red" icon={<WarningOutlined />}>并发排队超时</Tag>}
        {usage > 0 && <Tag>{usage} Tokens</Tag>}
        {model && <Tag>{model}</Tag>}
        {promptVersion && <Tag>{promptVersion}</Tag>}
        {Boolean(node.error) && <Tag color="red" icon={<WarningOutlined />}>执行异常</Tag>}
      </Space>
      {role && <Typography.Paragraph className="agent-trace-copy" type="secondary">职责：{role}</Typography.Paragraph>}
      {tools.length > 0 && (
        <div className="agent-trace-tools">
          <Typography.Text type="secondary">工具</Typography.Text>
          <Space wrap size={[4, 4]}>{tools.map((tool) => <Tag key={tool}>{tool}</Tag>)}</Space>
        </div>
      )}
      {Object.keys(changeSet).length > 0 && (
        <Typography.Paragraph className="agent-trace-copy" type="secondary">
          计划变更：{Object.keys(changeSet).join('、')}
        </Typography.Paragraph>
      )}
      {missingAspects.length > 0 && (
        <Typography.Paragraph className="agent-trace-copy" type="secondary">
          证据缺口：{missingAspects.join('；')}
        </Typography.Paragraph>
      )}
      {query && <Typography.Paragraph className="agent-trace-copy" type="secondary">检索查询：{query}</Typography.Paragraph>}
      {originalQuery && <Typography.Paragraph className="agent-trace-copy" type="secondary">原查询：{originalQuery}</Typography.Paragraph>}
      {rewrittenQuery && <Typography.Paragraph className="agent-trace-copy" type="secondary">改写后：{rewrittenQuery}</Typography.Paragraph>}
    </div>
  )
}

function traceData(question: InterviewQuestion) {
  const metadata = asRecord(question.decision_metadata)
  const observability = asRecord(metadata.observability)
  const agentGraph = asRecord(observability.agent_graph)
  const agentTrace = recordArray(
    Array.isArray(agentGraph.trace) ? agentGraph.trace : observability.feedback_trace,
  )
  const retrievalTrace = recordArray(metadata.retrieval_trace)
  const retrievalGrade = asRecord(metadata.retrieval_grade)
  const sourceEvidence = recordArray(question.source_evidence)
  const conductor = asRecord(observability.conductor)
  const criticTokens = agentTrace.reduce((total, node) => (
    total + usageTokens(asRecord(node.observability).usage)
  ), 0)
  const retrievalTokens = retrievalTrace.reduce((total, node) => total + usageTokens(node.usage), 0)
  const tokenCount = usageTokens(conductor.usage) + criticTokens + retrievalTokens
  const fallback = (
    (typeof conductor.source === 'string' && conductor.source !== 'model')
    || agentTrace.some((node) => String(node.decision_source).includes('FALLBACK'))
    || retrievalTrace.some((node) => String(node.grading_source ?? node.rewrite_source).includes('fallback') || Boolean(node.error))
    || Boolean(observability.single_question_guard)
  )
  return {
    agentTrace,
    retrievalTrace,
    retrievalGrade,
    evidenceCount: sourceEvidence.length,
    bestFusionScore: maxMetric(sourceEvidence, 'fusion_score'),
    bestVectorScore: maxMetric(sourceEvidence, 'vector_similarity'),
    bestBm25Score: maxMetric(sourceEvidence, 'bm25_score'),
    bestTrigramScore: maxMetric(sourceEvidence, 'trigram_similarity'),
    bestRerankScore: maxMetric(sourceEvidence, 'rerank_score'),
    tokenCount,
    fallback,
    totalLatency: formatLatency(observability.activation_total_latency_ms ?? observability.total_latency_ms),
    adaptiveAction: textValue(metadata.adaptive_action),
    reason: textValue(metadata.reason),
  }
}

export default function AgentExecutionTracePanel({ questions }: AgentExecutionTracePanelProps) {
  const turns = questions
    .map((question) => ({ question, trace: traceData(question) }))
    .filter(({ trace }) => trace.agentTrace.length > 0 || trace.retrievalTrace.length > 0)
  const fallbackCount = turns.filter(({ trace }) => trace.fallback).length
  const totalTokens = turns.reduce((total, { trace }) => total + trace.tokenCount, 0)

  return (
    <section className="agent-trace-panel">
      <Collapse
        className="agent-trace-collapse"
        items={[{
          key: 'agent-execution-trace',
          label: (
            <div className="agent-trace-panel-heading">
              <span><RobotOutlined /> Agent 执行轨迹</span>
              <Space wrap size={[4, 4]}>
                <Tag>{turns.length} 轮已记录</Tag>
                {totalTokens > 0 && <Tag>{totalTokens} Tokens</Tag>}
                {fallbackCount > 0 && <Tag color="gold">{fallbackCount} 轮降级</Tag>}
              </Space>
            </div>
          ),
          children: turns.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="面试开始后将在这里记录 Agent 路由和检索过程" />
          ) : (
            <div className="agent-trace-turns">
              <Alert
                type="info"
                showIcon
                message="这里展示结构化执行记录，不包含隐藏推理、完整 Prompt 或候选人作答正文。"
              />
              {turns.map(({ question, trace }) => {
                const gradeStatus = textValue(trace.retrievalGrade.status)
                const gradeConfidence = numericValue(trace.retrievalGrade.confidence)
                return (
                  <details className="agent-trace-turn" key={question.id}>
                    <summary>
                      <div className="agent-trace-turn-summary">
                        <div>
                          <strong>第 {question.order_no} 题 · {question.competency || question.question_type}</strong>
                          <Typography.Text type="secondary">{question.content}</Typography.Text>
                        </div>
                        <Space wrap size={[4, 4]}>
                          <Tag>{question.difficulty}</Tag>
                          {gradeStatus && <Tag color={gradeStatus === 'sufficient' ? 'green' : gradeStatus === 'partial' ? 'gold' : 'red'}>{actionLabels[gradeStatus] ?? gradeStatus}</Tag>}
                          {gradeConfidence !== null && <Tag>检索置信度 {(gradeConfidence * 100).toFixed(0)}%</Tag>}
                          {trace.adaptiveAction && <Tag color="purple">{actionLabels[trace.adaptiveAction] ?? trace.adaptiveAction}</Tag>}
                          {trace.totalLatency && <Tag color="blue">{trace.totalLatency}</Tag>}
                          {trace.tokenCount > 0 && <Tag>{trace.tokenCount} Tokens</Tag>}
                          {trace.fallback && <Tag color="gold">存在降级</Tag>}
                        </Space>
                      </div>
                    </summary>
                    <div className="agent-trace-turn-body">
                      {trace.reason && <Typography.Paragraph className="agent-trace-reason">出题决策：{trace.reason}</Typography.Paragraph>}
                      <Space wrap size={[4, 6]} className="agent-trace-retrieval-scores">
                        <Typography.Text type="secondary">检索结果</Typography.Text>
                        <Tag>采用 {trace.evidenceCount} 条证据</Tag>
                        {trace.bestFusionScore !== null && <Tag color="blue">融合 {(trace.bestFusionScore * 100).toFixed(1)}%</Tag>}
                        {trace.bestVectorScore !== null && <Tag>向量 {(trace.bestVectorScore * 100).toFixed(1)}%</Tag>}
                        {trace.bestBm25Score !== null && <Tag>BM25 {trace.bestBm25Score.toFixed(3)}</Tag>}
                        {trace.bestTrigramScore !== null && <Tag>Trigram {(trace.bestTrigramScore * 100).toFixed(1)}%</Tag>}
                        {trace.bestRerankScore !== null && <Tag>重排 {trace.bestRerankScore.toFixed(4)}</Tag>}
                      </Space>
                      <div className="agent-trace-columns">
                        <div>
                          <Typography.Title level={5}>Agent 主流程</Typography.Title>
                          {trace.agentTrace.length > 0 ? (
                            <Timeline items={trace.agentTrace.map((node, index) => ({
                              key: `${String(node.node)}-${index}`,
                              color: nodeColor(node),
                              children: <TraceNode node={node} />,
                            }))} />
                          ) : <Typography.Text type="secondary">该轮没有 Agent 主流程记录</Typography.Text>}
                        </div>
                        <div>
                          <Typography.Title level={5}>CRAG 检索子图</Typography.Title>
                          {trace.retrievalTrace.length > 0 ? (
                            <Timeline items={trace.retrievalTrace.map((node, index) => ({
                              key: `${String(node.node)}-${index}`,
                              color: nodeColor(node),
                              children: <TraceNode node={node} />,
                            }))} />
                          ) : <Typography.Text type="secondary">该轮没有触发检索子图</Typography.Text>}
                        </div>
                      </div>
                    </div>
                  </details>
                )
              })}
            </div>
          ),
        }]}
      />
    </section>
  )
}
