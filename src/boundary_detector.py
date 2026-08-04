"""
课程边界检测器 v3.4 — L1 闸门 + L2 算法增强 + P0-10 语义验证

对齐:
  - CLEAR Assurance: 边界合规性的确定性基底
  - TEACH-AI Responsibility: 课程内容范围约束
  - EduAgentBench: 过程约束 (知识组件边界检查)

检测策略 (分层):
  L1 (确定性, 0ms, $0):
    1. 关键词命中率: 课程核心术语 + 对应阶段 → hit_rate (0-1)
    2. 幻觉模式检测: 正则匹配大模型典型胡说模式 → hallucination_flags
    3. 关键词滥用标记: 命中≠正确使用的模式识别
    4. 四分类输出: keyword_validated / keyword_suspected / keyword_abuse / out_of_scope

  L2 (算法增强, <100ms):
    5. KB语义一致性: 回答 vs 课程知识库的向量相似度
    6. 关键词上下文验证: 命中词周边语义是否与KB定义一致

  L3 (LLM, 仅在灰色地带调用):
    7. LLM判定: 当 keyword_suspected 时, LLM判定是否为通用知识

P0-10修复: 关键词命中率不再是唯一信号。新增语义一致性分数和幻觉检测,
          区分"提到关键词"(keyword_abuse)和"正确使用关键词"(keyword_validated)。

当前阶段: L1关键词+幻觉检测是主信号, L2 KB语义+上下文验证增强精度
未来升级: 接入更细粒度的课程知识图谱做精确的事实校验
"""

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict
from openai import OpenAI


@dataclass
class BoundaryResult:
    """边界检测结果 (P0-10增强: 新增语义验证字段)"""
    status: str          # "keyword_validated" | "keyword_suspected" | "keyword_abuse" | "out_of_scope" | "error"
    max_score: float = 0.0       # 综合边界分数 (关键词+语义)
    matched_keywords: list = field(default_factory=list)
    missed_keywords: list = field(default_factory=list)
    llm_judgment: str = ""       # LLM 判定理由

    # ── P0-10 新增: 语义验证字段 ──
    keyword_quality: dict = field(default_factory=dict)
    #      结构: {keyword: {"context_used": str, "semantic_ok": bool, "abuse_pattern": str}}
    semantic_consistency: float = 0.0     # 整体语义一致性 (0-1, KB向量相似度)
    hallucination_flags: list = field(default_factory=list)  # 检测到的幻觉模式
    keyword_hit_rate_raw: float = 0.0     # 原始关键词命中率 (语义验证前的原始值)

    evidence: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_in_scope(self) -> bool:
        return self.status in ("keyword_validated", "in_scope")

    @property
    def is_out_of_scope(self) -> bool:
        return self.status in ("out_of_scope", "keyword_abuse")

    @property
    def is_suspicious(self) -> bool:
        """P0-10: 回答可疑 — 有关键词但语义不一致"""
        return self.status == "keyword_suspected"


