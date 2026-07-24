# PDF生产接入第一阶段

## 当前能力

生产入库链路已经支持文本型PDF：

```text
上传PDF
→ PyMuPDF逐页读取
→ TEXT / SCANNED / MIXED / BLANK分类
→ 质量检查
→ 文本PDF进入清洗、父子切片、1024维Embedding和BM25索引
```

扫描页和混合页不会进入切片：

```text
检测到需要OCR的页
→ IngestionJob = WAITING_OCR
→ current_stage = OCR
→ Document / DocumentVersion = OCR_PENDING
→ 保存待OCR页码和页面质量指标
→ 停止后续处理
```

该状态不是失败。文档仍可删除，但在OCR Worker完成前不能用于检索、简历选择或面试。

## 页面判定

- `TEXT`：至少40个可打印字符；达到120字符时优先信任原生文本层。
- `MIXED`：40至119个可打印字符，同时图片覆盖率达到35%。
- `SCANNED`：原生文本不足或乱码比例过高。
- `BLANK`：没有原生文本且图片覆盖率低于5%，不会触发OCR。

所有判断均按页执行。只要存在一个 `SCANNED` 或 `MIXED` 页面，整份文档等待OCR，以避免不完整内容进入向量库。

## 数据库迁移

迁移文件：

```text
backend/alembic/versions/0017_pdf_ocr_pending_status.py
```

由用户执行：

```powershell
cd backend
alembic upgrade head
```

## 运行要求
CR` 任务。
2. 读取原始PDF并仅识别待OCR页面。
3. 合并原生文本与OCR块，保存置信度和坐标。
4. 再次执行质量门禁。
5. 通过后把任务恢复到 `CLEANING`，复用现有切片和向量化链路。
6. OCR失败时保留可重试状态、错误原因和执行指标。

Worker实现和启动说明位于 `backend/ocr_worker/README.md`。PaddleOCR仍不得安装到FastAPI环境。
