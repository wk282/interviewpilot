# 面试 AI 链路性能优化

## 优化依据

冻结评测报告 `backend/evaluation/reports/20260717T094454Z/report.md` 显示：

- `VECTOR_BM25` 的 MRR 为 `0.834722`，是本轮最高结果；
- `VECTOR_BM25` 的 Recall@5 为 `0.677778`，NDCG@5 为 `0.729968`；
- 所有增加 Reranker 的组合均出现质量下降，延迟也明显增加；
- `CRAG_LOCAL` 平均延迟约 `4.77s`，主要开销来自每次都调用模型判级。

因此生产面试链路不继续沿用固定的“组件越多越好”策略，而是让离线评测决定默认配置。

## 默认策略

```dotenv
INTERVIEW_RETRIEVAL_PROFILE=VECTOR_BM25
INTERVIEW_GLOBAL_RERANK_ENABLED=false
CRAG_LOCAL_FAST_PATH_ENABLED=true
CRAG_FAST_PATH_MIN_EVIDENCE=2
CRAG_FAST_PATH_MIN_FUSION_SCORE=0.55
```

执行逻辑：

1. 查询只生成一次 Embedding；
2. 使用向量与 BM25 融合召回；
3. 默认不调用当前评测中负收益的全局 Reranker；
4. 证据数量和融合分数达到阈值时，由确定性规则直接判定为 `sufficient`；
5. 证据不足或低置信度时，仍调用 Retrieval Grader；
6. Critic、Plan Reviser 与 Conductor 闭环保持不变。

## 可回滚性

需要重新对比 Reranker 时，只修改 `.env`：

```dotenv
INTERVIEW_RETRIEVAL_PROFILE=VECTOR_BM25
INTERVIEW_GLOBAL_RERANK_ENABLED=true
```

所有新策略都会继续记录到题目的 Observability Trace。优化后应重新运行冻结评测，并比较质量、P95 延迟、Token 和降级率，不能只比较平均响应速度。
