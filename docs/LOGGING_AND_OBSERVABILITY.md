# 日志与链路定位

后端日志统一保存在 `backend/logs/`，不受启动命令所在目录影响。

| 进程 | 日志文件 | 主要内容 |
| --- | --- | --- |
| FastAPI | `app_YYYY-MM-DD.log` | API内执行的动态面试、五Agent节点和CRAG链路 |
| 普通Celery Worker | `celery_YYYY-MM-DD.log` | 文档入库、Embedding、索引、面试计划和最终评估任务 |
| OCR Worker | `ocr_worker.log` | PDF页面分类、PaddleOCR、质量门禁和普通队列回投 |

## 文档入库定位

使用 `job_id` 串联一次任务，正常扫描PDF会依次出现：

```text
Ingestion waiting for OCR
OCR task received
OCR page started / completed
OCR result handed to ingestion queue
Ingestion stage started | stage=CHUNKING
Embedding batch started
Ingestion completed
```

页面显示45%表示OCR结果已经保存，任务正从OCR Worker交回普通Celery Worker，准备切片。前端会继续每3秒轮询，不再需要手动刷新。

## 面试链路定位

使用 `interview_id` 串联一次面试，节点日志包括：

```text
request_router
planner_agent
answer_critic_agent
plan_reviser_agent
interviewer_agent
wait_for_answer
final_evaluator_agent
```

动态出题和回答后的Agent链路由FastAPI请求执行，因此查看 `app_YYYY-MM-DD.log`。异步生成面试计划和最终报告由Celery执行，因此查看 `celery_YYYY-MM-DD.log`。

日志只记录业务ID、路由、动作、分数、耗时和错误，不记录简历全文或候选人完整答案。
