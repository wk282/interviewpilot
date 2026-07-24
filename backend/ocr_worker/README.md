# InterviewPilot OCR Worker

该Worker只负责扫描PDF和混合PDF，不运行FastAPI、面试Agent或Embedding。

## 处理链路

```text
普通Ingestion Worker检测到SCANNED/MIXED页
→ job = WAITING_OCR
→ Redis的ocr队列
→ PaddleOCR逐页识别
→ OCR置信度质量门禁
→ 原子写入parsed.json
→ job恢复到PENDING / CHUNKING
→ 投递回普通Celery队列
→ 父子切片、Embedding、pgvector和BM25
```

## 环境

OCR必须使用独立Conda环境，不要安装进 `rpilot`：

```powershell
conda activate pdfocr
cd D:\Work\简历\工作知识学习\ResearchPilot\backend
python -m pip install -r ocr_worker\requirements.txt
python -m pip check
```

`backend/.env` 至少需要：

```text
DATABASE_URL=postgresql+asyncpg://...
DOCUMENT_STORAGE_ROOT=data/uploads
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
OCR_WORKER_ENABLED=true
OCR_CELERY_QUEUE=ocr
```

## 启动

普通Worker仍在 `rpilot` 环境运行：

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=info --pool=solo
```

OCR Worker在 `pdfocr` 环境运行：

```powershell
celery -A ocr_worker.celery_app.celery_app worker --loglevel=info --pool=solo -Q ocr
```

首次OCR任务会下载PaddleOCR模型。

## 测试

OCR处理器单元测试不连接数据库、Redis或真实OCR模型：

```powershell
python -m unittest ocr_worker.tests.test_pdf_processor -v
```

端到端测试需要同时运行Redis、PostgreSQL、普通Worker和OCR Worker。上传扫描PDF后，状态应依次变化：

```text
PENDING → RUNNING → WAITING_OCR → RUNNING(OCR)
→ PENDING(CHUNKING) → RUNNING → COMPLETED
```

失败时文档状态为 `FAILED`，可以使用现有“重试失败任务”功能重新开始。
