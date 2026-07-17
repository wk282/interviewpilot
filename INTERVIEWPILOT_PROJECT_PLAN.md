# InterviewPilot 项目完成与学习计划书

## 基于 Agentic CRAG 的双端智能技术面试平台

> 面向候选人模拟训练和企业候选人辅助评估，基于简历、岗位 JD 与技术知识库动态规划面试流程，实现检索自纠错、证据化评分、连续追问、人工审核与量化评测。

---

## 一、项目最终目标

项目完成后，应支持候选人端、企业端以及二者共享的智能面试底座。

### 1. 候选人端

候选人可以：

1. 注册并登录；
2. 上传 PDF/DOCX 简历；
3. 查看和修正简历结构化结果；
4. 选择目标岗位和面试难度；
5. 开始简历驱动的多轮技术面试；
6. 获得基于知识库证据的回答评分；
7. 接受围绕项目真实性的连续追问；
8. 结束后生成能力报告；
9. 查看知识薄弱点和学习建议；
10. 对比历史面试成绩。

### 2. 企业端

企业用户可以：

1. 创建岗位并导入 JD；
2. 配置岗位能力维度和评分 Rubric；
3. 上传候选人简历；
4. 自动生成候选人的面试计划；
5. 让 AI 执行结构化技术初面；
6. 查看每一项评分的证据；
7. 接收 AI 推荐的追问；
8. 修改 AI 评分和评价；
9. 生成结构化面试报告；
10. 由真人面试官作出最终判断。

### 3. 共同的智能底座

```text
简历/JD 结构化解析
→ 面试意图与能力点规划
→ Query Rewrite
→ Dense + BM25 混合召回
→ RRF 候选融合
→ Reranker 精排
→ Parent-Child 父块恢复
→ Retrieval Grader
→ 查询重写/联网补充/直接生成
→ 证据融合
→ 面试提问或回答评分
→ Grounding Grader
→ 重生成/拒答/继续追问
→ 证据化报告
```

---

## 二、当前已经完成的部分

当前项目不是从零开始，已经具备一套比较完整的 RAG 与 Agent 基础。

### 1. 文档处理

- PDF 页面渲染；
- VLM 图片转 Markdown；
- 异步 API 调用；
- 并发信号量控制；
- Tenacity 指数退避重试；
- MD5 页面缓存；
- SQLite 缓存数据库。

### 2. 文档切块

- Markdown 标题感知切块；
- Recursive Chunking；
- Parent-Child Chunking；
- 子块检索、父块保存；
- Small-to-Big 上下文恢复。

### 3. 检索链路

- OpenAI 兼容 Embedding；
- ChromaDB 持久化；
- Dense Retrieval；
- 粗召回后 Rerank；
- Reranker 失败降级；
- 父块去重和上下文控制。

### 4. Agent

- LangGraph 基础状态机；
- Query Rewrite；
- 简历结构化提取；
- 本地知识库检索；
- Tool Calling；
- Tavily 联网搜索；
- 基础会话记忆；
- 面试官 Prompt；
- 回答匹配度与追问。

### 5. 应用层

- FastAPI 后端；
- Streamlit 前端；
- PDF/DOCX 简历上传；
- 聊天界面；
- 检索来源展示。

### 6. 评测

- 112 条问答数据；
- RAGAS 评测脚本；
- Baseline 与高级版报告；
- Faithfulness、Answer Relevancy、Context Precision 等指标。

---

## 三、距离最终目标的核心缺口

| 模块 | 当前情况 | 最终目标 |
|---|---|---|
| 文档入库 | 多个离线脚本 | API 驱动的异步任务流水线 |
| 检索 | Dense + Rerank | Dense + BM25 + RRF + Rerank |
| CRAG | LLM 自主决定联网 | Retrieval Grader 显式条件路由 |
| 生成校验 | 没有独立校验节点 | Grounding Grader 与受限重生成 |
| 面试流程 | 通用聊天式面试 | 有阶段、有能力覆盖计划的状态机 |
| 双端产品 | 主要是候选人 Demo | 候选人端 + 企业审核端 |
| 工程能力 | 单机、内存会话 | 用户隔离、持久化、测试、监控 |
| 评测 | 报告存在缺失和污染 | 严格对照实验与多维指标 |

---

## 四、项目范围控制

这是一个个人求职项目，必须控制范围，优先完成能形成完整业务闭环、可评测、可解释和可部署的部分。

