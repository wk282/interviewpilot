# AI 成本与并发控制

## 目标

在不降低核心面试质量的前提下，限制无效模型调用、控制瞬时并发，并让等待时间和 Token 消耗可以被追踪。

## 成本控制策略

- Planner、Interviewer、Final Evaluator 使用主模型，保证规划、出题和终审质量。
- Answer Critic、Retrieval Grader、Query Rewrite 使用 Mini 模型。
- CRAG 证据达到数量与融合分数阈值时走本地快速判定，不调用模型 Grader。
- Query Rewrite 和 Web Search 均限制最多执行一次。
- 面试检索默认使用离线评测选定的 Profile，并关闭当前负收益的全局 Reranker。
- 文档 Embedding 按批次调用；上传文件通过 SHA-256 去重，避免重复解析与向量化。
- 面试设置最大题目数，Plan Reviser 可以提前结束已经充分验证的能力项。
- 逐轮记录 Token、节点耗时、降级来源与并发排队耗时。

## 并发闸门

所有 OpenAI 兼容的 Chat、Embedding 调用，以及启用时的 Reranker，统一通过
`app.services.ai_concurrency.ai_concurrency_slot` 获取执行槽位。

配置：

```env
MAX_CONCURRENCY=2
AI_CONCURRENCY_WAIT_TIMEOUT_SECONDS=30
```

- `MAX_CONCURRENCY`：单个 FastAPI 或 Celery 进程允许同时执行的 AI 请求数。
- `AI_CONCURRENCY_WAIT_TIMEOUT_SECONDS`：请求等待槽位的最长时间。
- 等待超时后，Interviewer、Critic 和 CRAG 会进入现有规则降级；Planner 和异步评估任务会进入 Celery 重试或失败处理。
- Celery 的 `worker_concurrency` 同步使用 `MAX_CONCURRENCY`，并保留 `worker_prefetch_multiplier=1`，避免任务被单个 Worker 过量预取。

## 可观测字段

节点的 `concurrency` 字段包含：

```json
{
  "operation": "interviewer",
  "model": "deepseek-v4-pro",
  "limit": 2,
  "queue_wait_ms": 18,
  "active_at_acquire": 2,
  "queued_ahead": 1,
  "held_ms": 1240,
  "timed_out": false
}
```

整场面试可观测接口会将排队耗时聚合为 `AI_QUEUE` 阶段，并统计实际发生排队的次数。企业端 Agent 执行轨迹可以查看单节点并发占用、排队时间和超时降级。

## 边界

当前 Semaphore 是进程内并发控制。单个 Backend 实例和单个 Celery Worker 实例可以受到约束，但多个 Backend 容器或多个 Worker 实例之间不会共享计数。

多副本生产部署还需要增加 Redis 分布式限流或带租约的分布式 Semaphore，并分别按用户、工作空间和高成本接口设置配额。

