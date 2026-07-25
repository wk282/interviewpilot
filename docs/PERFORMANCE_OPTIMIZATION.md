# 面试 AI 链路性能优化

## 优化依据

最新完整离线评测报告 `backend/evaluation/reports/20260723T005336Z/report.md` 显示：

- `VECTOR_BM25_RRF` 的 MRR 为 `0.867778`，是本轮最高结果；
- `VECTOR_BM25_RRF` 的 Recall@5 为 `0.672222`、NDCG@5 为 `0.747971`、Hit@5 为 `1.0`；
- `VECTOR_BM25` 的 MRR 为 `0.851389`、Recall@5 为 `0.677778`、NDCG@5 为 `0.741253`；
- RRF 略微牺牲 Recall@5，但提升了 MRR、NDCG@5 和 Hit@5，说明相关证据的首位排序和整体排序质量更好；
- 本轮所有增加 Reranker 的组合均出现质量下降和延迟增加，因此不默认启用全局 Reranker。

因此，生产面试链路默认采用 `VECTOR_BM25_RRF`，但不把“组件越多越好”作为原则，后续仍由冻结评测集上的回归结果决定默认配置。

## RRF 排名与 CRAG 判级必须分离

RRF 分数用于对多个召回通道的名次进行融合：

```text
RRF(d) = Σ 1 / (k + rank_channel(d))
```

它表达的是文档在多个通道中的**相对排名优势**，不是 0 到 1 的相关性概率。例如 `0.0328` 可能已经代表两个通道都排在前列，不能与 `0.55` 这类归一化相关性阈值直接比较。

因此 CRAG 将两个概念分开：

1. `fusion_score`：保留原始 RRF 分数，只用于排序和可观测性；
2. `evidence confidence`：根据证据数量、召回来源、通道排名和向量相似度判断证据是否充分；
3. 快速通道不满足时，再交给 Retrieval Grader 判断 `sufficient / partial / irrelevant`；
4. Grader 失败时走保守降级，不允许仅凭原始 RRF 分数判定证据充分。

## 默认策略

```dotenv
INTERVIEW_RETRIEVAL_PROFILE=VECTOR_BM25_RRF
INTERVIEW_GLOBAL_RERANK_ENABLED=false
CRAG_LOCAL_FAST_PATH_ENABLED=true
CRAG_FAST_PATH_MIN_EVIDENCE=2
CRAG_RRF_FAST_PATH_MIN_VECTOR_SIMILARITY=0.60
CRAG_RRF_FAST_PATH_MAX_VECTOR_RANK=5
CRAG_RRF_FAST_PATH_MAX_BM25_RANK=5
```

RRF 快速通道要求：

1. 证据数量不少于 `CRAG_FAST_PATH_MIN_EVIDENCE`；
2. Top-1 融合结果同时被 Vector 和 BM25 召回；
3. Top-1 的向量相似度不低于 `0.60`；
4. Top-1 的 Vector 排名和 BM25 排名均不低于各自 Top 5；
5. 任一条件不满足时调用 Retrieval Grader，而不是比较原始 RRF 分数。

完整执行逻辑：

1. 查询只生成一次 Embedding；
2. Vector 与 BM25 分别召回候选，并保留各自的原始名次；
3. 标准 RRF 只累计文档实际出现过的召回通道贡献；
4. 默认不调用本轮评测中为负收益的全局 Reranker；
5. 明确满足跨通道一致性条件时走本地快速判定；
6. 证据不足或存在冲突时调用 Retrieval Grader，并按需要进入 Query Rewrite 或 Web Search；
7. Critic、Plan Reviser 与 Conductor 闭环保持不变。

## 可回滚与回归评测

需要与加权归一化融合比较时：

```dotenv
INTERVIEW_RETRIEVAL_PROFILE=VECTOR_BM25
```

需要重新对比 Reranker 时：

```dotenv
INTERVIEW_RETRIEVAL_PROFILE=VECTOR_BM25_RRF
INTERVIEW_GLOBAL_RERANK_ENABLED=true
```

所有策略均记录到题目的 Observability Trace。由于本次同时修正了标准 RRF 的通道贡献规则，既有报告只能作为选择依据，合并后必须重新运行冻结评测，重点比较 MRR、Recall@5、NDCG@5、Hit@5、P95 延迟、Token 成本、Grader 调用率、Query Rewrite 率和 Web Search 率。
