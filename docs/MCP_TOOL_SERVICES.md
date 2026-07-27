# MCP 工具服务设计

## 1. 目标与边界

MCP（Model Context Protocol）用于统一 Agent 与工具之间的调用协议，不负责 Agent 决策，也不会因为接入 MCP 自动增加一个 Agent。

InterviewPilot 将两项可复用能力封装为独立的 Streamable HTTP MCP Server：

1. `retrieval-mcp`：向 CRAG、Planner 和 Interviewer 提供完整的面试证据检索能力；
2. `report-mcp`：向报告编排接口提供 PDF 评估报告渲染能力。

Interviewer 不调用 PDF 工具。PDF 只在 Final Evaluator 完成评估之后，由报告下载接口调用。

## 2. 调用链路

```text
Planner / Interviewer
        |
        v
CRAG deterministic route
        | MCP Client (Streamable HTTP)
        v
hybrid_retrieve_interview_evidence
        |
        +-- Vector retrieval (pgvector)
        +-- BM25 (OpenSearch)
        +-- RRF fusion
        +-- optional global Reranker
        `-- structured evidence + retrieval metadata
```

```text
Completed Final Evaluation
        |
        v
PDF download API / report orchestration
        | MCP Client (Streamable HTTP)
        v
render_interview_report
        |
        `-- controlled PDF artifact -> checksum verification -> download
```

默认生产检索 Profile 仍为离线评测选出的 `VECTOR_BM25_RRF`。MCP 只改变工具调用边界，不改变 CRAG 的判级、查询重写或 Web Search 路由规则。

## 3. 工具契约

### `hybrid_retrieve_interview_evidence`

输入：

- `interview_id`
- `query`
- `auth_token`（应用后端签发的短期内部 Token）

服务端根据已认证的面试会话读取简历、岗位和参考知识库，不允许模型传入 `workspace_id`、`user_id` 或任意知识库 ID。

输出：

- 结构化 `evidence`
- 检索 Profile、结果数、服务端延迟和各检索通道观测数据

### `render_interview_report`

输入：

- `interview_id`
- 固定模板版本 `interview-report-v1`
- 固定语言 `zh-CN`
- `auth_token`

输出的是受控 `artifact_id`、SHA-256 和文件大小，不返回任意服务器文件路径。FastAPI 从共享的受控目录读取文件、校验摘要后立即删除临时产物。

## 4. 安全与可靠性

- 后端使用 HMAC 签名短期 MCP Token，注入用户和工作空间上下文；
- MCP Server 再次查询成员关系并校验工作空间数据隔离；
- 检索来源由数据库中的面试配置派生，LLM 不能越权选择知识库；
- MCP 调用受 `MCP_CALL_TIMEOUT_SECONDS` 限制；
- MCP 超时、协议错误或服务不可用时，自动降级到原有进程内实现；
- MCP 是否成功、服务端耗时和降级原因写入现有检索 observability；
- PDF 使用 UUID 文件名和 SHA-256 校验，并清理过期产物。

## 5. 本地运行

默认 `.env.example` 关闭 MCP，FastAPI 会直接运行原有服务。实验 MCP 时，在 `backend` 目录打开两个终端：

```powershell
python -m mcp_servers.retrieval_server
python -m mcp_servers.report_server
```

然后设置：

```dotenv
MCP_RETRIEVAL_ENABLED=true
MCP_REPORT_ENABLED=true
MCP_INTERNAL_SECRET=<一个足够长的随机字符串>
```

修改环境变量后需要重启 FastAPI 和主 Celery Worker。前端不需要重启。

## 6. Docker Compose

Compose 默认启动两个内部 MCP 服务，它们不向公网映射端口：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f retrieval-mcp report-mcp
```

生产部署仍使用：

```bash
docker compose --profile production up -d --build
```

MCP 是内部工具层，公网入口仍只有 Caddy 的 80/443。

## 7. 验证重点

- MCP 与本地路径返回的 Evidence ID、Chunk 和排序是否一致；
- MCP 增加的 P50/P95 延迟；
- MCP 故障时本地降级是否成功；
- 用户跨工作空间访问是否被拒绝；
- 报告摘要校验、读取后删除和过期清理是否生效。
