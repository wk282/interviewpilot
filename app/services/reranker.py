import requests
from typing import List, Dict, Any
from app.core.config import settings
from app.core.logger import logger

# ==========================================
# 知识点讲解: 重排模型 (Reranker)
# 为什么有了向量检索还要做重排？
# 向量检索 (Embedding) 计算的是“语义相似度”，它很快，但很粗糙，经常漏掉“字面精确匹配”的关键词。
# 重排模型 (Reranker) 则是把 Query 和 Document 拼接在一起，送到深层神经网络里去“交叉比对”，
# 打分极其精准，但计算量很大。
# 所以业界标准做法是：先用 Embedding 秒搜出 Top 10（粗排），再喂给 Reranker 精挑出 Top 3（精排）。
# ==========================================

class ZhipuReranker:
    def __init__(self):
        # 优先使用专门的 RERANK 配置，如果没有配置，则回退到 OPENAI_ 默认配置
        self.api_url = settings.RERANK_BASE_URL or "https://open.bigmodel.cn/api/paas/v4/rerank"
        self.api_key = settings.RERANK_API_KEY or settings.OPENAI_API_KEY
        self.model = settings.RERANK_MODEL_NAME or "rerank"

    def rerank(self, query: str, documents: List[str], top_n: int = 3) -> List[Dict[str, Any]]:
        """
        调用智谱的 Rerank API，对传入的 documents 进行重新打分和排序。
        返回的数据格式类似: [{"index": 2, "relevance_score": 0.89}, ...]
        """
        if not documents:
            return []
            
        logger.info(f"⚖️ 正在调用智谱 Reranker，对 {len(documents)} 条粗排结果进行精准重排...")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            # API 默认已经按得分从高到低排好序了
            return results
            
        except Exception as e:
            logger.error(f"❌ 智谱 Rerank API 调用失败: {e}")
            # 如果重排失败，作为兜底（Fallback），我们直接原样返回（模拟全得分为 0）
            # 保证系统的高可用性
            return [{"index": i, "relevance_score": 0.0} for i in range(min(top_n, len(documents)))]
