"""
L2 算法评分模块 — 不依赖大模型，提供可解释的量化评分

在三层级联架构中的位置:
  L1 (rules/): 规则闸门 — 结构/事实/SLA/安全 → 30%
  L2 (此模块): 算法增强 — 语义相似度/关键词覆盖/边界分数 → 10%
  L3 (evaluator.py): LLM多Judge — 深度语义/教学策略 → 60%

对齐:
  - CLEAR Efficacy: 可解释的算法评分作为LLM评分的基线
  - TEACH-AI Explainability: 语义相似度提供可追溯的评分证据
  - EduAgentBench: 目标知识组件(KC)的关键词覆盖

v3.3: 默认启用 (evaluator.py 中 use_embedding=True, use_structure=True)
v3.4: Embedding 改为云端 API (硅基流动 bge-m3), 不再本地跑 torch
"""
import os
import jieba
import numpy as np

# ── 云端 Embedding API (硅基流动 SiliconFlow, OpenAI 兼容) ──
# 不再本地跑 SentenceTransformer/torch (~2GB), 改为按需调用免费 embedding API,
# 服务器零磁盘/内存占用。缺 openai 库或未配 key 时优雅降级 (由调用方 try/except 处理)。
try:
    from openai import OpenAI
    _OPENAI_SDK_AVAILABLE = True
except ImportError:
    OpenAI = None
    _OPENAI_SDK_AVAILABLE = False


def _cosine(a, b) -> float:
    """两个向量的余弦相似度 (numpy, 零外部依赖)"""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


class EmbeddingSimilarity:
    """语义相似度评分（答案相关性）— 云端 embedding API 版

    优先级:
      1. XJTLU AI Gateway (君谋校内向量模型, 免费低延迟)
      2. 硅基流动 bge-m3 (公网, 需要 API Key)

    XJTLU 配置环境变量:
      XJTLU_EMBEDDING_API_KEY / XJTLU_EMBEDDING_MODEL_ID / XJTLU_BASE_URL

    SiliconFlow 配置环境变量:
      SILICONFLOW_API_KEY / SILICONFLOW_BASE_URL / EMBEDDING_MODEL
    """
    def __init__(self, model_name: str = None):
        if not _OPENAI_SDK_AVAILABLE:
            raise RuntimeError("openai SDK 未安装, embedding API 不可用")

        # ── 提供商选择: XJTLU 优先 → SiliconFlow 回退 ──
        xjtl_key = os.getenv("XJTLU_EMBEDDING_API_KEY", "").strip()
        xjtl_model = os.getenv("XJTLU_EMBEDDING_MODEL_ID", "").strip()
        xjtl_base = os.getenv("XJTLU_BASE_URL", "").strip()

        if xjtl_key and xjtl_model and xjtl_base:
            self.provider = "xjtl"
            self.model = model_name or xjtl_model
            self.client = OpenAI(api_key=xjtl_key, base_url=xjtl_base)
            self._encoding_format = "float"  # XJTLU网关必须显式传float, 否则base64不兼容
        else:
            sf_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
            if not sf_key:
                raise RuntimeError(
                    "XJTLU_EMBEDDING_API_KEY 和 SILICONFLOW_API_KEY 均未配置, "
                    "embedding 不可用 (配置其一即可启用语义相似度)"
                )
            self.provider = "siliconflow"
            base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
            self.model = model_name or os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
            self.client = OpenAI(api_key=sf_key, base_url=base_url)
            self._encoding_format = None  # SiliconFlow 默认即可

    def embed_text(self, text: str) -> list[float]:
        """返回单文本的原始 embedding 向量 (Phase 2: 证据记忆 + 金标准RAG)

        用法:
            emb = EmbeddingSimilarity()
            vec = emb.embed_text("some text")
            # vec is list[float] of 1024 or 3072 dims
        """
        kwargs = {"model": self.model, "input": text[:8000]}
        if self._encoding_format:
            kwargs["encoding_format"] = self._encoding_format
        resp = self.client.embeddings.create(**kwargs)
        return resp.data[0].embedding

    def _embed_pair(self, question: str, answer: str):
        """一次请求拿两个文本的向量"""
        kwargs = {"model": self.model, "input": [question, answer]}
        if self._encoding_format:
            kwargs["encoding_format"] = self._encoding_format
        resp = self.client.embeddings.create(**kwargs)
        return resp.data[0].embedding, resp.data[1].embedding

    def compute(self, question, answer):
        """返回1-5分"""
        if not answer or len(answer.strip()) < 5:
            return 1.0

        emb_q, emb_a = self._embed_pair(question, answer)
        sim = _cosine(emb_q, emb_a)

        # 映射到1-5分：相似度0.3以下得1分，0.9以上得5分
        if sim < 0.3:
            score = 1.0
        else:
            score = 1 + 4 * (sim - 0.3) / 0.6
            score = min(5.0, score)
        return round(score, 1)

    def get_evidence(self, question, answer):
        """返回可解释证据"""
        emb_q, emb_a = self._embed_pair(question, answer)
        sim = _cosine(emb_q, emb_a)
        if not answer or len(answer.strip()) < 5:
            score = 1.0
        elif sim < 0.3:
            score = 1.0
        else:
            score = round(min(5.0, 1 + 4 * (sim - 0.3) / 0.6), 1)
        return {
            "method": "embedding_api",
            "model": self.model,
            "similarity": round(sim, 3),
            "score": score
        }


