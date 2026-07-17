import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.v1.router import router as v1_router

# ==========================================
# 知识点讲解:
# 这是我们后端大本营的入口文件。
# 它负责启动 FastAPI 引擎，并挂载我们在 routes.py 里写的接口。
# 我们还开启了 CORS (跨域资源共享)，这样如果前端和后端部署在不同端口/服务器，也能正常通信。
# ==========================================

# 1. 创建 FastAPI 实例
app = FastAPI(
    title="InterviewPilot API",
    description="基于 Agentic CRAG 的双端智能技术面试平台",
    version="1.0.0"
)

# 2. 配置跨域白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],  # 允许 GET, POST, OPTIONS 等所有方法
    allow_headers=["*"],
)

# 3. 挂载我们核心的问答路由
app.include_router(router, prefix="/api/v1")
app.include_router(v1_router, prefix="/api/v1")

@app.get("/")
def health_check():
    """健康检查接口：浏览器里访问根路径，看到这个就说明后端活蹦乱跳的。"""
    return {"status": "ok", "message": "ResearchPilot Backend is running smoothly! 🚀"}

if __name__ == "__main__":
    # 使用 Uvicorn 作为 ASGI 服务器启动 FastAPI
    # host="0.0.0.0" 表示允许局域网内其他设备访问
    # port=8000 是约定的默认后端端口
    print("🚀 正在启动 FastAPI 后端服务...")
    print("👉 Swagger UI 接口文档地址: http://127.0.0.1:8000/docs")
    uvicorn.run("run_server:app", host="0.0.0.0", port=8000, reload=True)
