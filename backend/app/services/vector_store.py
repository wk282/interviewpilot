import os
import chromadb
from app.core.logger import logger

# ==========================================
# 知识点讲解:
# 为什么要用向量数据库（Vector DB）？
# 传统关系型数据库（如 MySQL）只能做精确匹配（`WHERE text LIKE "%西瓜%"`）。
# 向量数据库存储的是经过 Embedding 转化的高维浮点数组。
# 当大模型把用户的问题转化为向量后，数据库就能通过“余弦相似度”或“欧氏距离”进行“模糊语义检索”。
# ==========================================

class ChromaDBManager:
    _instance = None  # 单例模式，防止多次初始化连接导致文件锁冲突

    def __new__(cls, persist_directory: str | None = None):
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super(ChromaDBManager, cls).__new__(cls)
            cls._instance._init_client(persist_directory)
        return cls._instance

    def _init_client(self, persist_directory: str | None = None):
        if persist_directory is None:
            # 默认存储到 data/processed/chroma_db 空的就创建一个文件
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.persist_directory = os.path.join(project_root, "data", "processed", "chroma_db")
        else:
            self.persist_directory = persist_directory

        logger.info(f"💾 初始化 ChromaDB 客户端，持久化存储路径: {self.persist_directory}")
        # 确保目录存在
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # 创建持久化客户端
        self.client = chromadb.PersistentClient(path=self.persist_directory)

    def get_or_create_collection(self, collection_name: str = "interview_questions"):
        """获取或创建一个集合（类似于关系型数据库中的 Table）"""
        # 我们使用 cosine 余弦相似度来作为距离度量标准
        collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"} # HNSW 算法配置：使用余弦距离
        )
        return collection
