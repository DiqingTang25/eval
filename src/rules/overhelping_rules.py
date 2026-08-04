"""
过度帮助检测规则 (Overhelping Detection Rules) v3.4

对齐:
  - PEBBLE (NeurIPS 2025): Overhelping Penalty — 处罚直接给答案行为
  - MRBench: Revealing of the Answer 非对称评分
  - TEACH-AI Learning Exploration: Socratic引导 vs 灌输式

检测 Agent 是否在教学过程中过度帮助——直接给出答案/代码而非引导学生思考。
这是 LLM 教学助手最常见的失败模式。

全确定性规则, 0 API 调用, <5ms 延迟。
"""

import re
import jieba
from dataclasses import dataclass, field


@dataclass
class OverhelpingCheckResult:
    """过度帮助检查结果"""
    score: float = 0.0                     # 0-5 综合分 (5=完全无过度帮助)
    has_overhelping: bool = False          # 是否检测到过度帮助

    # 子检测结果
    answer_revealed: bool = False          # 是否直接泄露了答案
    answer_revelation_rate: float = 0.0    # 答案泄露率 (0-1)
    code_exposed_before_guidance: bool = False  # 引导前就暴露代码
    code_blocks_count: int = 0             # 代码块数量
    dialogue_dominance_ratio: float = 0.0  # Agent输出/学生输出比
    has_guidance_question: bool = False    # 是否包含引导性提问
    guidance_question_count: int = 0       # 引导性提问数量

    evidence: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class OverhelpingRules:
    """
    过度帮助确定性检测器

    检测维度:
      1. 答案暴露率 — Agent回答与黄金答案的关键词/结构重叠度是否过高
      2. 代码暴露时机 — 代码块是否出现在Socratic引导之前
      3. 对话主导比 — Agent输出是否远超学生(<20%)，变成独角戏
      4. 引导性提问缺失 — Agent回答中是否有任何形式的反问/引导

    使用方式:
        checker = OverhelpingRules()
        result = checker.check(
            agent_answer="...",
            golden_answer="...",
            student_input="...",
            turn_number=1,
        )
        # result.score 可直接作为 guidance 维度的负向调节因子
    """

    # ── 引导性提问模式 ──
    GUIDANCE_QUESTION_PATTERNS: list[re.Pattern] = [
        re.compile(r'你.{0,10}(觉得|认为|理解|知道|想|尝试|试试|做过)'),
        re.compile(r'(先|请|试着|不妨|可以).{0,10}(思考|想想|分析|推导|设计|实现)'),
        re.compile(r'[？?]'),                    # 任何问号
        re.compile(r'(什么|怎么|如何|为什么|是不是|对不对|会不会|能不能)'),
        re.compile(r'(之前|前面|上一).{0,10}(讲过|学过|提到)'),
        re.compile(r'(你还记得|你了解|你听说过|你学过)'),
        re.compile(r'(能|可以|会|敢).{0,5}(吗|么|不)'),
        re.compile(r'(然后|接下来|下一步).*(呢|？|\?|怎么)'),
        re.compile(r'(试试|练习|挑战).*(吧|一下|看)'),
    ]

    # ── 直接给答案的信号模式 ──
    DIRECT_ANSWER_PATTERNS: list[str] = [
        "答案是", "正确答案", "完整代码", "直接给你", "就是这样",
        "你只需要", "照做就行", "复制粘贴", "运行即可",
        "下面就是", "这是完整的", "我已经帮你", "帮你写好了",
    ]

    def __init__(self):
        self.stopwords = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
            "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
            "你", "会", "着", "没有", "看", "好", "自己", "这", "那",
            "它", "他", "她", "对", "能", "而", "之", "与", "及", "等",
        }

    def check(
        self,
        agent_answer: str = "",
        golden_answer: str = "",
        student_input: str = "",
        turn_number: int = 1,
        total_turns: int = 1,
    ) -> OverhelpingCheckResult:
        """
        执行过度帮助检测

        :param agent_answer: Agent 的完整回答
        :param golden_answer: 黄金标准答案
        :param student_input: 学生在这轮对话中的输入
        :param turn_number: 当前轮次
        :param total_turns: 总轮次数
        :return: OverhelpingCheckResult
        """
        evidence: list[str] = []
        flags: list[str] = []
        details: dict = {}

        if not agent_answer:
            return OverhelpingCheckResult(
                score=5.0,
                evidence=["Agent回答为空，默认无过度帮助"],
            )

        # ── 1. 答案暴露率检测 ──
        answer_revealed, revelation_rate, rev_detail = self._check_answer_revelation(
            agent_answer, golden_answer
        )
        details["answer_revelation_rate"] = revelation_rate
        evidence.append(rev_detail)
        if answer_revealed:
            flags.append("OVERHELP_REVELATION:Agent直接泄露了答案")

        # ── 2. 代码暴露时机检测 ──
        code_blocks = self._count_code_blocks(agent_answer)
        code_before_guidance, code_detail = self._check_code_exposure_timing(
            agent_answer, turn_number, total_turns
        )
        details["code_blocks_count"] = code_blocks
        details["code_exposed_early"] = code_before_guidance
        evidence.append(code_detail)
        if code_before_guidance:
            flags.append("OVERHELP_CODE:引导前暴露完整代码")

        # ── 3. 对话主导比检测 ──
        dominance_ratio, dom_detail = self._check_dialogue_dominance(
            agent_answer, student_input
        )
        details["dialogue_dominance_ratio"] = dominance_ratio
        evidence.append(dom_detail)
        if dominance_ratio > 3.0:
            flags.append(f"OVERHELP_DOMINANCE:Agent主导比{dominance_ratio:.1f}:1")

        # ── 4. 引导性提问检测 ──
        has_guidance, guidance_count, guide_detail = self._check_guidance_questions(
            agent_answer
        )
        details["has_guidance_question"] = has_guidance
        details["guidance_question_count"] = guidance_count
        evidence.append(guide_detail)
        if not has_guidance:
            flags.append("OVERHELP_NO_GUIDANCE:回答无引导性提问")

        # ── 5. 直接给答案的文本信号 ──
        direct_signals = self._check_direct_answer_signals(agent_answer)
        details["direct_answer_signals"] = direct_signals
        if direct_signals:
            evidence.append(f"直接给答案信号: {direct_signals}")
            flags.append(f"OVERHELP_DIRECT:包含{len(direct_signals)}个直接给答案信号")

        # ── 综合评分 ──
        score = self._compute_score(
            answer_revealed=answer_revealed,
            revelation_rate=revelation_rate,
            code_before_guidance=code_before_guidance,
            dominance_ratio=dominance_ratio,
            has_guidance=has_guidance,
            direct_signals_count=len(direct_signals),
        )

        return OverhelpingCheckResult(
            score=score,
            has_overhelping=(
                answer_revealed
                or code_before_guidance
                or dominance_ratio > 3.0
                or not has_guidance
                or len(direct_signals) > 2
            ),
            answer_revealed=answer_revealed,
            answer_revelation_rate=revelation_rate,
            code_exposed_before_guidance=code_before_guidance,
            code_blocks_count=code_blocks,
            dialogue_dominance_ratio=dominance_ratio,
            has_guidance_question=has_guidance,
            guidance_question_count=guidance_count,
            evidence=evidence,
            flags=flags,
            details=details,
        )

    # ═══════════════════════════════════════════════════
    # 子检测方法
    # ═══════════════════════════════════════════════════

    def _check_answer_revelation(
        self, agent_answer: str, golden_answer: str
    ) -> tuple[bool, float, str]:
        """
        检测 Agent 回答是否直接暴露了黄金答案的核心内容

        方法: 提取双方的top关键词，计算重叠率
        重叠率>80% → 直接泄露答案
        """
        if not golden_answer or len(golden_answer) < 10:
            return False, 0.0, "黄金答案过短，跳过泄露检测"

        # 提取关键词
        gold_keywords = set(self._extract_keywords(golden_answer, top_n=10))
        agent_keywords = set(self._extract_keywords(agent_answer, top_n=15))

        if not gold_keywords:
            return False, 0.0, "无法提取黄金答案关键词"

        overlap = gold_keywords & agent_keywords
        overlap_rate = len(overlap) / len(gold_keywords)

        if overlap_rate >= 0.80:
            return (
                True,
                overlap_rate,
                f"⚠️ 答案泄露: 关键词重叠率{overlap_rate:.0%} "
                f"(重合: {', '.join(sorted(overlap)[:8])})",
            )
        elif overlap_rate >= 0.50:
            return (
                False,
                overlap_rate,
                f"⚠️ 部分泄露风险: 关键词重叠率{overlap_rate:.0%}",
            )
        else:
            return (
                False,
                overlap_rate,
                f"答案泄露检测通过: 重叠率{overlap_rate:.0%} ✓",
            )

    def _check_code_exposure_timing(
        self, agent_answer: str, turn_number: int, total_turns: int
    ) -> tuple[bool, str]:
        """
        检测代码块是否在Socratic引导之前就暴露了

        规则:
          - 第1轮且总轮次>1 → 检查是否应该先引导而非给代码
          - 回答中出现```代码块 + 前面无引导性提问 → 过度帮助
        """
        has_code = bool(re.search(r'```[\s\S]*?```', agent_answer))
        if not has_code:
            return False, "无代码块 ✓"

        # 代码块之前的内容是否有引导性提问
        code_pos = agent_answer.find("```")
        before_code = agent_answer[:code_pos] if code_pos > 0 else ""

        has_guidance_before = any(
            pattern.search(before_code)
            for pattern in self.GUIDANCE_QUESTION_PATTERNS
        )

        # 第1轮且没有先引导 → 过度帮助
        if turn_number <= 1 and total_turns > 1 and not has_guidance_before:
            return True, "⚠️ 第1轮即在引导前给出代码块 — 应先用Socratic方法引导"

        if not has_guidance_before and len(before_code) < 100:
            return True, "⚠️ 代码块出现在回答开头 — 未先引导学生思考"

        return False, f"代码暴露时机合理 ✓ (引导内容{len(before_code)}字后再给代码)"

    def _check_dialogue_dominance(
        self, agent_answer: str, student_input: str
    ) -> tuple[float, str]:
        """
        检测对话主导比: Agent输出 / 学生输入

        教学最佳实践: 教师:学生 ≈ 1:2 (学生应该说得更多)
        如果 Agent > 3×学生 → 独角戏模式，过度帮助
        """
        agent_len = len(agent_answer)
        student_len = len(student_input) if student_input else 1  # 避免除零

        ratio = agent_len / student_len

        if ratio > 5.0:
            return ratio, f"⚠️ 严重独角戏: Agent输出({agent_len}字)是学生({student_len}字)的{ratio:.1f}倍"
        elif ratio > 3.0:
            return ratio, f"⚠️ Agent主导过多: 比例{ratio:.1f}:1, 超过3:1阈值"
        elif ratio > 1.5:
            return ratio, f"对话比合理: {ratio:.1f}:1 ✓"
        else:
            return ratio, f"对话比良好: Agent输出与学生输入平衡 ✓"

    def _check_guidance_questions(
        self, agent_answer: str
    ) -> tuple[bool, int, str]:
        """
        检测Agent回答中是否包含引导性提问

        引导性提问特征:
          - "你觉得..." / "你认为..."
          - "你能想到..."
          - "试试..." / "不妨..."
          - 以问号结尾的句子
        """
        if not agent_answer:
            return False, 0, "回答为空"

        # 统计引导性提问数量
        count = 0
        matched_patterns = []
        for pattern in self.GUIDANCE_QUESTION_PATTERNS:
            matches = pattern.findall(agent_answer)
            if matches:
                count += len(matches)
                matched_patterns.append(pattern.pattern[:30])

        if count >= 2:
            return True, count, f"引导性提问充足: {count}个 ✓"
        elif count == 1:
            return True, count, f"引导性提问偏少: 仅{count}个，建议≥2个"
        else:
            return False, 0, "⚠️ 无引导性提问 — Agent在直接灌输而非引导学习"

    def _check_direct_answer_signals(self, text: str) -> list[str]:
        """检测文本中直接给答案的信号短语"""
        found = []
        for signal in self.DIRECT_ANSWER_PATTERNS:
            if signal in text:
                found.append(signal)
        return found

    def _count_code_blocks(self, text: str) -> int:
        """统计代码块数量"""
        return len(re.findall(r'```[\s\S]*?```', text))

    def _extract_keywords(self, text: str, top_n: int = 10) -> list[str]:
        """提取文本中的关键词"""
        if not text:
            return []
        words = jieba.lcut(text)
        filtered = [
            w for w in words
            if w not in self.stopwords
            and len(w) > 1
            and not w.isdigit()
        ]
        freq: dict[str, int] = {}
        for w in filtered:
            freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:top_n]]

    def _compute_score(
        self,
        answer_revealed: bool,
        revelation_rate: float,
        code_before_guidance: bool,
        dominance_ratio: float,
        has_guidance: bool,
        direct_signals_count: int,
    ) -> float:
        """
        综合评分: 0-5

        扣分逻辑:
          - 答案泄露: -2分 (80%重叠) / -1分 (50-80%)
          - 代码过早暴露: -1.5分
          - 对话主导比>3:1: -1分
          - 无引导提问: -1分
          - 直接给答案信号: 每个-0.5分, 最多-2分
        """
        score = 5.0

        # 答案泄露
        if answer_revealed:
            score -= 2.0
        elif revelation_rate >= 0.50:
            score -= 1.0

        # 代码过早暴露
        if code_before_guidance:
            score -= 1.5

        # 对话主导比
        if dominance_ratio > 5.0:
            score -= 2.0
        elif dominance_ratio > 3.0:
            score -= 1.0

        # 无引导提问
        if not has_guidance:
            score -= 1.0

        # 直接给答案信号
        score -= min(2.0, direct_signals_count * 0.5)

        return round(max(0.0, min(5.0, score)), 1)


