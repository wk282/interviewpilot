# InterviewPilot

InterviewPilot 是一个基于 **Agentic CRAG（纠错检索增强生成）** 架构驱动的简历与岗位 JD 驱动型智能技术面试平台。

## 目录结构

```text
ResearchPilot/
|- backend/                       FastAPI、Celery、AI 服务与数据库迁移
|  |- app/                        后端应用主包
|  |- alembic/                    数据库迁移脚本
|  |- data/                       后端数据集与运行文档
|  |- evaluation/                 离线评估语料、标注、指标与报告
|  |- .env.example                后端配置模板
|  |- alembic.ini
|  |- requirements.txt
|  `- run_server.py
|- frontend/                      React + TypeScript + Vite 前端应用
|- docs/                          架构设计与 Baseline 文档
|- 面试题/                         原始题库素材
`- docker-compose.opensearch.yml  OpenSearch 开发环境依赖
```

## 后端运行 (Backend)

请在 `backend` 目录下执行后端相关命令，以便 `.env`、Alembic、上传文件和日志路径能够正确加载：

```powershell
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn run_server:app --reload --host 0.0.0.0 --port 8000
```

在独立终端中运行主 Celery Worker（处理普通文档解析、向量化与 Agent 任务）：

```powershell
cd backend
conda activate rpilot
celery -A app.workers.celery_app.celery_app worker --loglevel=info --pool=solo
```

在另一个独立终端中运行专用的 OCR Celery Worker（处理扫描版/纯图片 PDF 识别，需要 `pdfocr` 独立环境，详见 `backend/ocr_worker/README.md`）：

```powershell
cd backend
conda activate pdfocr
celery -A ocr_worker.celery_app.celery_app worker --loglevel=info --pool=solo -Q ocr
```

## 前端运行 (Frontend)

```powershell
cd frontend
npm install
npm run dev
```

Vite 开发服务器会自动将 `/api` 请求代理到后端地址 `http://127.0.0.1:8000`。

## 基线版本 (Baseline)

评测前的完整产品基线版本已保存于 Git 标签 `baseline-v1`。详见 [docs/BASELINE_V1.md](docs/BASELINE_V1.md) 获取其功能范围与恢复说明。

## 离线评测体系 (Offline Evaluation)

`develop` 分支引入了版本化的检索与 Critic 回归评测框架。该框架基于冻结数据集，对比了 8 种检索 Profile、CRAG 本地/联网路由、延迟以及面试决策质量。详见 [backend/evaluation/README.md](backend/evaluation/README.md) 获取手动准备与评测命令。

## 动态自适应面试循环 (Adaptive Interview Loop)

`develop` 分支将面试流程拆分为：单轮回答评价器 (Answer Critic)、确定性计划修订器 (Plan Reviser)、CRAG 检索器、出题引导器 (Conductor) 以及终审评估器 (Final Evaluator)。每一次回答决策与计划修订都会持久化记录模型名称、Prompt 版本、证据链、降级策略与工作流 Trace 元数据。详见 [docs/ANSWER_CRITIC_WORKFLOW.md](docs/ANSWER_CRITIC_WORKFLOW.md)。

## 多 Agent 编排 (Multi-Agent Orchestration)

Planner、Answer Critic、Plan Reviser、Interviewer 和 Final Evaluator 共享同一个可序列化的 `InterviewState` 状态，并通过 LangGraph 路由提供 `PLAN`（规划）、`TURN`（轮次）和 `EVALUATE`（评估）入口。计划修订保留了前后对比快照、字段级 Diff 和能力项题目预算。详见 [docs/MULTI_AGENT_ARCHITECTURE.md](docs/MULTI_AGENT_ARCHITECTURE.md)。

运行图采用 PostgreSQL Checkpoint 与 `wait_for_answer` 中断机制。候选人提交回答后唤醒暂停的线程并执行 `ainvoke(None)`；即使网络中断，再次读取时也能恢复已生成的题目，无需重复调用大模型。详见 [docs/LANGGRAPH_CHECKPOINTING.md](docs/LANGGRAPH_CHECKPOINTING.md)。

## AI 可观测性 (AI Observability)

新的面试轮次会在现有的决策与工作流 Trace 中持久化记录节点级延迟、模型使用情况、Token 消耗量、路由决策和降级来源。面试计划视图提供了按题目划分的耗时汇总。详见 [docs/AI_OBSERVABILITY.md](docs/AI_OBSERVABILITY.md)。

FastAPI、Celery 导入任务以及独立 OCR Worker 会分别向 `backend/logs/` 写入独立日志文件。详见 [docs/LOGGING_AND_OBSERVABILITY.md](docs/LOGGING_AND_OBSERVABILITY.md) 获取日志归属与文档/面试工作流追踪 ID 说明。

## AI 成本与并发控制 (AI Cost Control)

模型调用采用主模型与 Mini 模型分层、CRAG 本地快速路径、Rewrite/Web Search 次数上限、批量 Embedding、文件内容去重和动态题目预算。所有 Chat、Embedding 与启用时的 Reranker 调用都经过统一并发闸门，并记录排队耗时、并发占用和超时降级。详见 [docs/AI_COST_AND_CONCURRENCY.md](docs/AI_COST_AND_CONCURRENCY.md)。

## 评测驱动的性能优化 (Evaluation-Driven Performance)

生产面试路径默认采用 Benchmark 领先的 `VECTOR_BM25_RRF` Profile，禁用了目前净收益为负的全局 Reranker，并在证据明确充分时走确定性的 CRAG 快速通道（Fast Path）。对于模糊不清的证据，仍将交由模型 Grader 评估。详见 [docs/PERFORMANCE_OPTIMIZATION.md](docs/PERFORMANCE_OPTIMIZATION.md)。

## 面试业务质量审计 (Interview Business Evaluation)

完成的面试将接受版本化的确定性质量审计，覆盖能力项覆盖率、Critic 覆盖率、自适应动作合规性、重复率、Grounding（依据契合度）、报告证据有效性、打分一致性和降级率。审计结果会被持久化保存并随最终报告一起展示。详见 [docs/INTERVIEW_BUSINESS_EVALUATION.md](docs/INTERVIEW_BUSINESS_EVALUATION.md)。