### 1. 必须完成

#### 智能底座

- Parent-Child；
- Dense + BM25；
- RRF；
- Rerank；
- Retrieval Grader；
- Query Rewrite；
- 联网补充；
- Evidence Fusion；
- Grounding Grader；
- 证据引用；
- 受限重试。

#### 候选人端

- 简历上传；
- 目标岗位配置；
- 多轮技术面试；
- 基于 Rubric 的评分；
- 动态追问；
- 面试报告。

#### 企业端

- 岗位和 JD；
- 能力模型；
- 候选人简历；
- AI 技术初面；
- 面试官审核评分；
- 评估报告。

#### 工程能力

- 数据持久化；
- 用户和会话隔离；
- 异步文档任务；
- 重试与幂等；
- 自动化测试；
- Docker；
- 日志和基础 Metrics；
- 离线评测报告。

### 2. 第一版暂时不做

- 视频面试；
- 摄像头监控；
- 表情或情绪识别；
- 复杂反作弊；
- 实时语音；
- 数字人；
- 多 Agent 辩论；
- 完整 ATS；
- Offer 管理；
- 邮件和日历；
- 微服务拆分；
- Kubernetes；
- 模型微调；
- 自研向量数据库；
- 自研推理引擎。

这些内容可以放入 Future Work，但不能影响主项目完成。

---

## 五、建议技术架构

### 1. 后端

继续使用：

- Python；
- FastAPI；
- Pydantic；
- LangGraph；
- SQLAlchemy；
- Alembic；
- PostgreSQL；
- Redis；
- ChromaDB 或 pgvector。

### 2. 向量数据库选择

短期不必立刻抛弃 ChromaDB：

1. 第一阶段继续使用 ChromaDB；
2. 通过 metadata 实现用户、企业、知识库过滤；
3. 项目核心完成后，再考虑迁移到 PostgreSQL + pgvector。

迁移向量库不是当前最重要的目标，真正重要的是：

- 数据归属；
- 增量更新；
- 删除同步；
- 检索质量；
- 评测；
- 会话隔离。

### 3. 异步任务

个人项目可以选择：

- Redis + Celery；
- Redis + RQ；
- Redis Streams；
- FastAPI BackgroundTasks，仅限早期开发。

推荐最终采用：

> Redis + Celery 或 RQ

不建议为了追求“高级”而自己从零实现复杂消息队列。

### 4. 前端

#### 第一阶段

继续使用 Streamlit，快速验证业务闭环。

#### 第二阶段

项目核心稳定后，再选择：

- React；
- Vue；
- Next.js。

不要一开始花大量时间重写前端。应优先保证智能链路、评测与工程可靠性。

---

## 六、核心数据模型

### 1. 用户与企业

#### User

```text
id
email
password_hash
display_name
role
tenant_id
created_at
```

#### Tenant

```text
id
name
status
created_at
```

#### Role

至少包括：

```text
candidate
interviewer
hr
tenant_admin
platform_admin
```

第一版不需要复杂 RBAC，可以先做角色枚举和资源归属校验。

### 2. 知识库与文档

#### KnowledgeBase

```text
id
tenant_id
name
type
visibility
created_by
```

类型可以包括：

```text
public_interview
enterprise_private
job_specific
candidate_resume
```

#### Document

```text
id
knowledge_base_id
filename
file_hash
file_type
storage_path
status
version
created_at
updated_at
```

#### IngestionTask

```text
id
document_id
status
current_stage
progress
error_code
error_message
retry_count
started_at
completed_at
```

任务状态：

```text
PENDING
PARSING
CHUNKING
EMBEDDING
COMPLETED
FAILED
CANCELLED
```

#### Chunk

```text
id
document_id
parent_id
content
chunk_type
page_number
section_path
content_hash
vector_id
```

### 3. 岗位和简历

#### JobPosition

```text
id
tenant_id
title
level
description
status
```

#### Competency

```text
id
job_id
name
description
weight
```

示例：

```text
RAG 原理：25%
Python 工程：20%
Agent 工作流：20%
系统设计：15%
数据库与缓存：10%
沟通表达：10%
```

#### ScoringRubric

```text
id
competency_id
score_level
description
positive_signals
negative_signals
```

#### Resume

```text
id
user_id
document_id
structured_data
confirmed_data
version
```

### 4. 面试

#### Interview

