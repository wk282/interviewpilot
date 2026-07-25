import os
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==========================================
# 知识点讲解:
# 在企业级项目中，我们通常不直接使用 os.getenv() 获取散落各处的环境变量。
# 使用 pydantic-settings 可以实现强类型校验，如果缺失关键变量，程序启动时就会立刻报错，
# 而不是运行到一半才崩溃（Fail Fast 原则）。
# ==========================================

class Settings(BaseSettings):
    # PostgreSQL and authentication configuration
    DATABASE_URL: str = "postgresql+asyncpg://interviewpilot:your_password@localhost:5432/interviewpilot"
    DATABASE_ECHO: bool = False
    LANGGRAPH_CHECKPOINT_DATABASE_URL: str | None = None
    INTERVIEW_PLAN_TIMEOUT_SECONDS: int = 180
    INTERVIEW_PLAN_STALE_SECONDS: int = 600
    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )
    DOCUMENT_STORAGE_ROOT: str = "data/uploads"
    DOCUMENT_MAX_FILE_SIZE_MB: int = 25
    OCR_WORKER_ENABLED: bool = False
    OCR_CELERY_QUEUE: str = "ocr"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # 这里定义环境变量的映射，Pydantic 会自动从环境变量或 .env 文件中去读取同名字段。
    # 如果类型定义为 str 且没有默认值，则代表该配置是**必填项**，找不到程序就会在启动时直接报错（Fail Fast）。
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str
    LLM_MODEL: str = "gpt-5.4-mini"
    LLM_MINI_MODEL: str = "gpt-5.4-mini"
    
    # 给定一个默认值，表示这是选填项。如果 .env 中没写 VISION_MODEL_NAME，就会默认使用 "gpt-4o"
    VISION_MODEL_NAME: str = "GPT-5.4-Mini"
    
    # Embedding 向量模型的专门配置（如果不在 .env 中配置，则默认复用上面的 OPENAI 配置）
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1024
    EMBEDDING_BATCH_SIZE: int = 32
    
    # 搜索工具配置
    TAVILY_API_KEY: str | None = None
    CRAG_WEB_SEARCH_ENABLED: bool = False
    CRAG_MAX_REWRITES: int = 1
    CRAG_MAX_WEB_SEARCHES: int = 1
    CRAG_WEB_SEARCH_TIMEOUT_SECONDS: int = 15
    CRAG_LOCAL_FAST_PATH_ENABLED: bool = True
    CRAG_FAST_PATH_MIN_EVIDENCE: int = 2
    CRAG_FAST_PATH_MIN_FUSION_SCORE: float = 0.55
    CRAG_RRF_FAST_PATH_MIN_VECTOR_SIMILARITY: float = Field(
        default=0.60, ge=0.0, le=1.0
    )
    CRAG_RRF_FAST_PATH_MAX_VECTOR_RANK: int = Field(default=5, ge=1, le=100)
    CRAG_RRF_FAST_PATH_MAX_BM25_RANK: int = Field(default=5, ge=1, le=100)

    # Interview retrieval defaults are selected from the frozen offline benchmark.
    INTERVIEW_RETRIEVAL_PROFILE: Literal[
        "VECTOR",
        "VECTOR_TRIGRAM",
        "VECTOR_RERANK",
        "VECTOR_TRIGRAM_RERANK",
        "VECTOR_BM25",
        "VECTOR_BM25_RERANK",
        "VECTOR_TRIGRAM_BM25",
        "VECTOR_TRIGRAM_BM25_RERANK",
        "VECTOR_BM25_RRF",
        "VECTOR_BM25_RRF_RERANK",
        "VECTOR_TRIGRAM_BM25_RRF",
        "VECTOR_TRIGRAM_BM25_RRF_RERANK",
    ] = "VECTOR_BM25_RRF"
    INTERVIEW_GLOBAL_RERANK_ENABLED: bool = False
    
    # Rerank 重排模型的专门配置
    RERANK_API_KEY: str | None = None
    RERANK_BASE_URL: str | None = None
    RERANK_MODEL_NAME: str = "rerank"

    # BM25 sparse retrieval service
    OPENSEARCH_URL: str | None = None
    OPENSEARCH_USERNAME: str | None = None
    OPENSEARCH_PASSWORD: str | None = None
    OPENSEARCH_INDEX_NAME: str = "interviewpilot-document-chunks"
    OPENSEARCH_TIMEOUT_SECONDS: int = 10
    
    # 单进程 AI 并发限制，防止瞬时请求过高导致 429 Rate Limit
    MAX_CONCURRENCY: int = Field(default=2, ge=1, le=100)
    AI_CONCURRENCY_WAIT_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=600)
    
    # 告诉 Pydantic 去当前目录下找 .env 文件并读取里面的变量，忽略多余的配置（extra="ignore"）
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# 实例化全局配置对象。在项目的其他文件里，只需 `from app.core.config import settings` 就能直接获取到这些值
settings = Settings()
