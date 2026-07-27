# Docker 构建加速说明

## 优化目标

原 Compose 为 `migrate`、`backend`、`celery-worker`、`retrieval-mcp` 和
`report-mcp` 分别生成后端镜像。五个目标使用相同 Dockerfile 和代码，首次构建时会
并发争抢服务器 CPU、内存、网络和磁盘。

现在统一使用：

```text
interviewpilot-app:${APP_IMAGE_TAG:-latest}
```

只有 `migrate` 声明后端 `build`，其余四个服务直接复用该镜像并通过不同
`command` 启动，同时通过 `pull_policy: never` 禁止 Compose 把本地应用镜像误当成
Docker Hub 的 `library/interviewpilot-app` 拉取。`docker compose build --print` 的默认构建目标因此从 6 个减少为：

```text
migrate
frontend
```

OCR 仍使用隔离镜像，只有启用 `ocr` Profile 时才构建。

## 依赖下载和缓存

后端、OCR 和前端 Dockerfile 均启用 BuildKit Cache Mount：

```text
/root/.cache/pip
/root/.npm
/var/cache/apt
/var/lib/apt/lists
```

缓存只保留在 Docker Builder 中，不进入最终运行镜像。即使
`requirements.txt` 或 `package-lock.json` 改变，已下载的 Wheel/NPM 包仍可复用。

国内部署默认使用：

```dotenv
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
NPM_REGISTRY=https://registry.npmmirror.com
```

海外服务器可在根目录 `.env` 改回：

```dotenv
PIP_INDEX_URL=https://pypi.org/simple/
NPM_REGISTRY=https://registry.npmjs.org
```

## 部署命令

代码或依赖发生变化时：

```bash
docker compose --profile production up -d --build
```

如果服务器使用的 Compose 版本仍然并行检查本地镜像，可显式拆成顺序执行：

```bash
docker compose build migrate frontend
docker compose --profile production up -d --pull never
```

只有环境变量变化时不需要构建：

```bash
docker compose --profile production up -d
```

检查实际构建目标但不执行构建：

```bash
docker compose --profile production build --print
```

查看完整构建阶段：

```bash
docker compose --profile production build --progress=plain
```

不要在普通部署中使用：

```bash
docker compose build --no-cache
docker builder prune
docker system prune
```

这些命令会使依赖缓存失效。只有确认缓存损坏或磁盘必须清理时才使用。

## Docker Hub 镜像下载

Pip/NPM 镜像不能加速 `python:3.11-slim`、`node:22-alpine`、Caddy 和
OpenSearch 等基础镜像。阿里云服务器应在“容器镜像服务 -> 镜像工具 -> 镜像加速器”
获取账号专属地址，然后配置 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": [
    "https://<你的阿里云镜像加速地址>"
  ]
}
```

修改 Docker Daemon 会短暂影响正在运行的容器，应在维护窗口执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
docker compose --profile production up -d
```

## 诊断

```bash
nproc
free -h
df -h
docker system df
docker compose --profile production build --print
```

构建日志停在 `FROM ... pulling fs layer` 表示基础镜像下载慢；停在
`pip install` 或 `npm ci` 表示依赖下载慢；停在 `npm run build` 通常表示 CPU 或内存
不足。