```text
id
tenant_id
candidate_id
job_id
mode
status
current_stage
started_at
completed_at
```

模式：

```text
candidate_practice
enterprise_ai_screening
interviewer_copilot
```

#### InterviewPlan

```text
id
interview_id
target_competencies
difficulty
question_budget
time_budget
plan_json
```

#### InterviewMessage

```text
id
interview_id
role
content
question_id
created_at
```

#### InterviewEvidence

```text
id
interview_id
message_id
source_type
document_id
chunk_id
content
relevance_score
```

#### InterviewScore

```text
id
interview_id
competency_id
ai_score
reviewed_score
confidence
positive_evidence
negative_evidence
reviewed_by
```

---

## 七、14 周实施与学习计划

建议以 14 周为周期。每周目标不是只看课程，而是：

```text
学习原理
→ 设计模块
→ 实现模块
→ 编写测试
→ 记录实验
→ 输出文档
```

如果每周时间不够，可以将每周延长为两周。不要为了赶进度跳过理解。

---

# 第一阶段：基础工程重构

## 第 1 周：统一项目边界和数据模型

### 学习内容

- 分层架构；
- 领域模型与数据库模型的区别；
- SQLAlchemy 基础；
- PostgreSQL 基础；
- Alembic 数据库迁移；
- REST API 资源设计；
- Pydantic 请求与响应模型。

### 实施任务

1. 明确最终项目名称和范围；
2. 绘制系统上下文图；
3. 绘制数据流图；
4. 设计数据库实体；
5. 将现有代码划分为：
   - API 层；
   - Application/Use Case 层；
   - Domain 层；
   - Infrastructure 层；
6. 将配置集中管理；
7. 补充依赖清单；
8. 创建 `.env.example`；
9. 编写最初版 README。

### 本周交付物

- 系统架构图；
- 数据模型图；
- API 草案；
- 项目目录设计；
- README V1；
- 技术决策记录 ADR。

### 验收标准

你能够解释：

- 为什么不能在 API Route 中直接写所有业务；
- 数据库实体与 Pydantic 模型有什么区别；
- 为什么数据库变更需要 Migration；
- 为什么不能把所有用户数据存在同一个默认会话里。

---

## 第 2 周：用户、会话和资源隔离

### 学习内容

- JWT 基本原理；
- 密码哈希；
- RBAC；
- 多租户；
- 水平越权；
- LangGraph Checkpointer；
- 无状态 API 与有状态会话。

### 实施任务

1. 用户注册和登录；
2. 候选人、面试官、管理员角色；
3. 请求中获取当前用户；
4. 所有资源增加 `user_id` 或 `tenant_id`；
5. 前端生成独立 `session_id`；
6. 移除固定的 `default_user_1`；
7. 真正使用前端传入的历史记录；
8. LangGraph thread 与 Interview ID 绑定；
9. 增加资源归属校验。

### 本周交付物

- 用户认证接口；
- 会话创建接口；
- 会话详情接口；
- 权限模型文档；
- 多用户隔离测试设计。

### 验收标准

- A 用户不能查看 B 用户的简历；
- A 用户不能调用 B 用户的面试会话；
- 不同会话的 LangGraph 状态不会串线；
- 服务重启后，核心业务记录不会丢失。

---

# 第二阶段：生产型文档入库

## 第 3 周：文档上传与异步任务

### 学习内容

- 同步和异步的区别；
- FastAPI 异步模型；
- 消息队列；
- Worker；
- At-least-once Delivery；
- 幂等性；
- 任务重试；
- 事务边界。

### 实施任务

1. 将 `run_parser.py` 转化为可复用服务；
2. 将切块脚本转化为服务；
3. 将向量化脚本转化为服务；
4. 新建文档上传 API；
5. 创建 `IngestionTask`；
6. Worker 执行：
   - Parsing；
   - Chunking；
   - Embedding；
   - Indexing；
7. 提供任务进度查询接口；
8. 记录阶段耗时；
9. 实现错误状态和重试次数。

### API 目标

```text
POST /documents
GET /documents/{id}
GET /tasks/{id}
POST /tasks/{id}/retry
```

### 验收标准

- 上传文档后立即返回任务 ID；
- 前端可以轮询任务进度；
- 任务失败后保留错误信息；
- 重试不产生重复向量；
- 处理过程中服务接口不会长时间阻塞。

---

## 第 4 周：增量索引和生命周期管理

### 学习内容

