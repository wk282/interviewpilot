# 阿里云域名与 HTTPS 部署

生产部署使用同源架构：

```text
https://wktqkeji.site
  -> Caddy（自动签发和续期 HTTPS 证书）
  -> Frontend Nginx
  -> /api/* 反向代理到 FastAPI Backend
```

## 1. DNS

在域名解析控制台配置：

| 类型 | 主机记录 | 记录值 |
| --- | --- | --- |
| A | `@` | 阿里云服务器公网 IPv4 |
| A | `www` | 阿里云服务器公网 IPv4 |

等待解析后，在服务器检查：

```bash
dig +short wktqkeji.site
dig +short www.wktqkeji.site
```

两个结果都应是当前服务器公网 IP。

## 2. 阿里云安全组

公网只需要放行：

- TCP 22：SSH；
- TCP 80：Caddy 首次签发证书和 HTTP 跳转；
- TCP 443：HTTPS；
- UDP 443：可选的 HTTP/3。

不要向公网放行 PostgreSQL 5432、Redis 6379、OpenSearch 9200 和 FastAPI 8000。Compose 已将这些调试端口限制到服务器的 `127.0.0.1`。

## 3. 生产环境变量

服务器仓库根目录 `.env` 至少包含：

```dotenv
PUBLIC_DOMAIN=wktqkeji.site
CORS_ALLOWED_ORIGINS=https://wktqkeji.site,https://www.wktqkeji.site
```

`backend/.env` 继续保存模型 Key、JWT Secret 等后端配置，不要提交这两个 `.env` 文件。
根目录 `.env` 还应设置独立的 `MCP_INTERNAL_SECRET`。两个 MCP 服务只在 Docker 内部网络提供工具接口，不需要开放 8011/8012 端口。

## 4. 启动

先确保服务器的 80 和 443 端口没有被宿主机 Nginx、Apache 或其他容器占用：

```bash
ss -lntup | grep -E ':80 |:443 '
```

生产环境启动命令：

```bash
docker compose --profile production up -d --build
docker compose --profile production ps
docker compose logs --tail=100 gateway frontend backend retrieval-mcp report-mcp
```

`gateway` 的 Caddy 会自动申请证书。DNS 尚未生效、端口未放行或域名未指向本机时，证书申请会失败。

## 5. 验证

```bash
curl -I http://wktqkeji.site
curl -I https://wktqkeji.site
curl https://wktqkeji.site/api/v1/health
```

项目后端当前的基础健康接口也可以通过根路径代理访问，但根路径由前端接管；容器内部检查使用：

```bash
curl http://127.0.0.1:8000/
```

查看自动证书日志：

```bash
docker compose logs -f gateway
```

## 6. 本地开发

本地不启用生产 Profile：

```bash
docker compose up -d
```

继续通过 `http://127.0.0.1:8080` 访问。本地调试端口只绑定到本机，不再暴露给局域网或公网。