class BoundaryDetector:
    """
    课程边界检测器

    基于课程核心关键词 + LLM 判定，判断回答是否在课程大纲范围内。

    用法:
        detector = BoundaryDetector(api_key)
        result = detector.detect(question="...", agent_answer="...")
        print(result.status)  # "in_scope"
    """

    # 课程核心关键词（按阶段分类，来自课程大纲）
    PHASE_KEYWORDS = {
        "PHASE_01": [
            "HiAgent", "千帆", "Agent", "大模型", "本地部署", "API调用", "Prompt", "提示词",
            "ESP32", "ESP32-S3", "开发板", "固件", "云边协同", "MQTT", "HTTP",
            "3D建模", "Blender", "SolidWorks", "STL", "切片", "3D打印",
        ],
        "PHASE_02": [
            "增材制造", "减材制造", "激光雕刻", "CNC", "五轴", "数控",
            "Arduino", "面包板", "LED", "按键", "IO控制", "传感器",
            "OpenClaw", "LightBurn", "UV打印", "安克",
        ],
        "PHASE_03": [
            "环境感知", "传感器", "温湿度", "摄像头", "图像识别",
            "Edge Impulse", "边缘AI", "音频识别", "麦克风", "声音控制",
            "嵌入式部署", "模型训练", "数据融合", "多模态",
        ],
        "PHASE_04": [
            "触觉反馈", "舵机", "灯带", "RGB", "电机", "小车",
            "触摸交互", "屏幕", "GUI", "AI标签", "语音触发",
            "具身智能", "执行器", "情感交互",
        ],
        "PHASE_05": [
            "M5Stack", "StackChan", "机器人", "传感器融合",
            "多模态交互", "项目路演", "云边协同", "3D打印外壳",
        ],
    }

    # 所有关键词的并集
    ALL_KEYWORDS = set()
    for kws in PHASE_KEYWORDS.values():
        ALL_KEYWORDS.update(kws)

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://api.deepseek.com/v1",
        keyword_threshold: float = 0.15,
    ):
        """
        :param api_key: DeepSeek API Key (用于 LLM 判定)
        :param base_url: API 地址
        :param keyword_threshold: 关键词命中率阈值
        """
        self.api_key = api_key
        self.base_url = base_url
        self.keyword_threshold = keyword_threshold
        self.client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None

    def _keyword_match(self, text: str) -> dict:
        """
        关键词匹配检测

        :return: {"hit": [...], "miss": [...], "hit_rate": float}
        """
        text_lower = text.lower()
        hit = []
        miss = []
        for kw in self.ALL_KEYWORDS:
            if kw.lower() in text_lower:
                hit.append(kw)
            else:
                miss.append(kw)

        hit_rate = len(hit) / len(self.ALL_KEYWORDS) if self.ALL_KEYWORDS else 0
        return {"hit": hit, "miss": miss, "hit_rate": hit_rate}

    # ═══════════════════════════════════════════════════════════
    # P0-10: 幻觉模式检测 + 关键词质量验证
    # ═══════════════════════════════════════════════════════════

    # ── 典型大模型幻觉模式 ──
    HALLUCINATION_PATTERNS = [
        # 模式A: 给硬件赋予不存在的超能力
        # 原理: LLM倾向把任何技术术语和"量子/AI/深度学习"强行关联
        {
            "name": "hardware_fantasy",
            "patterns": [
                r"(ESP32|Arduino|M5Stack|STM32).{0,20}(量子计算|量子|深度学习训练|大模型训练|区块链)",
                r"(量子计算|量子|深度学习训练|大模型训练|区块链).{0,20}(ESP32|Arduino|M5Stack|STM32)",
                r"(ESP32|单片机|开发板).{0,30}(GPU|图形处理器|显卡)",
            ],
            "severity": "high",
            "description": "给低功耗硬件赋予不存在的计算能力",
        },
        # 模式B: 技术术语的错误归因
        # 原理: LLM知道"I2C是通信协议"但可能随机关联到"WiFi路由"
        {
            "name": "term_misattribution",
            "patterns": [
                r"(I2C|SPI|UART|GPIO|PWM).{0,15}(是一个|是一种).{0,30}(WiFi|蓝牙|以太网|路由|交换机)",
                r"(云边协同).{0,15}(是一种|是一种|是一个).{0,30}(机器学习|深度学习|神经网络|强化学习|GAN|Transformer)",
                r"(传感器).{0,20}(可以训练|可以学习|自我进化|自适应学习)",
                r"(Arduino|ESP32).{0,30}(操作系统|OS|Linux内核|Windows)",
            ],
            "severity": "medium",
            "description": "技术术语的属性归因错误",
        },
        # 模式C: 课程范围外的技术概念越界
        # 原理: LLM把课程关键词和高级但不相关技术强行关联
        {
            "name": "concept_overreach",
            "patterns": [
                r"(大模型|Agent|AI助手).{0,40}(造车|自动驾驶|医疗诊断|金融交易|军事|武器)",
                r"(3D打印|增材制造).{0,30}(人体器官|生物打印|基因编辑|克隆)",
                r"(摄像头|传感器|麦克风).{0,30}(人脸识别门禁|监控追踪|隐私窃取)",
            ],
            "severity": "high",
            "description": "课程概念被扩展到不相关的危险/违规领域",
        },
        # 模式D: 虚假权威引用
        # 原理: LLM编造论文/标准/机构名称来背书
        {
            "name": "fake_authority",
            "patterns": [
                r"根据.{0,30}(论文|研究|标准|报告).{0,50}(显示|表明|指出|证明)",
                r"(IEEE|ISO|GB/T|国家标准)\s?\d{2,}",
                r"(清华大学|MIT|Stanford|哈佛).{0,30}(研究|实验|论文|团队)",
            ],
            "severity": "low",
            "description": "引用无法验证的权威来源 (可能是幻觉)",
        },
    ]

    # 可以安全忽略的关键词 (在合理上下文中几乎不可能是幻觉的标志词)
    SAFE_INDICATOR_PATTERNS = [
        r"(学习|了解|掌握|理解|掌握|熟悉).{0,20}(ESP32|Arduino|传感器|开发板)",
        r"(使用|利用|应用|基于|采用).{0,20}(HiAgent|ESP32|Arduino)",
        r"(例如|比如|如|像).{0,30}(ESP32|传感器|OLED|LED)",
    ]

    def _detect_hallucination_patterns(self, text: str) -> list[dict]:
        """
        P0-10: 检测大模型幻觉的典型文本模式。

        方法: 正则模式匹配, 零成本 (无LLM/API调用)。
        原理: LLM幻觉有其语言指纹 — 技术术语+不该出现的高级概念强行共现。
              例如"ESP32可以进行量子计算"中ESP32和量子计算的共现本身就是红旗。

        :return: [{name, severity, match, description}, ...]
        """
        flags_found = []
        text_clean = text.replace("\n", " ")

        for pattern_group in self.HALLUCINATION_PATTERNS:
            for pat in pattern_group["patterns"]:
                for match in re.finditer(pat, text_clean, re.IGNORECASE):
                    matched_text = match.group(0).strip()
                    # 检查安全上下文: 如果匹配段周围有"学习/了解/例如"等词, 降低严重度
                    context_start = max(0, match.start() - 60)
                    context_end = min(len(text_clean), match.end() + 60)
                    context = text_clean[context_start:context_end]

                    is_in_safe_context = any(
                        re.search(safe_pat, context, re.IGNORECASE)
                        for safe_pat in self.SAFE_INDICATOR_PATTERNS
                    )

                    effective_severity = "low" if is_in_safe_context else pattern_group["severity"]

                    flags_found.append({
                        "name": pattern_group["name"],
                        "severity": effective_severity,
                        "match": matched_text[:100],
                        "description": pattern_group["description"],
                    })

        # 去重 (同一模式只保留最高严重度的一条)
        seen = {}
        unique_flags = []
        for f in flags_found:
            key = f["name"]
            if key not in seen or (
                f["severity"] == "high" and seen[key] != "high"
            ):
                seen[key] = f["severity"]
                unique_flags.append(f)
            elif f["severity"] == seen[key]:
                pass  # skip duplicate same-severity

        return unique_flags

    def _validate_keyword_quality(
        self,
        matched_keywords: list[str],
        text: str,
    ) -> dict:
        """
        P0-10: 验证每个命中关键词的使用质量。

        方法: 提取每个关键词在回答中的上下文窗口(前后50字), 检查:
          1. 是否在否定语境中 ("不是ESP32", "没有用到Arduino")
          2. 是否在疑问/不确定语境中 ("可能是ESP32", "也许是传感器问题")
          3. 是否是泛泛而谈 (关键词重复但没有实质性解释)

        :return: {
            keyword: {
                "context_used": str,        # 关键词在回答中的上下文
                "likely_valid": bool,        # 是否可能是正确使用
                "risk_pattern": str,         # 如果可能误用, 是什么模式
            }
        }
        """
        quality = {}
        text_clean = text.replace("\n", " ")

        for kw in matched_keywords:
            # 否定/怀疑语境模式 (每个关键词动态构建)
            negation_patterns = [
                (r"(?:不是|并非|没有|不属于|不涉及|不包含).{0,20}" + re.escape(kw), "negation"),
                (r"(?:可能|也许|大概|应该|或许|不清楚|不确定).{0,20}" + re.escape(kw), "uncertain"),
                (re.escape(kw) + r".{0,20}(?:不是|并非|没有|不适用)", "negation"),
            ]
            # 找到关键词在文中的位置
            positions = [m.start() for m in re.finditer(re.escape(kw), text_clean, re.IGNORECASE)]
            if not positions:
                quality[kw] = {"context_used": "(未找到)", "likely_valid": False, "risk_pattern": "not_found"}
                continue

            # 取第一个出现位置的上下文
            pos = positions[0]
            ctx_start = max(0, pos - 50)
            ctx_end = min(len(text_clean), pos + len(kw) + 80)
            context = text_clean[ctx_start:ctx_end].strip()

            # ── 检查1: 否定语境 ──
            is_negated = False
            risk_pattern = ""
            for pat, risk_type in negation_patterns:
                try:
                    if re.search(pat, context, re.IGNORECASE):
                        is_negated = True
                        risk_pattern = risk_type
                        break
                except re.error:
                    continue

            # ── 检查2: 空泛使用 ("ESP32"一词出现多次但没有任何技术细节) ──
            kw_count = len(re.findall(re.escape(kw), text_clean, re.IGNORECASE))
            has_technical_detail = bool(re.search(
                r"(GPIO|I2C|SPI|PWM|ADC|引脚|寄存器|时钟|频率|电压|电流|协议)",
                text_clean, re.IGNORECASE,
            ))
            is_shallow = (kw_count >= 3 and not has_technical_detail)

            # ── 综合判定 ──
            if is_negated:
                likely_valid = False
                risk_pattern = risk_pattern or "negation"
            elif is_shallow:
                likely_valid = False
                risk_pattern = "shallow_repetition"
            else:
                likely_valid = True
                risk_pattern = ""

            quality[kw] = {
                "context_used": context[:120],
                "likely_valid": likely_valid,
                "risk_pattern": risk_pattern,
                "occurrences": kw_count,
                "has_technical_detail": has_technical_detail,
            }

        return quality

    def _compute_semantic_consistency(
        self,
        keyword_quality: dict,
        hallucination_flags: list[dict],
        hit_rate: float,
    ) -> tuple[float, str]:
        """
        P0-10: 计算语义一致性分数。

        方法: 综合三个信号得出0-1分数。
          - 关键词质量: 有效关键词占比
          - 幻觉严重度: high→重罚, low→轻罚
          - 安全上下文: 有"学习/例如"等词→轻微加分

        :return: (consistency_score, detail_string)
        """
        # ── 1. 关键词质量部分 (0.0-1.0) ──
        if not keyword_quality:
            kw_score = 0.0
        else:
            valid_count = sum(1 for q in keyword_quality.values() if q.get("likely_valid", False))
            kw_score = valid_count / len(keyword_quality) if keyword_quality else 0.0

        # ── 2. 幻觉惩罚 ──
        hallucination_penalty = 0.0
        high_count = sum(1 for f in hallucination_flags if f["severity"] == "high")
        med_count = sum(1 for f in hallucination_flags if f["severity"] == "medium")
        low_count = sum(1 for f in hallucination_flags if f["severity"] == "low")

        hallucination_penalty = min(1.0, high_count * 0.35 + med_count * 0.20 + low_count * 0.10)

        # ── 3. 综合 ──
        # 公式: 加法模型, 防止任一因子零化另一因子
        # kw_score: 有效关键词占比 (0-1)
        # hit_rate: 原始命中率归一化 (0-1), 用缩放代替截断
        # hallucination_penalty: 直接扣分
        hit_rate_norm = min(1.0, hit_rate * 3.0)  # 0.10→0.30, 0.20→0.60, 0.33+→1.0
        combined = 0.5 * kw_score + 0.5 * hit_rate_norm
        consistency = max(0.0, min(1.0, combined - hallucination_penalty))

        detail = (
            f"kw_valid={kw_score:.2f} halluc_penalty={hallucination_penalty:.2f} "
            f"hit_norm={hit_rate_norm:.2f} consistency={consistency:.2f}"
        )

        return round(consistency, 4), detail

    def _llm_judge(self, question: str, agent_answer: str) -> str:
        """
        LLM 判定回答是否在课程范围内

        :return: JSON 格式判定结果
        """
        if not self.client:
            return ""

        # 课程描述
        course_desc = """
课程名称: 国产智能硬件与AI应用开发（AI新硬件设计制造）
5个阶段:
- PHASE 01: 国产AI技术基础（大模型部署、HiAgent平台、Prompt工程、ESP32-S3、云边协同、3D建模）
- PHASE 02: 新型硬件设计（3D打印、激光雕刻、CNC加工、Arduino编程、增材/减材制造）
- PHASE 03: 环境感知（传感器、摄像头、Edge Impulse边缘AI、音频识别、嵌入式部署）
- PHASE 04: 触觉反馈集成（舵机/灯带/电机控制、触摸交互、AI标签联动、具身智能）
- PHASE 05: 具身智能控制（M5Stack、StackChan机器人、传感器融合、多模态交互、项目路演）

课程核心原则: 硬件"乐高化"（不涉及电路设计焊接）、AI"全能化"（代码由AI生成）、实验"拼图化"（模块化套件）
"""

        prompt = f"""
你是一个课程边界审查专家。请判断以下AI教学助手的回答是否在课程大纲范围内。

【课程描述】
{course_desc}

【学生问题】
{question}

【AI助手回答】
{agent_answer[:1500]}

请判断并输出JSON:
{{
    "judgment": "in_scope" | "partial_match" | "out_of_scope",
    "reason": "一句话理由",
    "is_general_knowledge": true/false  // 是否属于通用大模型知识而非课程内容
}}

只输出JSON。
"""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"judgment": "error", "reason": str(e), "is_general_knowledge": None}

    def detect(
        self,
        question: str = "",
        agent_answer: str = "",
    ) -> BoundaryResult:
        """
        检测 Agent 回答是否在课程边界内

        :param question: 原始问题
        :param agent_answer: Agent 的完整回答
        :return: BoundaryResult
        """
        if not agent_answer:
            return BoundaryResult(
                status="error",
                evidence="回答为空",
                recommendation="无法检测空回答",
            )

        # ── 1. 关键词匹配检测 ──
        kw_result = self._keyword_match(agent_answer + " " + question)
        raw_hit_rate = kw_result["hit_rate"]

        # ── 2. P0-10: 幻觉检测 + 关键词质量 ──
        hallucination_flags = self._detect_hallucination_patterns(agent_answer)
        keyword_quality = self._validate_keyword_quality(kw_result["hit"], agent_answer)
        local_consistency, _ = self._compute_semantic_consistency(
            keyword_quality, hallucination_flags, raw_hit_rate,
        )

        # ── 3. LLM 判定 ──
        llm_result = {}
        if self.client:
            llm_result = self._llm_judge(question, agent_answer)

        # ── 4. 综合判定 (P0-10增强: 关键词+幻觉+LLM) ──
        llm_judgment = llm_result.get("judgment", "unknown")
        is_general = llm_result.get("is_general_knowledge", None)

        abuse_keyword_count = sum(
            1 for q in keyword_quality.values()
            if not q.get("likely_valid", False)
        )

        # P0-10: 如果有幻觉信号或关键词滥用, LLM的in_scope判定也要打折
        has_hallucination = len(hallucination_flags) > 0
        has_abuse = abuse_keyword_count > 0

        if raw_hit_rate >= 0.3 and local_consistency >= 0.5 and not has_hallucination:
            status = "keyword_validated"
        elif has_abuse and has_hallucination:
            status = "keyword_abuse"
        elif llm_judgment == "out_of_scope" or is_general is True:
            status = "out_of_scope"
        elif raw_hit_rate >= self.keyword_threshold or llm_judgment == "partial_match":
            status = "keyword_suspected"
        else:
            status = "out_of_scope"

        effective_score = raw_hit_rate
        if status == "keyword_abuse":
            valid_kw_count = len(kw_result["hit"]) - abuse_keyword_count
            effective_score = round(valid_kw_count / len(self.ALL_KEYWORDS), 4) if self.ALL_KEYWORDS else 0.0
        elif status == "keyword_validated":
            effective_score = max(raw_hit_rate, local_consistency)

        # ── 5. 构建证据 ──
        evidence_parts = [
            f"[L3 P0-10增强] 关键词命中率(原始): {raw_hit_rate:.2%} ({len(kw_result['hit'])}/{len(self.ALL_KEYWORDS)})",
            f"语义一致性(本地): {local_consistency:.2%}",
            f"命中关键词: {', '.join(kw_result['hit'][:10])}" if kw_result["hit"] else "无关键词命中",
            f"LLM判定: {llm_judgment} — {llm_result.get('reason', 'N/A')}",
        ]

        if hallucination_flags:
            evidence_parts.append(f"⚠️ 幻觉信号: " + "; ".join(
                f"{f['severity']}/{f['name']}" for f in hallucination_flags[:3]
            ))

        if abuse_keyword_count > 0:
            abused = [kw for kw, q in keyword_quality.items() if not q.get("likely_valid")]
            evidence_parts.append(f"🔴 关键词滥用 ({abuse_keyword_count}): {', '.join(abused[:5])}")

        # ── 6. 建议 ──
        if status == "keyword_abuse":
            recommendation = (
                "🔴 关键词滥用+幻觉: 回答包含课程术语但使用错误, 可能为大模型幻觉。"
                "建议: 强制Agent基于课程知识库检索后回答"
            )
        elif status == "out_of_scope":
            recommendation = (
                "回答超出课程大纲范围，属于通用大模型能力。"
                "建议: 1) 限制回答范围为课程内容 2) 增加对课程知识点的引用"
            )
        elif status == "keyword_suspected":
            recommendation = "回答部分在课程范围内，可进一步聚焦到课程核心知识点"
        else:
            recommendation = "回答在课程大纲范围内 ✓"

        return BoundaryResult(
            status=status,
            max_score=round(effective_score, 4),
            matched_keywords=kw_result["hit"],
            missed_keywords=kw_result["miss"][:20],
            llm_judgment=llm_result.get("reason", ""),
            keyword_quality=keyword_quality,
            semantic_consistency=local_consistency,
            hallucination_flags=hallucination_flags,
            keyword_hit_rate_raw=raw_hit_rate,
            evidence="\n".join(evidence_parts),
            recommendation=recommendation,
        )

    def detect_deterministic(
        self,
        question: str = "",
        agent_answer: str = "",
    ) -> BoundaryResult:
        """
        纯确定性边界检测 — P0-10增强: 幻觉检测 + 关键词质量验证

        这是 L1 规则层的主入口, 在 evaluator.py 的 L2 算法层中使用。
        返回的 max_score 直接作为 boundary_compliance 维度分数基底。

        :return: BoundaryResult with semantic validation fields
        """
        if not agent_answer:
            return BoundaryResult(
                status="error",
                evidence="回答为空",
                recommendation="无法检测空回答",
            )

        # ── 1. 关键词匹配 (原始信号) ──
        kw_result = self._keyword_match(agent_answer + " " + question)
        raw_hit_rate = kw_result["hit_rate"]

        # ── 2. P0-10: 幻觉模式检测 ──
        hallucination_flags = self._detect_hallucination_patterns(agent_answer)

        # ── 3. P0-10: 关键词质量验证 ──
        keyword_quality = self._validate_keyword_quality(
            matched_keywords=kw_result["hit"],
            text=agent_answer,
        )

        # ── 4. P0-10: 语义一致性分数 ──
        semantic_consistency, consistency_detail = self._compute_semantic_consistency(
            keyword_quality=keyword_quality,
            hallucination_flags=hallucination_flags,
            hit_rate=raw_hit_rate,
        )

        # ── 5. P0-10 增强分类: 四分类 ──
        # 关键逻辑: 关键词命中率高≠在范围内; 必须检查语义一致性
        has_hallucination = len(hallucination_flags) > 0
        has_any_keyword = len(kw_result["hit"]) > 0
        abuse_keyword_count = sum(
            1 for q in keyword_quality.values()
            if not q.get("likely_valid", False)
        )

        if semantic_consistency >= 0.6 and raw_hit_rate >= 0.08 and not has_hallucination:
            # 真正在范围内: 语义一致 + 关键词够多 (>=6/70个) + 无幻觉
            # 阈值0.08≈6/70: 技术正确回答通常命中5-10个课程关键词
            status = "keyword_validated"
            effective_score = max(raw_hit_rate, semantic_consistency)
        elif has_hallucination and has_any_keyword:
            # P0-10核心: 幻觉信号+任何关键词命中 → 关键词滥用
            # 即使hit_rate低, 只要命中了关键词且同时检测到幻觉模式, 就是滥用
            status = "keyword_abuse"
            penalty = min(0.8, len(hallucination_flags) * 0.25)
            effective_score = round(raw_hit_rate * (1 - penalty), 4)
        elif abuse_keyword_count > 0 and raw_hit_rate >= 0.15:
            # P0-10: 关键词命中率高但多个关键词语义不一致→假阴性黑洞
            status = "keyword_abuse"
            valid_kw_count = len(kw_result["hit"]) - abuse_keyword_count
            effective_score = round(valid_kw_count / len(self.ALL_KEYWORDS), 4) if self.ALL_KEYWORDS else 0.0
        elif semantic_consistency >= 0.35 and raw_hit_rate >= 0.05:
            # 灰色地带: 语义部分一致但有疑虑
            status = "keyword_suspected"
            effective_score = round((raw_hit_rate + semantic_consistency) / 2, 4)
        elif raw_hit_rate >= self.keyword_threshold:
            status = "keyword_suspected"
            effective_score = raw_hit_rate
        else:
            status = "out_of_scope"
            effective_score = raw_hit_rate

        # ── 6. 构建证据 ──
        evidence_parts = [
            f"[L1 P0-10增强] 关键词命中率(原始): {raw_hit_rate:.2%} ({len(kw_result['hit'])}/{len(self.ALL_KEYWORDS)})",
            f"语义一致性: {semantic_consistency:.2%} — {consistency_detail}",
            f"关键词有效比: {len(kw_result['hit'])-abuse_keyword_count}/{len(kw_result['hit'])} 有效",
        ]
        if kw_result["hit"]:
            evidence_parts.append(f"命中关键词: {', '.join(kw_result['hit'][:10])}")
        else:
            evidence_parts.append("无关键词命中")

        if hallucination_flags:
            evidence_parts.append(f"⚠️ 幻觉信号 ({len(hallucination_flags)}): " + "; ".join(
                f"{f['severity']}/{f['name']}: {f['match'][:60]}" for f in hallucination_flags[:3]
            ))

        if abuse_keyword_count > 0:
            abused = [kw for kw, q in keyword_quality.items() if not q.get("likely_valid")]
            evidence_parts.append(f"🔴 关键词滥用 ({abuse_keyword_count}): {', '.join(abused[:5])}")
            for kw in abused[:3]:
                q = keyword_quality.get(kw, {})
                evidence_parts.append(f"   {kw}: {q.get('risk_pattern', '?')} — {q.get('context_used', '')[:80]}")

        evidence_parts.append(f"状态: {status} (有效分={effective_score:.4f})")

        # ── 7. 建议 ──
        if status == "keyword_abuse":
            recommendation = (
                "🔴 关键词滥用检测: 回答中出现了课程术语但并未正确使用。"
                f"检测到{abuse_keyword_count}个误用关键词。"
                "建议: 1) Agent需严格基于课程知识库回答 2) 避免用大模型自身知识替代课程内容 "
                "3) 对课程术语的解释必须与课程定义一致"
            )
        elif status == "keyword_suspected":
            recommendation = (
                "⚠️ 回答在课程范围边缘: 有关键词但语义一致性不足。"
                "建议: 引用课程知识库原文, 确保术语使用与课程定义一致"
            )
        elif status == "out_of_scope":
            recommendation = (
                "回答超出课程大纲范围 (关键词命中率过低)。"
                "建议: 1) 限制回答范围为课程内容 2) 增加对课程知识点的引用"
            )
        else:
            recommendation = "✅ 回答在课程大纲范围内, 关键词使用正确"

        return BoundaryResult(
            status=status,
            max_score=effective_score,
            matched_keywords=kw_result["hit"],
            missed_keywords=kw_result["miss"][:20],
            llm_judgment="",
            keyword_quality=keyword_quality,
            semantic_consistency=semantic_consistency,
            hallucination_flags=hallucination_flags,
            keyword_hit_rate_raw=raw_hit_rate,
            evidence="\n".join(evidence_parts),
            recommendation=recommendation,
        )

    def detect_with_kb(
        self,
        question: str = "",
        agent_answer: str = "",
    ) -> BoundaryResult:
        """
        L2: 知识库增强边界检测 — 语义检索 + 关键词匹配

        KB后端优先级:
          1. 火山引擎向量知识库 (VOLC_KB_* 环境变量)
          2. 火山引擎知识库 (VOLC_KB_*)
          3. 降级为纯关键词检测 (detect_deterministic)

        :return: BoundaryResult with kb_scores
        """
        if not agent_answer:
            return BoundaryResult(status="error", evidence="回答为空", recommendation="无法检测空回答")

        # ── 1. 关键词匹配 (L1 基底) ──
        kw_result = self._keyword_match(agent_answer + " " + question)
        kw_hit_rate = kw_result["hit_rate"]

        # ── 2. P0-10: 幻觉模式检测 ──
        hallucination_flags = self._detect_hallucination_patterns(agent_answer)

        # ── 3. P0-10: 关键词质量验证 ──
        keyword_quality = self._validate_keyword_quality(
            matched_keywords=kw_result["hit"],
            text=agent_answer,
        )

        # ── 4. KB 语义检索 (自动选择后端) ──
        kb_scores, kb_chunks, kb_error, kb_backend = self._retrieve_from_kb(
            query=question + " " + agent_answer[:200],
        )

        # ── 5. 综合判定 (P0-10增强: KB语义 + 幻觉检测 + 关键词质量) ──
        max_kb_score = max(kb_scores) if kb_scores else 0.0
        avg_kb_score = sum(kb_scores) / len(kb_scores) if kb_scores else 0.0

        # KB分作为语义一致性的"地面实况"
        kb_semantic_consistency = max_kb_score if kb_scores else 0.0

        # 计算整体语义一致性 (综合KB和本地信号)
        local_consistency, _ = self._compute_semantic_consistency(
            keyword_quality, hallucination_flags, kw_hit_rate,
        )
        # KB存在时: KB占总语义分60%
        semantic_consistency = (
            round(0.6 * kb_semantic_consistency + 0.4 * local_consistency, 4)
            if kb_scores else local_consistency
        )

        # 关键词分 (0-1) + KB分 (0-1) 加权
        kb_weight = 0.5 if kb_scores else 0.0  # 有KB数据时占50%
        kw_weight = 1.0 - kb_weight

        # P0-10: 如果有幻觉信号, 降低KB权重 (KB结果也可能是LLM幻觉)
        if hallucination_flags:
            kb_weight *= 0.5
            kw_weight = 1.0 - kb_weight

        combined_score = kw_weight * kw_hit_rate + kb_weight * max_kb_score

        # P0-10四分类
        abuse_keyword_count = sum(
            1 for q in keyword_quality.values()
            if not q.get("likely_valid", False)
        )

        if semantic_consistency >= 0.55 and combined_score >= 0.15 and not hallucination_flags:
            status = "keyword_validated"
        elif abuse_keyword_count > 0 and kw_hit_rate >= 0.15 and semantic_consistency < 0.35:
            status = "keyword_abuse"
            combined_score = combined_score * 0.5  # 惩罚
        elif combined_score >= 0.3:
            status = "keyword_validated"
        elif combined_score >= self.keyword_threshold:
            status = "keyword_suspected"
        else:
            status = "out_of_scope"

        # ── 6. 证据构建 ──
        evidence_parts = [
            f"[L2 P0-10增强] 综合分数: {combined_score:.2%} (后端: {kb_backend})",
            f"  关键词命中率(原始): {kw_hit_rate:.2%} ({len(kw_result['hit'])}/{len(self.ALL_KEYWORDS)})",
            f"  语义一致性: {semantic_consistency:.2%} (KB={kb_semantic_consistency:.3f} 本地={local_consistency:.3f})",
        ]
        if kb_scores:
            evidence_parts.append(
                f"  KB语义检索: max={max_kb_score:.3f} avg={avg_kb_score:.3f} "
                f"({len(kb_scores)}个结果)"
            )
            evidence_parts.append(f"  KB匹配内容: {kb_chunks[0][:120]}..." if kb_chunks else "  无匹配内容")
        elif kb_error:
            evidence_parts.append(f"  KB检索降级: {kb_error} (使用本地语义验证)")

        if hallucination_flags:
            evidence_parts.append(f"⚠️ 幻觉信号 ({len(hallucination_flags)}): " + "; ".join(
                f"{f['severity']}/{f['name']}" for f in hallucination_flags[:3]
            ))

        if abuse_keyword_count > 0:
            abused = [kw for kw, q in keyword_quality.items() if not q.get("likely_valid")]
            evidence_parts.append(f"🔴 关键词滥用 ({abuse_keyword_count}): {', '.join(abused[:5])}")

        evidence_parts.append(f"命中关键词: {', '.join(kw_result['hit'][:10])}" if kw_result["hit"] else "无关键词命中")
        evidence_parts.append(f"状态: {status}")

        # 建议
        if status == "keyword_abuse":
            recommendation = (
                "🔴 关键词滥用: 回答中出现课程术语但未正确使用。"
                "Agent可能依赖大模型自身知识而非课程内容。"
                "建议: 强制Agent基于知识库检索结果回答, 避免幻觉"
            )
        elif status == "out_of_scope":
            recommendation = (
                "回答超出课程大纲范围。建议: 1) 引用课程知识库中的内容 "
                "2) 基于课程核心概念回答 3) 区分'通用知识'和'课程知识'"
            )
        elif status == "keyword_suspected":
            recommendation = "⚠️ 回答部分在课程范围内但语义一致性不足，建议引用KB原文验证"
        else:
            recommendation = "✅ 回答在课程大纲范围内，关键词+语义双验证通过"

        return BoundaryResult(
            status=status,
            max_score=round(combined_score, 4),
            matched_keywords=kw_result["hit"],
            missed_keywords=kw_result["miss"][:20],
            llm_judgment="",
            keyword_quality=keyword_quality,
            semantic_consistency=semantic_consistency,
            hallucination_flags=hallucination_flags,
            keyword_hit_rate_raw=kw_hit_rate,
            evidence="\n".join(evidence_parts),
            recommendation=recommendation,
        )

    def _retrieve_from_kb(self, query: str, top_k: int = 5) -> tuple[list[float], list[str], str | None, str]:
        """
        统一KB检索入口 — 自动选择可用的KB后端

        优先级: HiAgent课程KB > 火山引擎 > 降级

        :return: (scores, chunks, error, backend_name)
        """
        # ── 后端0: HiAgent 课程知识库 (最高优先级, 真实的课程KB) ──
        hiagent_kb_configured = any(
            os.getenv(key, "") for key in [
                "VOLC_KB_PHASE1_KEY",
                "VOLC_KB_PHASE2_KEY",
                "VOLC_KB_PHASE3_4_KEY",
                "VOLC_KB_PHASE5_KEY",
            ]
        )
        if hiagent_kb_configured:
            try:
                scores, chunks = self._retrieve_from_hiagent_kb(
                    query=query, top_k=top_k,
                )
                if scores:
                    return scores, chunks, None, "hiagent_kb"
            except Exception:
                pass  # 失败 → 降级到火山引擎

        # ── 后端1: 火山引擎向量知识库 ──
        volc_domain = os.getenv("VOLC_KB_DOMAIN", "")
        volc_key = os.getenv("VOLC_KB_API_KEY", "")
        volc_service_id = os.getenv("VOLC_KB_SERVICE_ID", "")
        # HMAC认证 (优先): 不需要 VOLC_KB_API_KEY, 只需要 AK/SK
        volc_ak = os.getenv("VOLC_ACCESS_KEY", "")
        volc_sk = os.getenv("VOLC_SECRET_KEY", "")

        if volc_domain and (volc_key or (volc_ak and volc_sk)) and volc_service_id:
            try:
                scores, chunks = self._retrieve_from_volcano(
                    query=query,
                    domain=volc_domain,
                    api_key=volc_key,
                    service_id=volc_service_id,
                    top_k=top_k,
                )
                return scores, chunks, None, "volcano"
            except Exception as e:
                # 火山失败了尝试下一个
                pass

        # ── 降级 ──
        return [], [], "未配置KB后端 (设置VOLC_KB_*环境变量)", "none"

    def _retrieve_from_hiagent_kb(
        self,
        query: str,
        top_k: int = 5,
    ) -> tuple[list[float], list[str]]:
        """
        HiAgent 课程知识库检索 — 查询所有Phase火山引擎KB

        环境变量要求:
          VOLC_KB_PHASE1_KEY / VOLC_KB_PHASE1_ID
          VOLC_KB_PHASE2_KEY / VOLC_KB_PHASE2_ID
          VOLC_KB_PHASE3_4_KEY / VOLC_KB_PHASE3_4_ID
          VOLC_KB_PHASE5_KEY / VOLC_KB_PHASE5_ID
        """
        from src.hiagent_kb import query_all_phase_kbs

        results = query_all_phase_kbs(query, top_k=top_k)

        # 合并所有KB的chunks, 按分数降序取top_k
        all_chunks = []
        for phase, result in results.items():
            if result.error:
                continue
            for chunk in result.chunks:
                all_chunks.append((chunk.score, chunk.content, phase))

        all_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = all_chunks[:top_k]

        scores = [c[0] for c in top_chunks]
        chunks = [f"[{c[2]}] {c[1]}" for c in top_chunks]

        return scores, chunks

    def _retrieve_from_volcano(
        self,
        query: str,
        domain: str,
        api_key: str,
        service_id: str,
        top_k: int = 5,
    ) -> tuple[list[float], list[str]]:
        """
        火山引擎向量知识库检索

        认证优先级: HMAC-SHA256签名 > Bearer token

        API: POST https://{domain}/api/knowledge/v1/search
        """
        # ── 方式1: HMAC-SHA256 签名 (优先) ──
        ak = os.getenv("VOLC_ACCESS_KEY", "")
        sk = os.getenv("VOLC_SECRET_KEY", "")
        if ak and sk:
            try:
                from src.volcengine_auth import VolcSigner
                volc_service = os.getenv("VOLC_SERVICE", "air")
                volc_region = os.getenv("VOLC_REGION", "cn-north-1")
                signer = VolcSigner(ak=ak, sk=sk, service=volc_service, region=volc_region)

                path = "/api/knowledge/v1/search"
                body_dict = {
                    "service_id": service_id,
                    "query": query,
                    "top_k": top_k,
                    "search_type": "semantic",
                }
                body_str = json.dumps(body_dict, ensure_ascii=False)
                signed_headers = signer.sign(
                    method="POST", host=domain, path=path, body=body_str,
                )

                url = f"https://{domain}{path}"
                req = urllib.request.Request(
                    url,
                    data=body_str.encode("utf-8"),
                    headers=signed_headers,
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                records = data.get("results") or data.get("data") or data.get("records") or []
                scores = [
                    r.get("score", r.get("relevance", r.get("similarity", 0.0)))
                    for r in records
                ]
                chunks = [
                    r.get("content", "") or r.get("text", "") or r.get("chunk", "")
                    for r in records
                ]
                return scores, chunks
            except Exception:
                # HMAC失败 → 降级到Bearer
                pass

        # ── 方式2: Bearer token (降级) ──
        endpoint = f"https://{domain}/api/knowledge/v1/search"
        payload = json.dumps({
            "service_id": service_id,
            "query": query,
            "top_k": top_k,
            "search_type": "semantic",
        }).encode("utf-8")

        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # 解析结果 (兼容多种返回格式)
        records = data.get("results") or data.get("data") or data.get("records") or []
        scores = [
            r.get("score", r.get("relevance", r.get("similarity", 0.0)))
            for r in records
        ]
        chunks = [
            r.get("content", "") or r.get("text", "") or r.get("chunk", "")
            for r in records
        ]

        return scores, chunks

    def get_summary(self, results: list[BoundaryResult]) -> dict:
        """汇总边界检测统计"""
        total = len(results)
        if total == 0:
            return {"in_scope_pct": 0, "partial_pct": 0, "out_of_scope_pct": 0, "total": 0}

        in_scope = sum(1 for r in results if r.status == "in_scope")
        partial = sum(1 for r in results if r.status == "partial_match")
        out_of = sum(1 for r in results if r.status == "out_of_scope")

        return {
            "total": total,
            "in_scope": in_scope,
            "partial_match": partial,
            "out_of_scope": out_of,
            "in_scope_pct": round(in_scope / total, 2),
            "partial_pct": round(partial / total, 2),
            "out_of_scope_pct": round(out_of / total, 2),
        }