- 文件哈希；
- 内容寻址；
- 增量索引；
- 幂等 Upsert；
- Soft Delete 与 Hard Delete；
- 数据一致性；
- 补偿事务；
- 文档版本管理。

### 实施任务

1. 修复现有增量同步占位逻辑；
2. 文档上传时计算文件哈希；
3. 相同用户、相同知识库、相同哈希去重；
4. 文档修改后生成新版本；
5. 删除文档时清除：
   - 元数据；
   - Chunk；
   - 向量；
   - 缓存关联；
6. 失败时不能错误更新“已完成”状态；
7. Chunk 使用稳定 ID；
8. Embedding 批次支持失败重试。

### 验收标准

- 重复上传不会重复解析；
- 修改文档后旧向量会被清理或标记过期；
- 删除文档后无法再检索到对应内容；
- Worker 中途失败后可以安全重试；
- 数据库状态与向量库状态一致。

---

# 第三阶段：高级检索系统

## 第 5 周：检索评测基础

先不要立刻加 BM25。先建立检索评测，否则无法证明优化有效。

### 学习内容

- Precision@K；
- Recall@K；
- Hit Rate@K；
- MRR；
- NDCG；
- Query-Document Relevance；
- Hard Negative；
- 评测数据泄漏；
- 离线评测与线上评测。

### 实施任务

1. 为问题标注相关 Chunk；
2. 建立检索评测数据格式；
3. 给数据集增加：
   - 分类；
   - 难度；
   - 相关文档；
   - 相关 Chunk；
4. 编写统一 Retrieval Evaluator；
5. 评测现有：
   - 普通切块；
   - Parent-Child；
   - Dense Top-K；
   - Dense + Rerank；
6. 记录延迟和 API 成本。

### 验收标准

可以输出：

| 方案 | Recall@5 | Recall@10 | MRR | P95 延迟 |
|---|---:|---:|---:|---:|
| 固定切块 + Dense | 实测 | 实测 | 实测 | 实测 |
| Parent-Child + Dense | 实测 | 实测 | 实测 | 实测 |
| Parent-Child + Rerank | 实测 | 实测 | 实测 | 实测 |

---

## 第 6 周：Hybrid Search

### 学习内容

- 倒排索引；
- TF-IDF；
- BM25；
- Dense Retrieval；
- Sparse Retrieval；
- Hybrid Search；
- Score Normalization；
- RRF；
- 候选集去重；
- 中文分词。

### 实施任务

1. 增加 BM25 检索；
2. 分别召回 Dense Top-N 和 BM25 Top-N；
3. 使用 RRF 融合；
4. 对合并候选去重；
5. 将融合结果交给 Reranker；
6. 根据 metadata 执行知识库过滤；
7. 对不同方案进行评测。

### 推荐初始流程

```text
Dense Top 20
+
BM25 Top 20
→ RRF Top 20
→ Rerank Top 6
→ Parent Recovery Top 3
```

这些数字只是初始参数，最终应由实验确定。

### 验收标准

能够回答：

- BM25 为什么适合专有名词和精确匹配；
- Dense 为什么适合语义近似；
- 为什么不能直接比较两种检索器的原始分数；
- RRF 为什么不依赖分数尺度；
- 为什么 Rerank 不适合扫描整个知识库。

---

## 第 7 周：证据治理和引用

### 学习内容

- RAG 中的 Provenance；
- Citation；
- Chunk Metadata；
- Evidence Deduplication；
- 上下文压缩；
- Lost in the Middle；
- Prompt Injection；
- 可信来源排序。

### 实施任务

1. 统一 Evidence 数据格式；
2. 保存：
   - source_type；
   - document_id；
   - chunk_id；
   - page_number；
   - section；
   - retrieval_score；
   - rerank_score；
3. 父块恢复时保留子块命中位置；
4. 回答返回结构化引用；
5. 前端支持查看原文；
6. 区分：
   - 公共题库；
   - 企业私有题库；
   - 候选人简历；
   - 外部网页；
7. 对文档中的恶意指令进行隔离。

### 验收标准

- 回答的关键结论可以定位到真实文档；
- 用户点击引用能看到对应原文；
- 删除文档后引用不会继续指向不存在的内容；
- 外部网页与企业内部资料不会混淆。

---

# 第四阶段：真正的 Agentic CRAG

## 第 8 周：Retrieval Grader 与纠错路由

### 学习内容

