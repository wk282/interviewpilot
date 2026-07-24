# AI 链路可观测性

## 目标

逐题记录 AI 工作流各节点的耗时、模型、Token 用量、路由结果与降级来源，用于定位面试生成缓慢、接口失败和成本异常。

## 记录范围

- CRAG：本地检索、Retrieval Grader、查询改写、Tavily 搜索和 CRAG 总耗时。
- Answer Critic：模型耗时、Token、决策来源和失败降级。
- Plan Reviser：规则修正耗时和最终动作。
- Conductor：问题生成耗时、Token、模型输出或规则兜底。
- AI 并发队列：模型调用排队耗时、槽位占用和排队超时。
- 整轮链路：从处理上一轮回答到生成下一题的总耗时。

## 持久化位置

- `interview_question.decision_metadata.observability`：整轮、CRAG、Conductor 和反馈链路数据。
- `interview_question.decision_metadata.retrieval_trace`：CRAG 每个节点的详细 Trace。
- `interview_plan_revision.workflow_trace`：Critic 与 Plan Reviser Trace。

这些字段均为现有 JSONB 字段，本阶段不新增数据库表或迁移。

## 页面入口

进入“面试管理”，打开某场面试的“面试计划”，在“已生成题目与 AI 耗时”中查看：

- 总耗时
- Critic 耗时
- CRAG 耗时
- Embedding、知识库检索和 Reranker 耗时
- Conductor 耗时
- Conductor Token 用量
- 是否触发规则降级
- 是否发生并发排队及排队耗时

旧题目没有历史埋点数据，只会对修改后新生成的题目显示指标。

## 整场汇总

`GET /api/v1/workspaces/{workspace_id}/interviews/{interview_id}/observability`
会直接聚合已保存的 Trace，返回：

- 各节点平均耗时、P50、P95 和最大耗时；
- 模型 Token 总量；
- 降级事件数、降级题目数和降级率；
- 查询改写、联网搜索与 Retrieval Grader 路由统计；
- 排除整轮和 CRAG 聚合耗时后的主要瓶颈节点。

面试计划页面会自动加载并展示该汇总，不需要额外建立统计表。