class StructureCoverage:
    """结构化要点覆盖评分（内容完整性）"""
    def __init__(self):
        # 停用词（简单版，可根据需要扩充）
        self.stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "它", "他", "她", "对", "能", "而", "之", "与", "及", "等", "但", "或", "并", "则", "其", "于"}
    
    def _extract_keywords(self, text, top_n=5):
        """提取文本中的高频关键词（实体/名词）"""
        words = jieba.lcut(text)
        # 过滤：去掉停用词和单字
        words = [w for w in words if w not in self.stopwords and len(w) > 1]
        # 统计词频
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:top_n]]
    
    def compute(self, golden_answer, agent_answer):
        """返回1-5分"""
        if not golden_answer or not agent_answer:
            return 1.0
        
        ref_keywords = self._extract_keywords(golden_answer, top_n=5)
        if not ref_keywords:
            return 3.0  # 无法提取关键词时给中等分
        
        agent_keywords = set(self._extract_keywords(agent_answer, top_n=10))
        covered = [kw for kw in ref_keywords if kw in agent_keywords]
        coverage = len(covered) / len(ref_keywords) if ref_keywords else 0
        score = 1 + 4 * coverage
        return round(score, 1)
    
    def get_evidence(self, golden_answer, agent_answer):
        """返回可解释证据"""
        ref_keywords = self._extract_keywords(golden_answer, top_n=5)
        agent_keywords = set(self._extract_keywords(agent_answer, top_n=10))
        covered = [kw for kw in ref_keywords if kw in agent_keywords]
        missed = [kw for kw in ref_keywords if kw not in agent_keywords]
        coverage = len(covered) / len(ref_keywords) if ref_keywords else 0
        score = 1 + 4 * coverage
        return {
            "method": "structure",
            "ref_keywords": ref_keywords,
            "covered": covered,
            "missed": missed,
            "coverage": round(coverage, 3),
            "score": round(score, 1)
        }


class BoundaryScore:
    """边界合规性评分 — 基于知识库 semantic overlap"""

    def __init__(self, high_threshold=0.7, low_threshold=0.3):
        """
        :param high_threshold: 高于此值视为完全在范围内 (→ 5分)
        :param low_threshold: 低于此值视为越界 (→ 1分)
        """
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold

    def compute(self, kb_scores: list[float]) -> float:
        """
        根据知识库检索分数计算边界合规性 (1-5分)

        :param kb_scores: 知识库检索的相关性分数列表
        :return: 1-5分
        """
        if not kb_scores:
            return 1.0

        max_score = max(kb_scores)
        avg_score = sum(kb_scores) / len(kb_scores)

        # 加权：最大值权重 0.6，平均值 0.4
        combined = 0.6 * max_score + 0.4 * avg_score

        if combined >= self.high_threshold:
            score = 4.0 + (combined - self.high_threshold) / (1.0 - self.high_threshold)
        elif combined >= self.low_threshold:
            score = 1.0 + 3.0 * (combined - self.low_threshold) / (self.high_threshold - self.low_threshold)
        else:
            score = 1.0

        return round(min(5.0, max(1.0, score)), 1)

    def get_evidence(self, kb_scores: list[float]) -> dict:
        """返回可解释证据"""
        score = self.compute(kb_scores)
        max_score = max(kb_scores) if kb_scores else 0
        avg_score = sum(kb_scores) / len(kb_scores) if kb_scores else 0

        if score >= 4.0:
            level = "答案完全在课程大纲范围内"
        elif score >= 2.5:
            level = "答案部分在课程大纲范围内"
        else:
            level = "答案超出课程大纲范围"

        return {
            "method": "boundary_check",
            "max_kb_score": round(max_score, 3),
            "avg_kb_score": round(avg_score, 3),
            "boundary_score": score,
            "level": level,
        }


# 简单自测（可单独运行）
if __name__ == "__main__":
    # 测试 Embedding
    emb = EmbeddingSimilarity()
    q = "ESP32-S3 的 ADC 分辨率是多少？"
    a = "ESP32-S3 的 ADC 是 12 位的，分辨率 0-4095。"
    print("Embedding 相似度得分:", emb.compute(q, a))
    print("证据:", emb.get_evidence(q, a))
    
    # 测试 Structure
    struct = StructureCoverage()
    golden = "ADC 分辨率 12 位 0-4095"
    agent = "12 位 ADC，范围 0 到 4095"
    print("结构化覆盖得分:", struct.compute(golden, agent))
    print("证据:", struct.get_evidence(golden, agent))