- CRAG；
- Self-RAG；
- Retrieval Grading；
- Structured Output；
- LangGraph Conditional Edge；
- 状态机；
- 有限状态机与自由 Agent；
- 最大循环次数；
- 可恢复工作流。

### 实施任务

1. 增加独立 `retrieval_grader_node`；
2. 输出结构化评价：

```json
{
  "status": "partial",
  "confidence": 0.67,
  "missing_aspects": [
    "缺少该方案的适用条件"
  ],
  "recommended_action": "web_search"
}
```

3. 支持三类路由：

```text
sufficient → generate
partial → web_search
irrelevant → rewrite_query
```

4. Query Rewrite 根据“缺失信息”改写；
5. 设置最大改写次数；
6. 设置最大联网次数；
7. 记录每次纠错原因；
8. 达到上限后降级或拒答。

### 验收标准

- 路由由结构化评价结果决定；
- 不是完全依赖 LLM 自由 Tool Calling；
- 可以从日志或 Trace 中看到纠错原因；
- 不会无限循环；
- 评测模式可以关闭外网搜索。

---

## 第 9 周：证据融合与 Grounding Grader

### 学习内容

- Grounded Generation；
- Hallucination Detection；
- Claim-Evidence Alignment；
- Entailment；
- LLM-as-a-Judge；
- Judge Bias；
- 拒答策略；
- 置信度校准。

### 实施任务

1. 对本地和外部证据做统一格式化；
2. 外部结果去重与相关性过滤；
3. 增加证据冲突标记；
4. 生成答案后拆分关键 Claim；
5. 增加 `grounding_grader_node`；
6. 检查 Claim 是否有证据支持；
7. 输出：

```json
{
  "grounded": false,
  "unsupported_claims": [
    "该方案将召回率提升30%"
  ],
  "recommended_action": "regenerate"
}
```

8. 不忠实时：
   - 第一次：根据证据重生成；
   - 第二次：删除无依据内容；
   - 仍失败：低置信度拒答。

### 验收标准

- 无依据数字不会直接返回；
- 答案不能使用不存在的来源；
- 重生成次数有上限；
- 资料不足时明确说明；
- 可以评测“拒答准确率”。

完成这一周后，项目就可以名正言顺称为 **Agentic CRAG**。

---

# 第五阶段：面试业务核心

## 第 10 周：面试状态机与问题规划

### 学习内容

- Interview Plan；
- Task Planning；
- 对话状态管理；
- 能力模型；
- Adaptive Questioning；
- 难度调整；
- 问题覆盖率；
- 长期记忆与短期记忆。

### 实施任务

1. 定义面试阶段：

```text
PREPARATION
SELF_INTRODUCTION
PROJECT_DEEP_DIVE
TECHNICAL_FUNDAMENTALS
SYSTEM_DESIGN
CLOSING
REPORT_GENERATION
COMPLETED
```

2. 根据 JD 和简历生成 Interview Plan；
3. 每道问题关联：
   - 能力维度；
   - 难度；
   - 简历声明；
   - 期望证据；
   - 评分 Rubric；
4. 避免重复提问；
5. 记录已覆盖的能力；
6. 根据表现动态调节难度；
7. 每次只问一个核心问题；
8. 支持结束和暂停面试。

### 验收标准

- 面试不再是自由聊天；
- 系统能说明当前考察什么能力；
- 系统不会重复问同一个问题；
- 能力覆盖率可统计；
- 面试结束条件明确。

---

## 第 11 周：回答评分与连续追问

### 学习内容

- Rubric-based Evaluation；
- Evidence-based Scoring；
- Chain-of-Verification；
- 评分一致性；
- 评分偏差；
- Human-in-the-Loop；
- 追问策略。

### 实施任务

1. 不再直接让 LLM 输出任意百分比；
2. 根据 Rubric 分维度评分；
3. 从用户回答中抽取：
   - 正确技术点；
   - 错误技术点；
   - 缺失技术点；
   - 项目证据；
   - 不一致信息；
4. 输出结构化评分：

```json
{
  "competency": "RAG检索架构",
  "score": 3,
  "max_score": 5,
  "confidence": 0.76,
  "positive_evidence": [],
  "negative_evidence": [],
  "missing_points": [],
  "follow_up_strategy": "verify_project_claim"
}
```

5. 追问类型包括：
   - 原理追问；
   - 参数追问；
   - 失败案例；
   - 技术选型；
   - 对照实验；
   - 生产部署；
