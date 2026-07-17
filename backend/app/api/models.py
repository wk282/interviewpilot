from pydantic import BaseModel, Field
from typing import List, Dict, Any

# ==========================================
# 知识点讲解:
# Pydantic 提供了基于类型的强校验能力。
# 这相当于我们和前端开发（或者调用方）签了一份“法律合同”：
# 1. 规定前端发过来的必须是 JSON，且必须包含 query 字段。
# 2. 规定我们返回给前端的必须包含 answer 和 sources 字段。
# 如果不符合规定，FastAPI 会自动拒绝请求并报错（422 Unprocessable Entity）。
# ==========================================

class ChatRequest(BaseModel):
    """前端发来的请求体结构"""
    query: str = Field(..., description="用户的提问", examples=["怎么写单例模式？"])
    history: List[Dict[str, Any]] = Field(default_factory=list, description="历史对话上下文")
    top_k: int = Field(default=3, description="需要的参考文档数量")

class ChatResponse(BaseModel):
    """后端返回的响应体结构"""
    answer: str = Field(..., description="大模型生成的回答")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="引用的源文档信息")
