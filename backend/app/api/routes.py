from fastapi import APIRouter, HTTPException
from app.api.models import ChatRequest, ChatResponse
from app.services.rag_engine_advanced import AgentService
from app.core.logger import logger

# 创建路由器实例
router = APIRouter()

# 知识点：这里我们只实例化一次 RAG 引擎，所有的请求都复用这一个引擎实例
# 这种单例模式可以避免每次请求进来都去连一次数据库，极大提高并发性能。
rag_service = None

def get_rag_service():
    global rag_service  # 高并发场景下，有利于提高响应，不然每次都进行资源创建  内存会爆满
    if rag_service is None:
        logger.info("⚡ 首次调用，正在初始化 Agent 引擎...")
        rag_service = AgentService()
    return rag_service

@router.post("/chat", response_model=ChatResponse, summary="问答接口 (Agent)")
async def chat_endpoint(request: ChatRequest):
    """
    接收用户提问，经过向量检索，返回大模型的回答和参考资料。
    """
    try:
        service = get_rag_service()
        
        # ==========================================
        # [历史遗留代码归档：旧版同步调用]
        # answer, chunks = service.chat(request.query, history=request.history)
        # ==========================================
        
        # 【区别点】：加入了 await。只有外层加了 await，底层引擎里的纯异步方法才能真正释放 FastAPI 的事件循环！
        answer, chunks = await service.chat(request.query, history=request.history)
        
        return ChatResponse(
            answer=answer,
            sources=chunks
        )
    except Exception as e:
        logger.error(f"处理 /chat 请求时发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