6. 防止追问无限深入同一知识点；
7. 根据时间和覆盖率切换主题。

### 验收标准

- 同一个答案在相同配置下评分相对稳定；
- 评分有明确 Rubric；
- 每个分数都有回答证据；
- 追问依赖上一轮回答，而不是随机出题；
- AI 不确定时会降低置信度。

---

# 第六阶段：双端业务闭环

## 第 12 周：候选人端

### 学习内容

- 用户体验；
- 反馈设计；
- 学习报告；
- 雷达图的合理使用；
- 历史趋势；
- 如何避免反馈变成空泛鼓励。

### 实施任务

候选人端实现：

1. 简历上传和解析确认；
2. 选择目标岗位；
3. 设置难度、时长和专项；
4. 开始面试；
5. 查看当前问题和回答；
6. 查看每轮反馈；
7. 结束后生成：
   - 综合得分；
   - 能力维度得分；
   - 优势；
   - 薄弱点；
   - 项目表达风险；
   - 推荐学习内容；
8. 保存历史面试；
9. 比较历史趋势。

### 验收标准

候选人可以独立完成：

```text
上传简历
→ 选择岗位
→ 完成面试
→ 获得报告
→ 查看历史记录
```

---

## 第 13 周：企业端和人工审核

### 学习内容

- Multi-Tenancy；
- Human-in-the-Loop；
- 审计日志；
- 评分修改记录；
- AI 辅助决策边界；
- 招聘公平性；
- 敏感数据保护。

### 实施任务

企业端实现：

1. 创建企业和岗位；
2. 导入 JD；
3. 配置能力权重；
4. 配置评分 Rubric；
5. 导入候选人简历；
6. 创建 AI 技术初面；
7. 查看面试记录；
8. 查看 AI 评分和证据；
9. 面试官可以：
   - 修改评分；
   - 添加备注；
   - 标记 AI 判断错误；
   - 选择追问；
10. 保存修改前后的结果；
11. 生成企业版评估报告。

### 产品边界

> AI 提供辅助评分和证据整理，不应作为自动淘汰或录用候选人的唯一依据，最终决策由真人面试官完成。

### 验收标准

- 不同企业的数据不会互相检索；
- 面试官能看到评分依据；
- 人工能修改 AI 结果；
- 修改有记录；
- 报告区分 AI 评分和人工最终评分。

---

# 第七阶段：评测、可靠性和交付

## 第 14 周：系统评测与求职交付

### 学习内容

- 消融实验；
- 压力测试基础；
- P50/P95/P99；
- Token 成本；
- 缓存命中率；
- OpenTelemetry 基础；
- Docker；
- CI；
- 项目答辩和 STAR 表达。

### A. 检索评测

比较：

1. Fixed Chunk + Dense；
2. Parent-Child + Dense；
3. Parent-Child + Dense + Rerank；
4. Hybrid + RRF + Rerank；
5. Hybrid + CRAG。

指标：

- Recall@5；
- Recall@10；
- MRR；
- NDCG；
- Context Precision；
- 检索 P95；
- Rerank P95。

### B. 生成评测

指标：

- Faithfulness；
- Answer Relevancy；
- Fact Coverage；
- Citation Accuracy；
- Refusal Accuracy；
- Grounding Pass Rate。

### C. 面试评测

指标：

- 问题与简历相关性；
- 问题与 JD 匹配度；
- 能力覆盖率；
- 重复问题比例；
- 追问相关性；
- 评分一致性；
- AI 与人工评分一致性。

### D. 工程指标

- API P50/P95；
- 文档处理吞吐；
- 失败率；
- 重试成功率；
- 缓存命中率；
- Token 消耗；
- 单次面试平均成本。

### E. 工程交付

补齐：

- README；
- 架构图；
- 数据流图；
- LangGraph 状态图；
- ER 图；
- API 文档；
- `.env.example`；
- Dockerfile；
- Docker Compose；
- 单元测试；
- 集成测试；
- 演示截图；
- 演示视频；
- 评测报告；
- 技术决策文档；
- 已知限制；
- Future Work。

---

## 八、最终 LangGraph 状态设计

建议最终状态至少包含：

