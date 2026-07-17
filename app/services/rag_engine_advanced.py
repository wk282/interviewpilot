import os
import json
import operator
from typing import List, Dict, Any, Tuple, Optional, Annotated, TypedDict

import asyncio
from openai import AsyncOpenAI
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings
from app.core.logger import logger
from app.services.vector_store import ChromaDBManager
from app.services.tools import web_search, WEB_SEARCH_TOOL_SCHEMA
from app.services.reranker import ZhipuReranker

# ==========================================
# 高阶版 AgentState，新增 search_query 字段
# ==========================================
class AgentState(TypedDict, total=False):
    messages: Annotated[list, operator.add]
    chunks: list
    search_query: str
    parsed_resume: dict

class AgentService:
    def __init__(self, is_eval_mode: bool = False):
        self.is_eval_mode = is_eval_mode
        logger.info(f"⚙️ 正在初始化【高级进阶版】Agent 核心引擎... (评测模式: {self.is_eval_mode})")
        
        self.llm_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
        self.llm_model = settings.LLM_MODEL
        self.db_manager = ChromaDBManager()
        
        openai_ef = OpenAIEmbeddingFunction(
            api_key=settings.EMBEDDING_API_KEY,
            api_base=settings.EMBEDDING_BASE_URL,
            model_name=settings.EMBEDDING_MODEL_NAME
        )
        # 【修改 1】：连接高级独立表
        self.collection = self.db_manager.client.get_or_create_collection(
            name="interview_questions_advanced",
            embedding_function=openai_ef, # type: ignore
            metadata={"hnsw:space": "cosine"}
        )

        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        # 【修改 2】：新增 Query Rewrite 节点
        workflow.add_node("rewrite_node", self._rewrite_node)
        workflow.add_node("retrieve_node", self._retrieve_node)
        workflow.add_node("llm_node", self._llm_node)
        workflow.add_node("tool_node", self._tool_node)
        
        workflow.add_edge(START, "rewrite_node")
        workflow.add_edge("rewrite_node", "retrieve_node")
        workflow.add_edge("retrieve_node", "llm_node")
        
        workflow.add_conditional_edges(
            "llm_node",
            self._should_continue,
            {
                "continue": "tool_node",
                "end": END
            }
        )
        workflow.add_edge("tool_node", "llm_node")
        
        app = workflow.compile(checkpointer=self.memory)
        return app

    async def _rewrite_node(self, state: AgentState):
        """新增节点：查询重写，提升 Answer Relevancy"""
        user_input = state["messages"][-1].get("content", "") if state["messages"] else ""
        
        # 通过意图关键词判断是否为前端传入的简历面试模板，而不是粗暴地使用长度判断
        is_resume_intent = "我的个人简历" in user_input or "扮演一名严苛的高级技术面试官" in user_input
        
        if is_resume_intent:
            logger.info("📍 [Node: rewrite] 识别到简历提问意图，启动 JSON 结构化信息抽取...")
            prompt = f"""你是一个专业的技术招聘专家。以下可能是一份超长的简历或系统提示词。
请对其进行结构化抽取，并必须严格以 JSON 格式返回，包含以下 4 个字段：
{{
    "internship_exp": "实习经历及核心贡献(简要总结)",
    "project_exp": "项目经历、使用的核心架构及解决的难点(简要总结)",
    "tech_stack": "掌握的核心技术栈列表(逗号分隔)",
    "doubtful_points": ["可能有水分或值得深挖的技术疑点1", "疑点2", "疑点3"]
}}
请不要返回任何非 JSON 格式的文字，不要用 markdown 代码块包裹。
内容：{user_input[:2000]}"""
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MINI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw_response = response.choices[0].message.content or "{}"
            
            import re
            try:
                # 防呆解析，去除可能存在的 markdown 标签
                clean_json = re.sub(r'```json|```', '', raw_response).strip()
                parsed_resume = json.loads(clean_json)
                doubtful_points = parsed_resume.get("doubtful_points", [])
                tech_stack = parsed_resume.get("tech_stack", "")
                
                # 保留完整的项目和实习上下文，拼接成一段连贯的文本，作为后续搜索向量库的 Query
                internship = parsed_resume.get("internship_exp", "")
                project = parsed_resume.get("project_exp", "")
                tech_stack = parsed_resume.get("tech_stack", "")
                doubtful_points_str = " ".join(parsed_resume.get("doubtful_points", []))
                
                search_query = f"实习与项目经历：{internship} {project}。核心技术栈：{tech_stack}。核心技术疑点：{doubtful_points_str}"
                
                logger.info(f"📍 [Node: rewrite] 简历抽取成功，提取到完整的上下文搜索 Query: {search_query[:80]}...")
            except Exception as e:
                logger.error(f"📍 [Node: rewrite] JSON 解析失败，回退到普通截断。错误: {e}")
                parsed_resume = {}
                search_query = user_input[:200]
                
            return {"search_query": search_query, "parsed_resume": parsed_resume}
        else:
            logger.info(f"📍 [Node: rewrite] 正在对口语化提问进行高质量改写...")
            prompt = f"你是一个专业的搜索引擎查询词优化专家。请把以下用户的口语化提问，改写为极其精准、包含专业术语的搜索关键词（不要超过20个字）。\n\n用户提问：{user_input}\n\n直接返回改写后的关键词，不要有任何废话："
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MINI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            search_query = response.choices[0].message.content or user_input
            
        logger.info(f"📍 [Node: rewrite] 改写结果: '{search_query}'")
        return {"search_query": search_query}

    async def _retrieve_node(self, state: AgentState):
        """节点 1：负责从向量库进行粗排 + Rerank 精排 + Small-to-Big 还原"""
        search_query = state.get("search_query", "")
        
        user_input = state["messages"][-1].get("content", "") if state["messages"] else search_query
        
        parsed_resume = state.get("parsed_resume", {})
        
        # 【Bug 修复】：只有在我们明确提纯了结构化简历（parsed_resume 有实质内容）时，
        # 才说明原文本包含了“角色扮演”等噪声指令，此时才使用 search_query 作为 Reranker 输入。
        # 否则，一律保留原始自然语言作为 Reranker 的 Query，以便充分利用 Reranker 的 QA 对齐能力。
        if parsed_resume and any(parsed_resume.values()):
            rerank_query = search_query
        else:
            rerank_query = user_input
        
        # 我们多捞一点子节点（比如 top 6），为了能拼出几个完整的大节点
        chunks = await asyncio.to_thread(self.search, search_query, rerank_query, 6)
        
        # 【核心魔法：Small-to-Big 还原逻辑，提升 Faithfulness】
        final_parent_chunks = []
        seen_parents = set()
        
        for chunk in chunks:
            parent_id = chunk.get("parent_id")
            if parent_id and parent_id not in seen_parents:
                seen_parents.add(parent_id)
                final_parent_chunks.append({
                    "content": chunk.get("parent_content", chunk["content"]), # 用完整父节点替换子节点
                    "source": chunk["source"],
                    "similarity": chunk.get("similarity", 0)
                })
        
        # 提取去重后的前 3 个大块发给模型
        final_parent_chunks = final_parent_chunks[:3]
        logger.info(f"📍 [Node: retrieve] Small-to-Big 还原完毕，最终送给模型 {len(final_parent_chunks)} 个完整大块。")
        return {"chunks": final_parent_chunks}

    async def _llm_node(self, state: AgentState):
        logger.info("📍 [Node: llm_reasoning] 大模型开始思考并做决策...")
        messages = state["messages"]
        chunks = state.get("chunks", [])
        
        context_text = ""
        for idx, chunk in enumerate(chunks):
            context_text += f"\n--- 面经知识点 {idx+1} (来源: {chunk['source']}) ---\n{chunk['content']}\n"
            
        parsed_resume = state.get("parsed_resume")
        resume_context = ""
        if parsed_resume:
            resume_context = f"\n<结构化简历分析结果>:\n实习经历: {parsed_resume.get('internship_exp', '无')}\n项目经历: {parsed_resume.get('project_exp', '无')}\n技术栈: {parsed_resume.get('tech_stack', '无')}\n需深挖疑点: {parsed_resume.get('doubtful_points', [])}\n"
            
        if self.is_eval_mode:
            system_prompt = f"""你是一个客观、精准的专业 AI 助手（做题家模式）。
请严格根据下述【本地面试题库参考资料】的内容，直接、完整、准确地回答用户的问题。
要求：
1. 你的回答必须100%忠实于参考资料，不能加入任何主观寒暄、点评或反问。
2. 如果给定的资料不足以回答用户的问题，请直接回答“资料中未提及”。

<本地面试题库参考资料>:
{context_text}
"""
        else:
            system_prompt = f"""你是一个严苛但专业的高级技术面试官。
你的任务核心分为三种场景：
【场景 A：基于简历的深挖】如果用户在对话中发送了他的个人简历，你需要立刻阅读简历内容，然后针对他简历中的“项目经历”或“技术栈”发起一次刁钻、有深度的技术提问。千万不要泛泛而谈，必须结合<本地面试题库参考资料>中的知识点来考验他简历内容的真实性！
【场景 B：普通提问考核】如果用户单纯让你“开始面试”或“出个题”，你需要根据传入的<本地面试题库参考资料>，向用户抛出一个具体的、有深度的专业面试题。知识库内容仅供参考，不要求一字不差。一次只问一个问题！不要自问自答！
【场景 C：判卷与追问】如果用户在回答你的上一轮问题，你需要严格比对<本地面试题库参考资料>来评估他的回答。你必须在回复的开头明确给出该回答的匹配度，格式如：“**回答匹配度：85%**”。然后客观指出他对在哪里、错在哪里，并结合简历或题库进行下一轮追问。
【终极绝招：外网兜底】如果用户的回答非常超纲，或者简历上写的技术非常冷门，你必须立即调用 `web_search` 工具去互联网查找最新技术答案或核实开源项目是否存在。

<本地面试题库参考资料>:
{context_text}
{resume_context}

请注意：扮演真实的对话语气，不要每次都生硬地罗列规则。一次只能抛出一个核心问题！你的目标是探底用户的真实技术水平。
"""
        clean_messages = [msg for msg in messages if msg.get("role") != "system"]
        prompt_messages = [{"role": "system", "content": system_prompt}] + clean_messages
        
        # 控制变量法：评测模式下强制闭卷，不给搜索工具，只测试本地向量库水平
        kwargs = {
            "model": self.llm_model,
            "messages": prompt_messages,
            "temperature": 0.4
        }
        if not self.is_eval_mode:
            kwargs["tools"] = [WEB_SEARCH_TOOL_SCHEMA]
            
        response = await self.llm_client.chat.completions.create(**kwargs)  # type: ignore
        
        message = response.choices[0].message
        return {"messages": [message.model_dump(exclude_unset=True)]}

    def _should_continue(self, state: AgentState) -> str:
        last_message = state["messages"][-1]
        if last_message.get("tool_calls"):
            logger.info("📍 [Edge: router] 发现工具调用请求，路由至 tool_node")
            return "continue"
        logger.info("📍 [Edge: router] 大模型已给出最终回复，路由至 END")
        return "end"

    async def _tool_node(self, state: AgentState):
        last_message = state["messages"][-1]
        tool_calls = last_message.get("tool_calls", [])
        
        tool_messages = []
        for tool_call in tool_calls:
            if tool_call["function"]["name"] == "web_search":
                args = json.loads(tool_call["function"]["arguments"])
                query = args.get("query", "")
                logger.info(f"📍 [Node: tool_executor] 正在联网异步检索: {query}")
                
                result = await web_search(query, is_eval_mode=self.is_eval_mode)
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": "web_search",
                    "content": result
                })
        return {"messages": tool_messages}

    def search(self, search_query: str, original_query: str = "", top_k: int = 6) -> List[Dict[str, Any]]:
        recall_size = 15
        logger.info(f"🔎 正在进行高精度子块向量粗排，目标召回 {recall_size} 条...")
        results = self.collection.query(
            query_texts=[search_query],
            n_results=recall_size
        )
        documents: List[str] = results["documents"][0] if results["documents"] else []  # type: ignore
        metadatas: List[Dict[str, Any]] = results["metadatas"][0] if results["metadatas"] else []  # type: ignore
        
        if not documents:
            return []
            
        reranker = ZhipuReranker()
        # Reranker 需要理解用户的原始意图，而不是干瘪的搜索关键词。如果 query 太长则截断，防止报错。
        rerank_query = original_query[:1000] if original_query else search_query
        rerank_results = reranker.rerank(rerank_query, documents, top_n=top_k)
        
        final_chunks = []
        for r in rerank_results:
            idx = r["index"]
            score = r["relevance_score"]
            meta = metadatas[idx] if isinstance(metadatas[idx], dict) else {}
            final_chunks.append({
                "content": documents[idx],
                "source": meta.get("source", "未知文件"),
                "similarity": score * 100,
                "parent_id": meta.get("parent_id", ""),
                "parent_content": meta.get("parent_content", "")
            })
            
        logger.success(f"🎯 重排完成！已精选出 {len(final_chunks)} 个核心子切片。")
        return final_chunks

    async def chat(self, user_input: str, history: Optional[List[Dict[str, Any]]] = None, session_id: str = "default_user_1") -> Tuple[str, List[Dict[str, Any]]]:
        logger.info(f"🚀 触发进阶版 LangGraph 异步流转，Session ID: {session_id}")
        config = {"configurable": {"thread_id": session_id}}
        
        final_state = await self.graph.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config
        )
        
        answer = final_state["messages"][-1].get("content", "")
        chunks = final_state.get("chunks", [])
        return answer, chunks
