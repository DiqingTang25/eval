"""
事实锚点规则 (Fact Anchor Rules)

对齐:
  - CLEAR Efficacy: 事实正确性的确定性基底
  - TEACH-AI Explainability: 可追溯的事实证据
  - EduAgentBench: 基于目标知识组件(KC)的 verification

通过黄金答案的关键词/数字/否定词匹配提供确定性事实基底。
全本地计算, 0 API 调用, <1ms 延迟。
"""

import re
import jieba
from dataclasses import dataclass, field


@dataclass
class FactCheckResult:
    """事实锚点检查结果"""
    score: float = 0.0               # 0-5 综合分
    keyword_hit_rate: float = 0.0    # 关键词命中率
    keyword_hit: list[str] = field(default_factory=list)
    keyword_miss: list[str] = field(default_factory=list)
    numeric_match_rate: float = 0.0  # 数字精确匹配率
    numeric_hit: list[str] = field(default_factory=list)
    numeric_miss: list[str] = field(default_factory=list)
    negation_ok: bool = True         # 否定词方向正确
    negation_detail: str = ""
    evidence: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


class FactRules:
    """
    事实锚点确定性检查器

    通过黄金答案提取关键事实锚点，在 Agent 回答中进行匹配:
      1. 关键词提取与命中率 (jieba 分词)
      2. 关键数字精确匹配
      3. 否定词方向检查

    使用方式:
        checker = FactRules()
        result = checker.check(golden_answer="...", agent_answer="...")
        # result.score 可直接作为 correctness 维度的确定性基底
    """

    # ── 停用词 ──
    STOPWORDS: set[str] = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "那",
        "它", "他", "她", "对", "能", "而", "之", "与", "及", "等",
        "但", "或", "并", "则", "其", "于", "可以", "使用", "需要",
        "通过", "进行", "包括", "例如", "其中", "一般", "比较", "主要",
        "不同", "相关", "是否", "可能", "应该", "这个", "那个", "一些",
    }

    # ── 数字提取正则 ──
    NUMERIC_PATTERN = re.compile(
        r'\d+(?:\.\d+)?(?:\s*(?:位|个|条|次|秒|ms|mm|cm|m|kg|g|V|A|W|Hz|GHz|MHz|GB|MB|KB|%|°))?'
    )
    # 提取纯数值（带上下文）
    NUMERIC_WITH_CONTEXT = re.compile(
        r'(\d+(?:\.\d+)?)\s*(位|个|条|次|秒|毫秒|ms|mm|cm|m|kg|g|V|A|W|Hz|GHz|MHz|GB|MB|KB|比特|%)?'
    )

    # ── 否定词 ──
    NEGATION_WORDS = {"不", "并非", "不是", "没有", "无", "非", "禁止", "不可", "不能", "不应"}

    def __init__(self, top_n_keywords: int = 8):
        self.top_n_keywords = top_n_keywords

    def check(
        self,
        golden_answer: str = "",
        agent_answer: str = "",
    ) -> FactCheckResult:
        """
        执行事实锚点检查

        :param golden_answer: 黄金标准答案
        :param agent_answer: Agent 回答
        :return: FactCheckResult
        """
        evidence: list[str] = []
        flags: list[str] = []

        # ── 前提检查 ──
        if not golden_answer or not agent_answer:
            return FactCheckResult(
                score=3.0,
                evidence=["无黄金答案或Agent回答为空，跳过事实锚点检查"],
                flags=["NO_GOLDEN_ANSWER"] if not golden_answer else ["EMPTY_AGENT_ANSWER"],
            )

        # ── 1. 关键词提取与命中 ──
        ref_keywords = self._extract_keywords(golden_answer)
        agent_words = set(jieba.lcut(agent_answer))

        keyword_hit = [kw for kw in ref_keywords if kw in agent_words]
        keyword_miss = [kw for kw in ref_keywords if kw not in agent_words]
        hit_rate = len(keyword_hit) / len(ref_keywords) if ref_keywords else 0.0

        # 关键词分: 0-5
        kw_score = self._keyword_to_score(hit_rate)
        evidence.append(
            f"关键词命中: {len(keyword_hit)}/{len(ref_keywords)} "
            f"({hit_rate:.0%}) → 命中=[{', '.join(keyword_hit[:8])}] "
            f"缺失=[{', '.join(keyword_miss[:5])}] → 分={kw_score:.1f}"
        )

        if hit_rate < 0.3:
            flags.append(f"FACT_KEYWORD:命中率仅{hit_rate:.0%}")

        # ── 2. 数字精确匹配 ──
        ref_numbers = self._extract_numbers(golden_answer)
        agent_numbers = self._extract_numbers(agent_answer)

        numeric_hit = [n for n in ref_numbers if n in agent_numbers]
        numeric_miss = [n for n in ref_numbers if n not in agent_numbers]
        num_rate = len(numeric_hit) / len(ref_numbers) if ref_numbers else 1.0

        num_score = self._keyword_to_score(num_rate)
        evidence.append(
            f"数字匹配: {len(numeric_hit)}/{len(ref_numbers)} "
            f"({num_rate:.0%}) → 命中={numeric_hit} 缺失={numeric_miss} → 分={num_score:.1f}"
        )

        if num_rate < 0.5 and ref_numbers:
            flags.append(f"FACT_NUMERIC:数字匹配率仅{num_rate:.0%}")

        # ── 3. 否定词方向检查 ──
        negation_ok, neg_detail = self._check_negation_direction(golden_answer, agent_answer)
        evidence.append(neg_detail)
        if not negation_ok:
            flags.append("FACT_NEGATION:否定词方向错误")

        # ── 综合评分 ──
        # 关键词权重 0.5, 数字权重 0.3, 否定词 0.2
        composite = kw_score * 0.5 + num_score * 0.3 + (5.0 if negation_ok else 0.0) * 0.2

        return FactCheckResult(
            score=round(min(5.0, composite), 1),
            keyword_hit_rate=round(hit_rate, 3),
            keyword_hit=keyword_hit,
            keyword_miss=keyword_miss,
            numeric_match_rate=round(num_rate, 3),
            numeric_hit=numeric_hit,
            numeric_miss=numeric_miss,
            negation_ok=negation_ok,
            negation_detail=neg_detail,
            evidence=evidence,
            flags=flags,
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词（jieba 分词 + 停用词过滤 + 词频排序）"""
        if not text:
            return []

        words = jieba.lcut(text)
        # 过滤: 去掉停用词、单字、纯数字
        filtered = [
            w for w in words
            if w not in self.STOPWORDS
            and len(w) > 1
            and not w.isdigit()
            and not re.match(r'^[\d\.\+\-\*\/]+$', w)
        ]

        # 词频统计
        freq: dict[str, int] = {}
        for w in filtered:
            freq[w] = freq.get(w, 0) + 1

        # 按频次排序取 top_n
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:self.top_n_keywords]]

    def _extract_numbers(self, text: str) -> list[str]:
        """提取文本中的关键数字（带上下文单位）"""
        if not text:
            return []
        matches = self.NUMERIC_WITH_CONTEXT.findall(text)
        # 拼接数字+单位
        return [f"{m[0]}{m[1]}" if m[1] else m[0] for m in matches]

    def _keyword_to_score(self, hit_rate: float) -> float:
        """命中率 → 0-5 分数"""
        if hit_rate >= 0.8:
            return 5.0
        elif hit_rate >= 0.6:
            return 4.0 + (hit_rate - 0.6) / 0.2  # 4.0-5.0
        elif hit_rate >= 0.4:
            return 3.0 + (hit_rate - 0.4) / 0.2  # 3.0-4.0
        elif hit_rate >= 0.2:
            return 2.0 + (hit_rate - 0.2) / 0.2  # 2.0-3.0
        elif hit_rate > 0:
            return 1.0 + hit_rate / 0.2          # 1.0-2.0
        else:
            return 1.0

    def _check_negation_direction(self, golden: str, agent: str) -> tuple[bool, str]:
        """
        检查 Agent 回答的否定方向是否与黄金答案一致

        核心逻辑: 如果黄金答案说"不是X"，Agent说"是X"→方向错误
        """
        golden_sents = re.split(r'[。！？；\n]', golden)
        agent_sents = re.split(r'[。！？；\n]', agent)

        # 从黄金答案提取否定句
        golden_negated_terms = set()
        for sent in golden_sents:
            for neg in self.NEGATION_WORDS:
                if neg in sent:
                    # 提取被否定的概念
                    idx = sent.index(neg)
                    after_neg = sent[idx + len(neg):idx + len(neg) + 20].strip()
                    if after_neg:
                        golden_negated_terms.add(after_neg)
                    break

        if not golden_negated_terms:
            return True, "黄金答案无否定表述，跳过方向检查"

        # 检查Agent是否误"肯定"了黄金答案中的否定概念
        violations = []
        for term in golden_negated_terms:
            for sent in agent_sents:
                if term in sent:
                    has_agent_neg = any(neg in sent for neg in self.NEGATION_WORDS)
                    if not has_agent_neg:
                        violations.append(term)

        if violations:
            return False, f"否定方向错误: 黄金答案否定'{violations}'但Agent给予了肯定回答"

        return True, f"否定方向一致 ✓ (检查了{len(golden_negated_terms)}个否定表述)"