```text
interview_id
user_id
tenant_id
job_id
resume_id

interview_mode
interview_stage
interview_plan
covered_competencies
current_competency
difficulty

messages
current_question
current_answer
question_count

original_query
rewritten_query
rewrite_count

retrieved_evidence
web_evidence
merged_evidence

retrieval_grade
grounding_grade
retry_count
web_search_count

answer_score
score_evidence
follow_up_strategy

final_report
errors
```

### 最终流程

```text
START
  │
  ▼
load_interview_context
  │
  ▼
plan_or_continue_interview
  │
  ▼
generate_retrieval_query
  │
  ▼
hybrid_retrieve
  │
  ▼
rerank
  │
  ▼
parent_context_recovery
  │
  ▼
retrieval_grader
  │
  ├─ sufficient ────────────────┐
  │                             │
  ├─ partial → web_search       │
  │              │              │
  │              ▼              │
  │        evidence_fusion      │
  │                             │
  └─ irrelevant → query_rewrite │
                    │            │
                    └─ retrieve  │
                                 ▼
                     question_or_score_generator
                                 │
                                 ▼
                         grounding_grader
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
               grounded                    ungrounded
                  │                             │
                  ▼                             ▼
       select_follow_up_or_finish       regenerate_or_refuse
                  │
                  ├─ continue → 下一轮
                  └─ finish → report_generator
```

---

## 九、测试计划

### 1. 单元测试

至少覆盖：

- 文件哈希；
- 重复上传检测；
- Chunk ID 稳定性；
- Parent-Child 关联；
- RRF 计算；
- Evidence 去重；
- Rubric 评分解析；
- Retrieval Grader 结构化输出；
- Grounding Grader 结构化输出；
- 最大重试次数。

### 2. 集成测试

至少覆盖：

- 上传文档到完成入库；
- 文档删除到向量清理；
- 文档修改到重新索引；
- 简历上传到结构化结果；
- 创建面试到生成报告；
- 外部搜索失败降级；
- Reranker 失败降级；
- LLM 返回无效 JSON；
- Worker 任务失败重试；
- 服务重启后的会话恢复。

### 3. 权限测试

至少覆盖：

- A 用户不能读取 B 用户简历；
- A 企业不能读取 B 企业题库；
- 候选人不能修改企业 Rubric；
- 面试官不能访问无权限岗位；
- 向量检索必须附带 tenant/knowledge-base 过滤。

---

## 十、学习方法

每个知识点都采用下面的学习循环。

### 第一步：理解问题

例如学习 Hybrid Search，不要先抄代码，要先回答：

- Dense Retrieval 的失败场景是什么？
- BM25 的失败场景是什么？
- 为什么它们互补？
- 为什么原始分数不能直接相加？

### 第二步：实现最小版本

先实现最简单、可解释的版本，不立即追求抽象。

### 第三步：构造失败案例

例如：

- 精确技术名词；
- 缩写；
- 同义表达；
- 否定问题；
- 多条件问题；
- 跨段问题。

### 第四步：做对照实验

比较优化前后，不凭感觉判断。

### 第五步：写技术笔记

每个核心模块至少写一篇短文：

```text
问题是什么
基础方案是什么
为什么基础方案不够
选择了什么方案
方案的原理
实现时遇到了什么问题
评测结果是什么
有什么限制
```

### 第六步：准备面试追问

例如完成 RRF 后，必须能回答：

- RRF 公式是什么；
- `k` 参数的作用；
- 为什么不直接把 BM25 和 Dense 分数相加；
- 候选集重复如何处理；
- RRF 与学习排序有什么区别。

---

## 十一、优先级划分

### P0：没有这些就不能称为完整项目

1. 用户和会话隔离；
2. 文档异步入库；
3. 增量更新、删除和幂等；
4. Hybrid Search；
5. Retrieval Grader；
6. Grounding Grader；
7. 有阶段的面试状态机；
8. Rubric 评分；
9. 候选人完整闭环；
10. 严格评测；
11. README、测试和 Docker。

### P1：增强企业场景

1. 岗位 JD；
2. 能力模型；
3. 企业题库；
4. 租户隔离；
5. 企业面试工作台；
6. 人工修改评分；
7. 审核记录；
8. 企业版报告。

### P2：加分项

1. React 前端；
2. pgvector；
3. OpenTelemetry Trace；
4. 详细成本面板；
5. 面试官 Copilot；
6. 历史能力趋势；
7. 更完整的权限模型。

### P3：暂时不要做

- 语音；
- 视频；
- 数字人；
- 微服务；
- Kubernetes；
- 多 Agent；
- 情绪识别；
- 反作弊；
- 模型微调。

