# =============================================================================
# memory_plugin.py
# 通用AI助手向量记忆插件（基于ChromaDB+嵌入模型）
# 与主程序完全解耦：删除本文件后主程序无报错，仅失去长期语义记忆功能
#
# 核心特性
# --------
# 1. 持久化向量存储：使用ChromaDB本地数据库保存对话记忆
# 2. 语义检索：基于嵌入模型实现上下文相关的记忆召回
# 3. 自动保存：每次对话自动将用户提问和AI回复存入记忆库
# 4. 多模态兼容：适配火山方舟多模态嵌入模型返回格式
# =============================================================================
import requests
import time
import chromadb
import os

# =============================== 【可替换】核心配置区 ===============================
# 
# 嵌入模型API配置
EMBED_API_KEY = "YOUR_EMBED_API_KEY_HERE"  # ⚠️ 你的嵌入模型API密钥
EMBED_ENDPOINT = "YOUR_EMBED_ENDPOINT_ID_HERE"  # ⚠️ 你的嵌入模型端点ID
EMBED_URL = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"  # 【可替换】API地址

# 向量数据库配置
DB_PATH = os.path.dirname(os.path.abspath(__file__))  # 【可替换】数据库存储路径
COLLECTION_NAME = "ai_pet_memory"  # 【可替换】数据库集合名称
REQUEST_TIMEOUT = 10  # 【可替换】API请求超时时间（秒）
# ==============================================================================

class MemoryPlugin:
    def __init__(self):
        # 创建数据库目录（如果不存在）
        if not os.path.exists(DB_PATH):
            os.makedirs(DB_PATH)
        
        # 初始化ChromaDB持久化客户端
        self.client = chromadb.PersistentClient(path=DB_PATH)
        # 获取或创建记忆集合
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

    def _get_vector(self, text):
        """
        调用嵌入模型API将文本转换为向量
        返回向量列表，失败返回None
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {EMBED_API_KEY}"
        }
        
        payload = {
            "model": EMBED_ENDPOINT,
            "input": [
                {
                    "type": "text",
                    "text": text
                }
            ],
            "encoding_format": "float"
        }
        
        try:
            res = requests.post(EMBED_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            print(f"[记忆] 向量API返回状态码: {res.status_code}")
            
            data = res.json()
            # 适配火山方舟多模态嵌入模型返回格式
            # 注意：如果使用单模态嵌入模型，可能需要改为 data['data'][0]['embedding']
            if 'data' in data and 'embedding' in data['data']:
                return data['data']['embedding']
            else:
                print(f"[记忆] 嵌入模型返回异常: {data}")
                return None
                
        except Exception as e:
            print(f"[记忆] 获取向量失败: {e}")
            return None

    def save_memory(self, user_msg, ai_reply):
        """
        公开接口：保存对话记忆
        主程序在收到AI回复后自动调用此方法
        """
        vector = self._get_vector(user_msg)
        if vector:
            # 【可替换】记忆存储格式
            content = f"用户说:{user_msg} | AI回答:{ai_reply}"
            self.collection.add(
                embeddings=[vector],
                documents=[content],
                ids=[str(time.time())]  # 使用时间戳作为唯一ID
            )
            print("[记忆] 已保存本次对话到长期记忆库。")

    def search_memory(self, current_query):
        """
        公开接口：检索与当前查询最相关的记忆
        返回最相关的一条记忆文本，无结果返回空字符串
        """
        vector = self._get_vector(current_query)
        if vector:
            try:
                # 【可替换】检索结果数量，n_results=1表示只返回最相关的1条
                results = self.collection.query(query_embeddings=[vector], n_results=1)
                if results['documents'] and len(results['documents'][0]) > 0:
                    return results['documents'][0][0]
            except Exception as e:
                print(f"[记忆] 检索失败: {e}")
        return ""