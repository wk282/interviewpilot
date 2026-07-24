# PDF入库隔离实验

## 状态与边界

该目录是独立实验，不属于生产应用：

- 不修改 `backend/app/services/document_parsers.py`。
- 不调用正式上传API、Celery、PostgreSQL、pgvector或OpenSearch。
- 默认测试使用Fake OCR和Fake Embedding，不产生外部API费用。
- 指标通过并人工评审前，不允许接入正式入库链路。

现有生产链路已经具备父子切片、1024维Embedding、pgvector和BM25入库。实验只验证PDF能否稳定转换为相同的：

```text
metadata + blocks + plain_text
```

## 实验链路

```text
PDF签名/大小/页数校验
→ PyMuPDF逐页提取原生文本和图像覆盖率
→ 页级分类：TEXT / SCANNED / MIXED
→ 仅对SCANNED和MIXED页调用OCR
→ 原生文本与OCR块去重
→ 质量门禁
→ 父子切片实验
→ 1024维向量契约验证
→ 与同内容MD基线做检索评测
```

## 目录

```text
pdf_lab/
  classifier.py       页级文本/OCR路由
  parser.py           PyMuPDF解析与统一输出契约
  ocr_backends.py     可选PaddleOCR 2.x适配器
  quality.py          入切片前质量门禁
  vectorization.py    1024维向量覆盖契约
  metrics.py          CER和路由准确率
  benchmark.py        数据集批量评测入口
tests/                不连接正式服务的单元测试
fixtures/             待放入PDF测试集
expected/             人工校验标准文本
reports/              评测输出
```

## 第一层：不安装OCR的单元测试

在项目根目录执行：

```powershell
pip install -r experiments/pdf_ingestion/requirements.txt
python -m unittest discover -s experiments/pdf_ingestion/tests -v
```

覆盖内容：

- 文本页、扫描页和混合页分类。
- 原生文本PDF输出契约。
- 扫描页只调用注入的Fake OCR。
- 没有OCR后端时明确失败。
- PDF文件签名和最大页数限制。
- 空文本、乱码和低OCR置信度门禁。
- 每个Child切片必须对应一个1024维有限向量。
- OCR字符错误率和页路由准确率计算。

真实Embedding测试默认跳过，不会在普通单元测试中调用外部接口。

## 第二层：真实PaddleOCR测试

先安装独立OCR依赖：

```powershell
pip install -r experiments/pdf_ingestion/requirements-ocr.txt
```

指定一份扫描PDF后执行：

```powershell
$env:RUN_PDF_OCR_INTEGRATION="1"
$env:PDF_OCR_FIXTURE="D:\path\to\scanned-resume.pdf"
python -m unittest experiments.pdf_ingestion.tests.test_real_ocr_integration -v
```

PaddleOCR首次运行可能下载模型。CPU和GPU版本的PaddlePaddle不能混装；GPU验证应单独建立环境。

测试成功后会在 `reports/` 生成：

```text
<PDF文件名>-ocr.txt       OCR纯文本
<PDF文件名>-parsed.json   页类型、文本块、坐标和置信度
<PDF文件名>-quality.json  质量门禁指标
```

如果错误栈显示 `albumentations.pytorch` 加载 `torch` DLL失败，说明安装了Albumentations 2.x。实验固定使用Albumentations 1.x，因为PaddleOCR推理不需要PyTorch。修复命令：

```powershell
python -m pip install --upgrade --force-reinstall "numpy>=1.24,<2.0" "opencv-python-headless>=4.10.0.84,<4.12.0" "albumentations>=1.4.10,<2.0"
```

## 真实1024维Embedding测试

该测试会产生真实接口调用和费用，只使用实验环境变量，不读取正式 `.env`：

```powershell
$env:RUN_PDF_EMBEDDING_INTEGRATION="1"
$env:PDF_EMBEDDING_FIXTURE="D:\path\to\native-text.pdf"
$env:PDF_EMBEDDING_API_KEY="你的测试Key"
$env:PDF_EMBEDDING_BASE_URL="Embedding服务地址"
$env:PDF_EMBEDDING_MODEL="embedding-3"
python -m unittest experiments.pdf_ingestion.tests.test_real_embedding_integration -v
```

测试只有在PDF质量门禁通过后才会切片和调用Embedding，并验证每个切片都有一个1024维有限向量。它不会写入正式PostgreSQL或OpenSearch。

## 第三层：数据集基准评测

1. 将PDF放入 `fixtures/`。
2. 将人工校验文本放入 `expected/`。
3. 复制并填写 `manifest.example.json`。
4. 执行：

```powershell
python -m experiments.pdf_ingestion.pdf_lab.benchmark `
  experiments/pdf_ingestion/manifest.example.json `
  --enable-ocr `
  --output experiments/pdf_ingestion/reports/pdf-benchmark.json
```

## 接入生产前质量门禁

| 指标 | 门禁 |
|---|---:|
| 文本PDF字符召回率 | ≥98% |
| 清晰扫描件OCR CER | ≤5% |
| 复杂扫描件OCR CER | ≤10% |
| TEXT/SCANNED/MIXED路由准确率 | ≥95% |
| 成功文档空文本率 | 0% |
| Child切片向量覆盖率 | 100% |
| 向量维度正确率 | 100%，固定1024维 |
| PDF检索Recall@5 | 相比同内容MD基线下降不超过3个百分点 |
| 加密、损坏和超限文件明确失败率 | 100% |

## 尚未实现的实验项

- 表格单元格和复杂双栏阅读顺序评测。
- 页眉页脚和跨页重复内容清理。
- 真实Embedding API的批量上限、超时、重试和费用统计。
- PDF与同内容MD的Recall@K、MRR、NDCG回归。
- 模糊、旋转、低分辨率扫描件的预处理对比。
- PDF恶意内容、压缩炸弹和病毒扫描方案。

这些项目完成前，实验代码不得注册到生产 `parser_for()`。