---

## 十二、项目完成的最终验收流程

### 1. 候选人链路

```text
1. 候选人注册并登录
2. 上传 PDF/DOCX 简历
3. 后台异步解析并显示进度
4. 用户确认结构化简历
5. 选择目标岗位和难度
6. 系统生成面试计划
7. Hybrid Retrieval 检索相关知识
8. Retrieval Grader 判断证据质量
9. 必要时改写查询或联网补充
10. AI 发起与简历相关的问题
11. 候选人回答
12. 系统基于 Rubric 和证据评分
13. Grounding Grader 校验评分理由
14. 系统动态追问
15. 完成多轮面试
16. 生成能力报告和学习建议
17. 保存历史记录
```

### 2. 企业链路

```text
1. 企业用户登录
2. 创建岗位并导入 JD
3. 配置能力维度和评分标准
4. 上传候选人简历
5. 创建 AI 技术初面
6. 系统按岗位和简历生成面试计划
7. 完成结构化多轮面试
8. 生成带原文证据的评分报告
9. 面试官审核并修改评分
10. 保存 AI 原始评分和人工最终评分
11. 导出结构化评估报告
```

### 3. 工程验收

```text
1. Docker 一键启动
2. 不同用户数据隔离
3. 不同企业数据隔离
4. 文档支持增删改和失败重试
5. 会话状态可恢复
6. 外部服务失败时可以降级
7. 关键链路有日志和耗时
8. 核心模块有自动化测试
9. 有真实消融实验报告
10. 简历上的每个数字都可以复现
```

---

## 十三、最终简历表达方向

完成后，项目可以命名为：

> **InterviewPilot——基于 Agentic CRAG 的双端智能技术面试平台**

项目介绍可以写：

> 面向企业技术人才辅助评估与候选人模拟训练场景，设计由岗位 JD、个人简历和技术知识库联合驱动的双端智能面试平台。系统基于 LangGraph 编排混合检索、检索质量评估、查询重写、联网补充、证据融合及答案忠实度校验，通过结构化评分 Rubric 完成个性化提问、连续追问和证据化能力报告，并支持企业面试官人工复核。

在真正完成和评测前，不要提前写：

- “召回率提高 XX%”；
- “Faithfulness 达到 0.89”；
- “支持高并发”；
- “企业级”；
- “生产级高可用”；
- “多租户安全”；
- “显著降低成本”。

这些描述必须先有测试或报告支撑。

---

## 十四、最重要的执行建议

接下来的主线不应该是继续追逐更多 AI 名词，而应该是：

```text
现有 Demo
→ 数据与会话可靠
→ 文档入库闭环
→ 检索可评测
→ CRAG 显式纠错
→ 面试流程可控
→ 双端业务闭环
→ 测试与部署
→ 简历和面试表达
```

每完成一个阶段，都产出四样东西：

1. **可运行的功能；**
2. **自动化测试；**
3. **真实评测数据；**
4. **自己能够解释的技术文档。**

这样最终得到的不是一个堆叠 LangGraph、RAGAS、BM25 等关键词的项目，而是一个可以从业务、算法、后端、可靠性和评测五个角度完整讲清楚的求职主项目。

---

## 十五、阶段打卡总表

| 阶段 | 核心目标 | 状态 |
|---|---|---|
| 第 1 周 | 项目边界、数据模型和分层架构 | 未开始 |
| 第 2 周 | 用户、会话和资源隔离 | 未开始 |
| 第 3 周 | 文档上传与异步任务 | 未开始 |
| 第 4 周 | 增量索引和文档生命周期 | 未开始 |
| 第 5 周 | 检索评测基线 | 未开始 |
| 第 6 周 | Hybrid Search 与 RRF | 未开始 |
| 第 7 周 | 证据治理与引用 | 未开始 |
| 第 8 周 | Retrieval Grader 与 CRAG 路由 | 未开始 |
| 第 9 周 | Evidence Fusion 与 Grounding Grader | 未开始 |
| 第 10 周 | 面试状态机与问题规划 | 未开始 |
| 第 11 周 | Rubric 评分与连续追问 | 未开始 |
| 第 12 周 | 候选人端业务闭环 | 未开始 |
| 第 13 周 | 企业端与人工审核 | 未开始 |
| 第 14 周 | 评测、可靠性和求职交付 | 未开始 |

