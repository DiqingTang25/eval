"""
结构完整性规则 (Structure Rules)

对齐:
  - CLEAR Assurance: 输出结构合规性闸门
  - TEACH-AI Consistency: 回答格式稳定性检查
  - EduAgentBench: 过程约束 (process constraints)

全确定性, 0 API 调用, 亚毫秒级延迟。
"""

import re
from dataclasses import dataclass, field


@dataclass
class StructureCheckResult:
    """结构检查结果"""
    score: float = 0.0           # 0-5 综合分
    length_ok: bool = True
    length_score: float = 5.0
    format_ok: bool = True
    format_score: float = 5.0
    lang_match: bool = True
    lang_score: float = 5.0
    markdown_valid: bool = True
    evidence: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    veto: bool = False           # 空回答触发一票否决


class StructureRules:
    """
    回答结构/长度/格式的确定性检查器

    使用方式:
        checker = StructureRules()
        result = checker.check(question="...", answer="...")
        if result.veto:
            return  # 跳过所有 LLM 评测
    """

    # ── 长度阈值 ──
    MIN_LENGTH_CHARS = 20        # 少于20字符视为过短
    IDEAL_MIN_LENGTH = 50        # 理想最小长度
    TOO_LONG_WARNING = 5000      # 过长警告

    # ── 格式正则 ──
    MARKDOWN_CODE_BLOCK = re.compile(r'```[^`]*```')
    MARKDOWN_LIST = re.compile(r'^[\s]*[-*+]|\d+\.\s', re.MULTILINE)
    MARKDOWN_HEADING = re.compile(r'^#{1,4}\s', re.MULTILINE)

    # ── 中文检测 ──
    CHINESE_CHAR = re.compile(r'[一-鿿]')

    def __init__(
        self,
        min_length: int = 20,
        ideal_min_length: int = 50,
    ):
        self.min_length = min_length
        self.ideal_min_length = ideal_min_length

    def check(self, question: str = "", answer: str = "") -> StructureCheckResult:
        """
        执行结构完整性检查

        :param question: 用户问题
        :param answer: Agent 回答
        :return: StructureCheckResult
        """
        evidence: list[str] = []
        flags: list[str] = []

        # ── 1. 空回答检测 (一票否决) ──
        if not answer or len(answer.strip()) < 3:
            return StructureCheckResult(
                score=0.0,
                length_ok=False,
                length_score=0.0,
                format_ok=False,
                format_score=0.0,
                lang_match=False,
                lang_score=0.0,
                markdown_valid=False,
                evidence=["回答为空或过短（<3字符）"],
                flags=["EMPTY_RESPONSE"],
                veto=True,
            )

        # ── 2. 长度检查 ──
        clean_answer = answer.strip()
        answer_len = len(clean_answer)
        length_score, length_ok = self._score_length(answer_len)
        evidence.append(f"回答长度: {answer_len}字符 → 长度分={length_score:.1f}")

        # ── 3. 格式检查 ──
        format_score, format_ok, format_evidence = self._score_format(clean_answer)
        evidence.extend(format_evidence)

        # ── 4. 语言一致性检查 ──
        lang_score, lang_match, lang_ev = self._check_language(question, clean_answer)
        evidence.append(lang_ev)

        # ── 5. Markdown 有效性 ──
        md_valid, md_ev = self._check_markdown(clean_answer)
        evidence.append(md_ev)

        # ── 综合评分 ──
        scores = [length_score, format_score, lang_score]
        if answer_len > 100:
            scores = [length_score, format_score, lang_score]  # 短回答不扣格式分

        composite = sum(scores) / len(scores)

        # 收集 flags
        if not length_ok:
            flags.append(f"LENGTH:长度={answer_len}字符")
        if not format_ok:
            flags.append("FORMAT:缺少结构化元素")
        if not lang_match:
            flags.append("LANG:语言不匹配")
        if not md_valid:
            flags.append("MD:Markdown格式问题")

        return StructureCheckResult(
            score=round(composite, 1),
            length_ok=length_ok,
            length_score=round(length_score, 1),
            format_ok=format_ok,
            format_score=round(format_score, 1),
            lang_match=lang_match,
            lang_score=round(lang_score, 1),
            markdown_valid=md_valid,
            evidence=evidence,
            flags=flags,
            veto=False,
        )

    def _score_length(self, char_count: int) -> tuple[float, bool]:
        """评分回答长度 (0-5)"""
        if char_count < self.min_length:
            return 1.0, False
        elif char_count < self.ideal_min_length:
            # 20-50字: 线性映射 1→3
            ratio = (char_count - self.min_length) / (self.ideal_min_length - self.min_length)
            return round(1.0 + 2.0 * ratio, 1), False
        elif char_count < 200:
            return 4.0, True
        elif char_count < 1000:
            return 5.0, True
        elif char_count < self.TOO_LONG_WARNING:
            return 4.5, True
        else:
            return 4.0, True  # 过长略扣分

    def _score_format(self, text: str) -> tuple[float, bool, list[str]]:
        """评分格式结构 (0-5)"""
        ev: list[str] = []
        score = 1.0
        has_code = bool(self.MARKDOWN_CODE_BLOCK.search(text))
        has_list = bool(self.MARKDOWN_LIST.search(text))
        has_heading = bool(self.MARKDOWN_HEADING.search(text))
        has_paragraphs = len(text.split('\n\n')) >= 2

        if has_code:
            score += 1.0
            ev.append("含代码块 (+1)")
        if has_list:
            score += 1.0
            ev.append("含列表 (+1)")
        if has_heading:
            score += 1.0
            ev.append("含标题 (+1)")
        if has_paragraphs:
            score += 1.0
            ev.append("含多段落 (+1)")

        score = min(5.0, score)
        ok = score >= 2.0
        ev.insert(0, f"格式结构: 代码={has_code} 列表={has_list} 标题={has_heading} 段落={has_paragraphs} → 格式分={score:.0f}")

        return round(score, 1), ok, ev

    def _check_language(self, question: str, answer: str) -> tuple[float, bool, str]:
        """检查中英文一致性"""
        q_has_chinese = bool(self.CHINESE_CHAR.search(question)) if question else True
        a_has_chinese = bool(self.CHINESE_CHAR.search(answer))

        if not question:
            return 5.0, True, "无问题文本，跳过语言一致性检查"

        if q_has_chinese and not a_has_chinese:
            return 2.0, False, "问题为中文但回答无中文字符 → 语言不匹配"
        elif not q_has_chinese and a_has_chinese:
            return 3.0, True, "问题非中文但回答含中文 (可能正常)"
        elif q_has_chinese and a_has_chinese:
            return 5.0, True, "中英文一致 ✓"
        else:
            return 5.0, True, "语言一致 ✓"

    def _check_markdown(self, text: str) -> tuple[bool, str]:
        """检查 Markdown 代码块是否闭合"""
        # 统计 ``` 出现次数
        backtick_blocks = self.MARKDOWN_CODE_BLOCK.findall(text)
        open_ticks = len(re.findall(r'(?<!\\)```(?!`)', text))

        if open_ticks % 2 != 0:
            return False, f"Markdown代码块未正确闭合 (```出现{open_ticks}次)"
        return True, "Markdown格式正常 ✓"
