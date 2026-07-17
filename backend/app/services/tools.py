from typing import Dict, Any, List
import json
from app.core.logger import logger

# ==========================================
# 知识点讲解: 大模型的 Tool Calling (工具调用)
# 大模型本身是没有手脚的，它只能做“文本接龙”。
# 但如果我们在请求 API 时，明确告诉它：“我这儿有一个叫 web_search 的函数，参数是 query，作用是搜索互联网”
# 大模型在遇到不懂的问题时，就会停止文本接龙，转而返回一个特殊的指令，要求我们（本地代码）去帮它执行这个函数。
# 拿到搜索结果后，我们再把结果喂回给大模型，它就能根据最新信息生成回答了。
# ==========================================

# ==========================================
# [旧版：同步执行，会阻塞整个 FastAPI 事件循环]
# 为什么改成异步？因为同步的 DDGS 网络请求在执行期间，FastAPI 无法处理其他并发请求，会导致吞吐量急剧下降。
# ==========================================
# def web_search(query: str, max_results: int = 3) -> str:
#     """
#     具体的搜索执行逻辑（供本地代码调用）
#     使用 duckduckgo_search 库进行免费、免梯子的互联网搜索。
#     """
#     logger.info(f"🌐 触发大模型工具调用：正在全网搜索关键词 -> '{query}'")
#     try:
#         from duckduckgo_search import DDGS
#         
#         with DDGS() as ddgs:
#             # 拿到原生的搜索结果列表
#             results = list(ddgs.text(query, max_results=max_results))
#             
#             if not results:
#                 return f"未能在互联网上找到关于 '{query}' 的相关信息。"
#             
#             # 将搜索结果拼接成大模型容易看懂的纯文本格式
#             formatted_result = ""
#             for idx, r in enumerate(results):
#                 formatted_result += f"【搜索结果 {idx+1}】\n标题：{r.get('title')}\n摘要：{r.get('body')}\n链接：{r.get('href')}\n\n"
#             
#             logger.success(f"✅ 全网搜索完成，共抓取到 {len(results)} 条网页摘要。")
#             return formatted_result
#             
#     except ImportError:
#         error_msg = "🚨 系统缺少 `duckduckgo-search` 依赖包！请在终端运行 `pip install duckduckgo-search` 后重试。"
#         logger.error(error_msg)
#         return error_msg
#     except Exception as e:
#         logger.error(f"❌ 网页搜索失败: {e}")
#         return f"网页搜索失败: {e}"

# ==========================================
# [新版：纯异步版本工具，支持极高并发]
# 区别：使用了 AsyncDDGS() 和 async with 进行真正的异步非阻塞 I/O。
# 当爬虫在等待网页响应的这几秒钟里，CPU 会立刻转头去服务其他并发进来的用户，单核并发能力提升百倍。
# ==========================================
async def web_search(query: str, max_results: int = 3, is_eval_mode: bool = False) -> str:
    """
    异步版本的互联网搜索逻辑，极大地提升高并发下的响应能力。
    双模态架构：面试阶段使用 Tavily (稳定高质)，评测阶段使用本地代理的 DDGS (白嫖无限)。
    """
    logger.info(f"🌐 触发大模型工具调用：正在全网异步搜索关键词 -> '{query}' (评测模式: {is_eval_mode})")
    try:
        from app.core.config import settings
        import asyncio
        import requests
        
        def _sync_search():
            # 【评测模式】：使用本地 Clash 代理白嫖 DuckDuckGo
            if is_eval_mode:
                from duckduckgo_search import DDGS
                return list(DDGS(proxy="http://127.0.0.1:7897").text(query, max_results=max_results, backend="html"))
            
            # 【面试模式】：使用稳定的 Tavily API
            else:
                if not settings.TAVILY_API_KEY:
                    raise ValueError("未配置 TAVILY_API_KEY，请在 .env 中设置")
                
                payload = {
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results
                }
                resp = requests.post("https://api.tavily.com/search", json=payload, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                # 转换 Tavily 的格式为类似 DDGS 的格式，方便下方统一解析
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "body": item.get("content", ""),
                        "href": item.get("url", "")
                    })
                return results

        results = await asyncio.to_thread(_sync_search)
        
        if not results:
            return f"未能在互联网上找到关于 '{query}' 的相关信息。"
        
        # 将搜索结果拼接成大模型容易看懂的纯文本格式
        formatted_result = ""
        for idx, r in enumerate(results):
            formatted_result += f"【搜索结果 {idx+1}】\n标题：{r.get('title')}\n摘要：{r.get('body')}\n链接：{r.get('href')}\n\n"
        
        logger.success(f"✅ 全网异步搜索完成，共抓取到 {len(results)} 条网页摘要。")
        logger.info(f"📚 格式化后的搜索结果：{formatted_result}")
        return formatted_result
            
    except ImportError:
        error_msg = "🚨 系统缺少 `duckduckgo-search` 依赖包！请在终端运行 `pip install duckduckgo-search` 后重试。"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        logger.error(f"❌ 网页异步搜索失败: {e}")
        return f"网页搜索失败: {e}"

# 这里非常关键！这是严格遵守 OpenAI 协议的 Tool 定义格式 (JSON Schema)。
# 大模型就是看着这段说明书，才知道怎么用你的工具的。
WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "当且仅当本地面试题库中没有答案，或者用户询问最新鲜的知识、互联网上的公开信息时，调用此工具进行全网搜索兜底。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "需要搜索引擎去查询的精确关键词，如 'Python 3.12 新特性' 或 '最新大模型排行'"
                }
            },
            "required": ["query"]
        }
    }
}