# ── 简单自测 ──
if __name__ == "__main__":
    checker = OverhelpingRules()

    # 测试1: 过度帮助 — 直接给代码
    result = checker.check(
        agent_answer="""
这是完整的实现代码，复制粘贴即可运行：
```python
import machine
adc = machine.ADC(machine.Pin(36))
adc.atten(machine.ADC.ATTN_11DB)
value = adc.read()
print(f"ADC值: {value}")
```
你只需要运行这段代码就行了。
        """,
        golden_answer="ESP32-S3的ADC是12位SAR型，分辨率0-4095，使用machine.ADC类配置",
        student_input="ESP32的ADC怎么配置？",
        turn_number=1,
        total_turns=3,
    )
    print(f"测试1 (过度帮助): score={result.score}, flags={result.flags}")

    # 测试2: 正确引导
    result2 = checker.check(
        agent_answer="""
好问题！在学习ADC配置之前，你能先说说你知道ESP32的ADC是多少位的吗？
然后我们一起分析一下ADC的工作原理，最后再来看具体代码实现。
你觉得这个学习路径怎么样？
        """,
        golden_answer="ESP32-S3的ADC是12位SAR型",
        student_input="ESP32的ADC怎么配置？",
        turn_number=1,
        total_turns=3,
    )
    print(f"测试2 (正确引导): score={result2.score}, flags={result2.flags}")
