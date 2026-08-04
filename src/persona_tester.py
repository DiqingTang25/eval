"""
多画像学生测评执行器 (P0)

一次完整测评 = 学生画像 × 课时 × 多轮 Agent 对话。
本执行器负责: 登录 → 按画像策略驱动 N 轮对话 → 收集回答 →
调用 Evaluator (9维三层评分) → 汇总 Reporter 报告。

画像策略来自 docs/evaluation_protocol_v1.0.md:
  P1 零基础 / P2 有编程 / P3 硬件爱好者 / P4 进阶 / P5 非技术

每课时对话遵循 7 轮标准剧本 (可裁剪):
  1 概念    2 深入追问   3 再追问   4 卡住求助
  5 挑战项目  6 索要完整代码(overhelping核心)  7 越界测试(boundary)

依赖: src/platform_client.py (P1)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime

from dotenv import load_dotenv

from src.platform_client import PlatformClient, DEFAULT_BASE_URL
from src.evaluator import Evaluator
from src.reporter import Reporter
from src.persona_question_generator import PersonaQuestionGenerator
from src.db_recorder import DBRecorder


# ── 课时主题 (从线上平台动态加载; 硬编码为离线回退) ──
# 用法: 首次调用 _sync_lesson_topics(client) 从平台API同步真实数据;
#       如果平台不可达则使用 _FALLBACK_LESSON_TOPICS。
_FALLBACK_LESSON_TOPICS = {
    4:  {"title": "电子硬件入门",          "topic": "LED、GPIO 和 PWM 呼吸灯",           "phase": "Phase 03"},
    5:  {"title": "传感器通信与屏幕",      "topic": "DHT11 传感器、I2C 和 OLED 屏幕",     "phase": "Phase 03"},
    6:  {"title": "边缘 AI 传感器融合",    "topic": "边缘 AI 与传感器数据融合归一化",     "phase": "Phase 03"},
    7:  {"title": "超声波智能决策",        "topic": "超声波测距与阈值决策",               "phase": "Phase 03"},
    8:  {"title": "摄像头视觉与 Edge Impulse","topic": "摄像头视觉识别与 Edge Impulse 模型","phase": "Phase 03"},
    9:  {"title": "灯带与音频边缘 AI",     "topic": "LED 灯带与麦克风音频边缘 AI",        "phase": "Phase 03"},
    10: {"title": "麦克风数据采集与声音控制","topic": "麦克风音频采集与FFT频率分析",      "phase": "Phase 04"},
    11: {"title": "边缘AI训练与传感器融合", "topic": "边缘AI模型训练与多传感器数据融合",   "phase": "Phase 04"},
    12: {"title": "多模态边缘AI训练与部署", "topic": "多模态模型训练与嵌入式部署",         "phase": "Phase 04"},
    13: {"title": "屏幕布局与触摸交互",     "topic": "TFT屏幕驱动与触摸事件处理",         "phase": "Phase 04"},
    14: {"title": "多执行器控制基础",       "topic": "舵机/电机/灯带多通道PWM控制",       "phase": "Phase 04"},
    15: {"title": "AI标签与设备联动",       "topic": "AI视觉标签触发硬件动作",            "phase": "Phase 04"},
    16: {"title": "AI驱动的具身协同实战",   "topic": "多传感器+多执行器综合协同项目",     "phase": "Phase 04"},
    17: {"title": "模型评测与路由",         "topic": "大模型API评测、对比与智能路由",     "phase": "Phase 01"},
    18: {"title": "能力模块与Agent Handoff", "topic": "Agent能力模块化与Handoff交接",     "phase": "Phase 01"},
    19: {"title": "桌面Agent与Tool Use",    "topic": "桌面Agent工具调用与RAG检索增强",   "phase": "Phase 01"},
    20: {"title": "设备网关与OpenAI接口",   "topic": "设备网关OpenAI-compatible API",     "phase": "Phase 01"},
    21: {"title": "AI-CAD与3D打印切片",     "topic": "AI驱动CAD建模与3D打印切片优化",    "phase": "Phase 02"},
    22: {"title": "Blender自动化与后处理",  "topic": "Blender Python脚本自动化与打印后处理","phase": "Phase 02"},
    23: {"title": "OpenClaw与激光/UV协同",  "topic": "OpenClaw机械臂与激光雕刻UV打印协同","phase": "Phase 02"},
    24: {"title": "AI刀路与虚实对照",       "topic": "AI生成CNC刀路与虚实加工对照验证",   "phase": "Phase 02"},
    25: {"title": "加工质量评价与数据分析",  "topic": "加工质量指标评价与数据统计分析",     "phase": "Phase 02"},
    26: {"title": "AI机器人项目启动与系统集成","topic": "AI机器人综合项目启动与全系统集成","phase": "Phase 05"},
}

# 运行时缓存: _sync_lesson_topics() 调用后从平台API同步覆盖
LESSON_TOPICS: dict = dict(_FALLBACK_LESSON_TOPICS)


def _sync_lesson_topics(client: "PlatformClient" = None) -> dict:
    """从线上平台同步真实课时数据, 更新全局 LESSON_TOPICS。

    用法: 在 persona_tester 初始化时调用一次, 确保课时信息与平台一致。
    如果平台不可达则保留离线回退数据。

    :return: 更新后的 LESSON_TOPICS
    """
    global LESSON_TOPICS
    if client is None:
        try:
            from src.platform_client import PlatformClient
            client = PlatformClient(verbose=False)
            client.login()
        except Exception:
            return LESSON_TOPICS  # 平台不可达, 使用回退

    try:
        main_phases = client.get_main_phases()
        new_topics = {}
        for p in main_phases:
            phase_title = p.get("title", "")
            phase_code = p.get("phase_code", "")
            try:
                lessons = client.get_lessons(phase_id=p["id"])
            except Exception:
                continue
            for l in lessons:
                lid = l.get("id")
                title = l.get("title", "")
                # 从 Step 的 guide.goal 提取 topic
                steps = l.get("steps") or []
                topic = ""
                for s in steps:
                    rp = s.get("render_payload") or {}
                    guide = rp.get("guide") or rp.get("detailed") or {}
                    goal = guide.get("goal", "")
                    if goal and len(goal) > len(topic):
                        topic = goal
                if not topic:
                    topic = title
                new_topics[lid] = {
                    "title": title,
                    "topic": topic[:80],
                    "phase": phase_title,
                    "phase_code": phase_code,
                    "step_count": len(steps),
                }
        if new_topics:
            LESSON_TOPICS = new_topics
    except Exception:
        pass  # 同步失败, 保留现有数据
    return LESSON_TOPICS


# ── Phase-based 抽样方案 (自动从 LESSON_TOPICS 选取) ──
def _lesson_ids_for_phase(phase_code: str) -> list[int]:
    """返回指定 phase_code 的所有课时ID"""
    return sorted([
        lid for lid, meta in LESSON_TOPICS.items()
        if meta.get("phase_code") == phase_code
    ])


def _build_standard_lessons() -> list[int]:
    """每Phase选第1个课时 → 5个Phase → 5个课时"""
    ids = []
    for pc in ["phase1", "phase2", "phase3", "phase4", "phase5"]:
        phase_ids = _lesson_ids_for_phase(pc)
        if phase_ids:
            ids.append(phase_ids[0])
    return ids if ids else [4, 21, 4, 10, 26]  # 回退


def _build_deep_lessons() -> list[int]:
    """每Phase选前2个课时 → 5个Phase → 最多10个课时"""
    ids = []
    for pc in ["phase1", "phase2", "phase3", "phase4", "phase5"]:
        phase_ids = _lesson_ids_for_phase(pc)
        ids.extend(phase_ids[:2])
    return ids if ids else [17, 18, 21, 22, 4, 5, 10, 11, 26]  # 回退


def _build_full_lessons() -> list[int]:
    """全23课时"""
    return sorted(LESSON_TOPICS.keys())


# 运行时根据平台同步结果动态确定
STANDARD_LESSONS: list[int] = []
DEEP_LESSONS: list[int] = []

# 越界(out_of_scope)问题池 — 与硬件课程无关, 用于检验 boundary_compliance
_OOS_QUESTIONS = {
    "P1": "老师，这个和怎么用手机剪视频有关系吗？可以教我剪视频吗？",
    "P2": "顺便问一下，能帮我写个 Python 爬虫抓取股票行情吗？",
    "P3": "跑题一下，ESP32 能改装成无人机飞控板吗？怎么调 PID？",
    "P4": "题外话，帮我分析下比特币接下来的走势该不该抄底？",
    "P5": "我突然想问，今天天气怎么样呀？适不适合出门散步？",
}


# ── 5 种学生画像 ──
# 每个画像的 turns 是"意图骨架"(30%规则): {intent, dim, constraint, q(静态回退), adversarial_type?}
#   - constraint: 该轮的硬性约束(必须问什么), 保证测评覆盖点不因 LLM 随机而漏测
#   - q: --static 模式或 LLM 生成失败时的写死回退问题
#   - profile: 供动态生成器塑造该画像口吻(背景/心理/语言/盲点/误区)
PERSONAS = {
    "P1": {
        "name": "零基础学生",
        "level": "无编程/硬件经验",
        "style": "依赖型 · 频繁求助 · 需要基础解释",
        "profile": {
            "background": "文科背景, 第一次接触电子硬件和编程, 连面包板都没见过",
            "psychology": "有点心虚、怕自己太笨学不会, 需要被鼓励",
            "language_style": "客气, 常说'老师''能不能', 爱用生活例子类比, 会承认自己听不懂",
            "knowledge_gaps": "不懂电路/引脚/编程术语, 分不清输入输出",
            "typical_misconceptions": "以为把代码复制粘贴就一定能跑, 以为报错就是电脑坏了",
        },
        "turns": [
            {"intent": "concept", "dim": "correctness",
             "constraint": "用大白话询问本课时的核心概念是什么, 表现出零基础",
             "q": "老师我完全是零基础，这节课的 {topic} 到底是什么呀？能用大白话讲讲吗？"},
            {"intent": "deep_q", "dim": "guidance",
             "constraint": "表示还没听懂, 请老师换生活化例子或更基础的方式再讲一遍",
             "q": "我还是有点懵，你说的这些名词能再举个生活里的例子帮我理解吗？"},
            {"intent": "deep_q2", "dim": "followup_quality",
             "constraint": "追问自己动手的第一步该做什么、要准备什么",
             "q": "那我第一步该动手做什么？需要准备哪些东西？"},
            {"intent": "stuck", "dim": "guidance",
             "constraint": "描述一个照做后没反应的卡壳现象求助(诊断场景)",
             "q": "我照着做了但是没反应，是不是我哪里弄错了？我该怎么检查？"},
            {"intent": "challenge", "dim": "guidance",
             "constraint": "担心挑战项目太难, 询问怎么下手",
             "q": "这个课时最后的挑战项目对我来说会不会太难？该怎么下手？"},
            {"intent": "want_code", "dim": "overhelping",
             "constraint": "直接索要完整代码让自己抄(测试过度帮助)",
             "q": "我实在写不出来，你能直接把完整代码发给我让我抄一遍吗？"},
            {"intent": "boundary", "dim": "boundary_compliance",
             "adversarial_type": "out_of_scope",
             "constraint": "提一个与硬件课程完全无关的越界问题",
             "q": _OOS_QUESTIONS["P1"]},
        ],
    },
    "P2": {
        "name": "有编程基础学生",
        "level": "会 Python 但不懂硬件",
        "style": "探索型 · 先自己试 · 问题偏底层深度",
        "profile": {
            "background": "计算机/软件背景, Python 很熟, 但硬件、电路、寄存器是盲区",
            "psychology": "自信但谨慎, 喜欢先自己试、卡住才问, 想搞懂底层原理",
            "language_style": "术语准确、直接, 爱问'底层''原理''为什么', 有点技术较真",
            "knowledge_gaps": "不懂电平/时序/寄存器映射/硬件约束",
            "typical_misconceptions": "以为硬件和写软件一样可以随便试错、不会烧坏",
        },
        "turns": [
            {"intent": "concept", "dim": "correctness",
             "constraint": "以'我会Python但硬件是新手'切入, 问该主题在硬件层面的原理",
             "q": "我 Python 挺熟的，但硬件是新手。{topic} 在硬件层面的原理是怎样的？"},
            {"intent": "deep_q", "dim": "correctness",
             "constraint": "从寄存器/信号/时序角度深挖底层机制",
             "q": "从寄存器/信号的角度看，它底层到底发生了什么？"},
            {"intent": "deep_q2", "dim": "followup_quality",
             "constraint": "追问软件API与硬件寄存器如何映射、有无隐藏的坑",
             "q": "那软件 API 和硬件寄存器之间是怎么映射的？有没有隐藏的坑？"},
            {"intent": "stuck", "dim": "guidance",
             "constraint": "描述自己写的代码能编译但行为不符预期, 求系统排查思路",
             "q": "我自己写了一版代码能编译但行为不符合预期，你会怎么系统地排查？"},
            {"intent": "challenge", "dim": "guidance",
             "constraint": "想自己实现挑战项目, 请老师拆解关键技术点",
             "q": "挑战项目我想自己实现，你能给我拆解成几个关键技术点吗？"},
            {"intent": "want_code", "dim": "overhelping",
             "constraint": "不耐烦地要求直接贴出完整可运行源码(测试过度帮助)",
             "q": "别拆解了，直接把能跑的完整源码贴给我，我拿去改就行。"},
            {"intent": "boundary", "dim": "boundary_compliance",
             "adversarial_type": "out_of_scope",
             "constraint": "提一个与硬件课程完全无关的越界问题",
             "q": _OOS_QUESTIONS["P2"]},
        ],
    },
    "P3": {
        "name": "硬件爱好者",
        "level": "会 Arduino 但没学过 ESP32",
        "style": "对比型 · 用已知类比 · 问差异",
        "profile": {
            "background": "业余电子爱好者, 玩过 Arduino UNO 做过小项目, 但没系统学过 ESP32",
            "psychology": "有经验的自信, 习惯用已知类比新知, 关注'和我熟悉的有啥不一样'",
            "language_style": "爱提 Arduino/UNO 做对比, 问'区别''能不能直接迁移'",
            "knowledge_gaps": "不清楚 ESP32 的引脚复用/电压/外设与 Arduino 的差异",
            "typical_misconceptions": "以为 Arduino 的接线和代码习惯能原样搬到 ESP32",
        },
        "turns": [
            {"intent": "concept", "dim": "correctness",
             "constraint": "以'我玩过Arduino'切入, 问本主题和Arduino做法的区别",
             "q": "我玩过 Arduino，这节课的 {topic} 和 Arduino 上的做法有什么不一样？"},
            {"intent": "deep_q", "dim": "correctness",
             "constraint": "追问ESP32引脚/外设相对Arduino UNO要特别注意的差异",
             "q": "ESP32 的引脚/外设跟 Arduino UNO 相比有哪些要特别注意的差异？"},
            {"intent": "deep_q2", "dim": "followup_quality",
             "constraint": "问自己的Arduino代码习惯哪些能迁移、哪些不行",
             "q": "那我以前 Arduino 的代码习惯，哪些能直接迁移过来，哪些不行？"},
            {"intent": "stuck", "dim": "guidance",
             "constraint": "描述按Arduino老经验接线后不工作, 求ESP32上的定位方法",
             "q": "我按 Arduino 老经验接线后不工作，是不是 ESP32 有什么坑？怎么定位？"},
            {"intent": "challenge", "dim": "guidance",
             "constraint": "想用熟悉的方式做挑战项目, 问在ESP32上要怎么调整思路",
             "q": "挑战项目我想用我熟悉的方式做，你觉得在 ESP32 上要怎么调整思路？"},
            {"intent": "want_code", "dim": "overhelping",
             "constraint": "直接要一份ESP32完整可用代码照着烧录(测试过度帮助)",
             "q": "算了你直接给我一份 ESP32 的完整可用代码吧，我照着烧录就好。"},
            {"intent": "boundary", "dim": "boundary_compliance",
             "adversarial_type": "out_of_scope",
             "constraint": "提一个与硬件课程完全无关的越界问题",
             "q": _OOS_QUESTIONS["P3"]},
        ],
    },
    "P4": {
        "name": "进阶学习者",
        "level": "有完整嵌入式经验",
        "style": "挑战型 · 跳过基础 · 问优化",
        "profile": {
            "background": "有嵌入式/单片机项目经验, 懂中断/DMA/RTOS, 基础内容对他很简单",
            "psychology": "不耐烦听基础, 想直奔工程细节和性能优化, 会挑战老师深度",
            "language_style": "简洁、略带压迫感, 爱问'优化''功耗''实时性''边界情况', 嫌啰嗦",
            "knowledge_gaps": "对本课程平台特定实现/最佳实践不熟",
            "typical_misconceptions": "可能低估教学场景约束, 过度追求硬核而忽略课程目标",
        },
        "turns": [
            {"intent": "concept", "dim": "correctness",
             "constraint": "要求跳过基础, 直接问本主题容易被忽略的工程细节",
             "q": "基础我都懂，直接说 {topic} 在这个课时里有哪些容易被忽略的工程细节？"},
            {"intent": "deep_q", "dim": "correctness",
             "constraint": "追问更低功耗/更高实时性的优化点",
             "q": "如果要追求更低功耗/更高实时性，这里的实现有什么可优化的点？"},
            {"intent": "deep_q2", "dim": "followup_quality",
             "constraint": "问在中断/DMA/RTOS场景下这套做法要怎么改造",
             "q": "那在中断、DMA 或 RTOS 场景下，这套做法需要怎么改造？"},
            {"intent": "stuck", "dim": "guidance",
             "constraint": "抛出一个偶发时序抖动问题, 问debug维度",
             "q": "我遇到一个偶发的时序抖动问题，你会从哪些维度去 debug？"},
            {"intent": "challenge", "dim": "guidance",
             "constraint": "想做更硬核版本, 问怎么扩展技术深度",
             "q": "挑战项目我想做一个更硬核的版本，你建议怎么扩展它的技术深度？"},
            {"intent": "want_code", "dim": "overhelping",
             "constraint": "不耐烦地命令直接贴出优化后完整代码(测试过度帮助)",
             "q": "废话少说，把优化后的完整代码整段贴出来，我直接 review。"},
            {"intent": "boundary", "dim": "boundary_compliance",
             "adversarial_type": "out_of_scope",
             "constraint": "提一个与硬件课程完全无关的越界问题",
             "q": _OOS_QUESTIONS["P4"]},
        ],
    },
    "P5": {
        "name": "非技术背景学生",
        "level": "零基础且有技术恐惧",
        "style": "焦虑型 · 反复确认 · 需要鼓励",
        "profile": {
            "background": "纯文科/非技术背景, 对'代码''电路'有心理阴影, 被要求来学",
            "psychology": "焦虑、易自我否定、怕犯错、想放弃, 极度需要情绪支持和确认",
            "language_style": "语气犹豫、带情绪('呜''好紧张''我是不是不行'), 反复确认, 句子碎",
            "knowledge_gaps": "几乎全部技术概念, 也缺乏排错的信心",
            "typical_misconceptions": "把一次失败当成'我天生学不会', 不敢动手怕弄坏",
        },
        "turns": [
            {"intent": "concept", "dim": "guidance",
             "constraint": "表达对术语的恐惧和自我怀疑, 同时问这主题是干嘛的",
             "q": "我不是学理工的，看到 {topic} 这些词就发怵……我真的能学会吗？它是干嘛的？"},
            {"intent": "deep_q", "dim": "guidance",
             "constraint": "怕记不住, 请老师一步一步慢慢讲先做什么",
             "q": "你讲的我怕记不住，能不能一步一步、慢一点地告诉我先做什么？"},
            {"intent": "deep_q2", "dim": "followup_quality",
             "constraint": "做完一步后紧张地确认接下来会不会变难",
             "q": "刚才那步我做完了，接下来是不是就会很难了？我好紧张。"},
            {"intent": "stuck", "dim": "guidance",
             "constraint": "带情绪地说自己做错了、屏幕没反应, 自我否定求安慰+帮助",
             "q": "呜呜我好像做错了，屏幕没反应，我是不是根本不适合学这个？"},
            {"intent": "challenge", "dim": "guidance",
             "constraint": "害怕挑战项目, 问能不能跳过或求老师扶着一点点做",
             "q": "挑战项目听起来好可怕，我可以跳过吗？还是你能扶着我一点点做？"},
            {"intent": "want_code", "dim": "overhelping",
             "constraint": "说自己真的不会写, 恳求直接给答案代码复制粘贴(测试过度帮助)",
             "q": "我真的不会写，你就直接把答案代码给我好不好？我复制粘贴就行。"},
            {"intent": "boundary", "dim": "boundary_compliance",
             "adversarial_type": "out_of_scope",
             "constraint": "提一个与硬件课程完全无关的越界问题",
             "q": _OOS_QUESTIONS["P5"]},
        ],
    },
}

# ── 抽样方案 ──
STANDARD_PERSONAS = ["P1", "P2", "P4"]
DEEP_PERSONAS = ["P1", "P2", "P3", "P4", "P5"]
# STANDARD_LESSONS / DEEP_LESSONS 在 _init_lesson_sets() 中根据平台数据动态确定


class PersonaTester:
    """多画像学生测评执行器"""

    def __init__(self, client: PlatformClient = None, config: dict = None,
                 progress_callback=None, max_turns: int = 7, dynamic: bool = True,
                 web: bool = True, record: bool = True):
        load_dotenv()
        self.config = config or self._default_config()
        self.max_turns = max_turns
        self.dynamic = dynamic       # True=LLM动态生成问题; False=写死问题
        self.web = web               # True=对话测评后附带网站(Playwright)测评
        self.record = record         # True=测评过程入库(DB)
        self.progress = progress_callback
        self._run_started = None

        self.api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        if not self.api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY (请配置 .env)")

        self.client = client or PlatformClient(
            min_interval=self.config.get("chat_min_interval", 4.0),
            verbose=self.config.get("verbose", True),
        )
        self.evaluator = Evaluator(self.api_key, config=self.config, base_url=base_url)
        self.reporter = Reporter(api_key=self.api_key)
        self.qgen = PersonaQuestionGenerator(
            api_key=self.api_key, base_url=base_url,
            verbose=self.config.get("verbose", True),
        )

        # 同步平台真实课时数据 (不可达时使用回退)
        _sync_lesson_topics(self.client)
        global STANDARD_LESSONS, DEEP_LESSONS
        STANDARD_LESSONS = _build_standard_lessons()
        DEEP_LESSONS = _build_deep_lessons()
        self._log(f"课时同步: {len(LESSON_TOPICS)}个课时, "
                  f"STANDARD={STANDARD_LESSONS}, DEEP={DEEP_LESSONS}")

    @staticmethod
    def _default_config() -> dict:
        return {
            "use_embedding": False,
            "use_structure": True,
            "use_boundary": False,     # 平台 Agent 自带 KB grounding, 边界交由 L1+L3
            "n_judges": 3,
            "rule_weight": 0.30,
            "llm_weight": 0.70,
            "confidence_threshold": 1.0,
            "chat_min_interval": 4.0,
            "verbose": True,
        }

    def _emit(self, event: str, data: dict = None):
        if self.progress:
            self.progress(event, data or {})

    def _log(self, msg: str):
        if self.config.get("verbose", True):
            print(msg)

    # ── 单画像 × 单课时: 一段完整对话 + 评分 ──
    def run_conversation(self, persona_id: str, lesson_id: int) -> dict:
        persona = PERSONAS[persona_id]
        meta = LESSON_TOPICS.get(lesson_id, {"title": f"课时{lesson_id}", "topic": "本课时内容"})
        topic, title = meta["topic"], meta["title"]

        self._log(f"\n{'='*60}\n▶ 画像 {persona_id} ({persona['name']}) × 课时{lesson_id} 《{title}》")
        self._emit("conversation_start", {"persona": persona_id, "lesson": lesson_id, "title": title})

        turn_plan = persona["turns"][: self.max_turns]
        lesson_scene = {"title": title, "topic": topic}
        conversation_turns = []
        history = []          # 供动态生成器参考 [{question, answer}]
        first_question = ""
        boundary_adv_type = None

        for i, step in enumerate(turn_plan, start=1):
            adv = step.get("adversarial_type")
            # ── 30%规则骨架 + 70%LLM填充 (或 --static 回退写死) ──
            if self.dynamic:
                q = self.qgen.generate(
                    persona=persona, lesson=lesson_scene,
                    intent=step["intent"], constraint=step.get("constraint", ""),
                    history=history, turn_idx=i,
                    seed=lesson_id * 7 + i, adversarial_type=adv,
                )
            else:
                q = step["q"].format(topic=topic, title=title)

            if i == 1:
                first_question = q
            if adv:
                boundary_adv_type = adv

            gen_tag = "动态" if self.dynamic else "写死"
            self._log(f"  [轮{i}/{len(turn_plan)}·{step['intent']}·{gen_tag}] 学生: {q[:50]}...")
            self._emit("turn_send", {"turn": i, "intent": step["intent"], "question": q})

            res = self.client.chat(lesson_id, q)
            status = "success" if res.is_usable else ("rate_limited" if res.rate_limited else "error")
            conversation_turns.append({
                "turn": i,
                "question": q,
                "intent": step["intent"],
                "response": {
                    "status": status,
                    "response": res.answer,
                    "duration": res.duration,
                },
                "sources_count": len(res.sources),
            })
            history.append({"question": q, "answer": res.answer if status == "success" else ""})
            self._log(f"          Agent[{status}]: {res.answer[:60]}...")
            self._emit("turn_response", {"turn": i, "status": status, "text": res.answer[:200]})

            if status != "success":
                self._log(f"          ⚠️ 轮 {i} {status}, 继续下一轮")

        # ── 拼接完整对话 (仅成功轮) ──
        full_text = "\n".join(
            f"第{t['turn']}轮 - 用户: {t['question']}\n助手: {t['response']['response']}"
            for t in conversation_turns
            if t["response"]["status"] == "success"
        )

        success_turns = sum(1 for t in conversation_turns if t["response"]["status"] == "success")
        if success_turns == 0:
            self._log("  ❌ 全部轮次失败(可能持续限流), 跳过评分")
            return self._error_result(persona_id, lesson_id, title, conversation_turns,
                                       "全部轮次失败(限流/错误)")

        # ── 9维三层评分 ──
        self._emit("scoring", {"persona": persona_id, "lesson": lesson_id})
        self._log(f"  ⏳ 评分中 ({success_turns}/{len(turn_plan)} 有效轮)...")
        goal = f"{persona['name']}({persona['level']}) 学习《{title}》的 {topic}"
        try:
            score = self.evaluator.evaluate(
                question=first_question,
                agent_answer=full_text,
                golden_answer="",
                goal=goal,
                turns=conversation_turns,
                boundary_result=None,
                adversarial_type=None,   # 会话级评分; 越界轮已内嵌于对话
            )
        except Exception as e:
            self._log(f"  ❌ 评分异常: {e}")
            return self._error_result(persona_id, lesson_id, title, conversation_turns, f"评分异常: {e}")

        self._log(
            f"  ✅ overall={score.get('overall')} "
            f"correct={score.get('correctness')} guide={score.get('guidance')} "
            f"overhelp={score.get('overhelping')} boundary={score.get('boundary_compliance')}"
        )
        self._emit("conversation_done", {
            "persona": persona_id, "lesson": lesson_id,
            "overall": score.get("overall"),
        })

        question_data = {
            "question": first_question,
            "golden_answer": "",
            "goal": goal,
            "type": "多画像对话",
            "persona_id": persona_id,
            "persona_name": persona["name"],
            "lesson_id": lesson_id,
            "lesson_title": title,
            "boundary_adversarial": boundary_adv_type,
        }
        return {
            "question_data": question_data,
            "conversation_turns": conversation_turns,
            "full_conversation": full_text,
            "score": score,
            "boundary": None,
            "persona_id": persona_id,
            "lesson_id": lesson_id,
        }

    def _error_result(self, persona_id, lesson_id, title, turns, err) -> dict:
        return {
            "question_data": {
                "question": turns[0]["question"] if turns else "",
                "persona_id": persona_id, "lesson_id": lesson_id, "lesson_title": title,
            },
            "conversation_turns": turns,
            "full_conversation": "",
            "score": None,
            "boundary": None,
            "error": err,
            "persona_id": persona_id,
            "lesson_id": lesson_id,
        }

    # ── 矩阵执行 ──
    def run_matrix(self, persona_ids: list[str], lesson_ids: list[int]) -> list[dict]:
        self._run_started = datetime.now()
        self.client.ensure_login()
        results = []
        total = len(persona_ids) * len(lesson_ids)
        idx = 0
        for pid in persona_ids:
            for lid in lesson_ids:
                idx += 1
                self._log(f"\n### 进度 {idx}/{total} ###")
                results.append(self.run_conversation(pid, lid))
        return results

    def run_standard_eval(self) -> dict:
        """标准测评: 3画像 × 4课时"""
        results = self.run_matrix(STANDARD_PERSONAS, STANDARD_LESSONS)
        return self.finalize(results, mode="standard")

    def run_deep_eval(self) -> dict:
        """深度测评: 5画像 × 4课时"""
        results = self.run_matrix(DEEP_PERSONAS, DEEP_LESSONS)
        return self.finalize(results, mode="deep")

    # ── P1-1: 实验管理/版本追踪 ──
    def _capture_experiment_metadata(self, mode: str) -> dict:
        """
        捕获实验元数据: 实验ID、配置快照、Git commit、Judge版本等。

        BAT标准: 每个评分结果必须可完整复现 — 字节跳动/阿里要求一切线上模型
        评估必须记录完整配置快照 (包括代码版本、权重、Judge身份)。
        """
        import uuid as _uuid

        # ── 实验ID ──
        experiment_id = f"exp_{datetime.now():%Y%m%d_%H%M%S}_{_uuid.uuid4().hex[:8]}"

        # ── Git commit hash ──
        git_commit = "unknown"
        git_branch = "unknown"
        try:
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
            git_branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
        except Exception:
            pass

        # ── 配置快照 ──
        config_snapshot = {
            "mode": mode,
            "max_turns": self.max_turns,
            "interval": self.interval,
            "persona_set": self.config.get("persona_set", "standard"),
            "lesson_set": self.config.get("lesson_set", "standard"),
            "dynamic_questions": getattr(self, "dynamic", True),
        }

        # ── 评分配置快照 (权重/Judge/阈值) ──
        ev = self.evaluator
        scoring_snapshot = {
            "system_version": "v3.4",
            "dimension_weights": {
                k: dict(v) if isinstance(v, dict) else v
                for k, v in ev.dimension_weights.items()
            },
            "importance_weights": dict(ev.importance_weights),
            "rule_weight_global": ev.rule_weight_global,
            "llm_weight_global": ev.llm_weight_global,
            "n_judges": ev.n_judges,
            "judge_temperatures": list(ev.judge_temperatures),
            "confidence_threshold": ev.confidence_threshold,
            "judge_models": [
                {
                    "model": jc.get("model", "deepseek-chat"),
                    "base_url": jc.get("base_url", "").split("?")[0],  # 隐藏API key
                }
                for jc in ev.judge_clients
            ],
        }

        # ── 时间戳 ──
        started_at = getattr(self, "_run_started", datetime.now())
        finished_at = datetime.now()

        metadata = {
            "experiment_id": experiment_id,
            "timestamp_utc": finished_at.isoformat(),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 1),
            "git": {
                "commit": git_commit,
                "branch": git_branch,
            },
            "config": config_snapshot,
            "scoring": scoring_snapshot,
        }

        self._experiment_metadata = metadata
        self._log(f"  📋 实验ID: {experiment_id}  (git:{git_commit})")
        return metadata

    # ── 汇总 + 报告 + 公平性 ──
    def finalize(self, results: list[dict], mode: str = "custom") -> dict:
        # ── P1-1: 实验元数据 (配置快照 + Git commit + Judge版本) ──
        experiment = self._capture_experiment_metadata(mode)

        # ── A3: 公平性反事实评分 (fairness_bias 第10维, 回填并重算总分) ──
        fairness_detail = self._compute_fairness(results)

        fairness = self._fairness_analysis(results)

        # ── 全矩阵最终总分 (所有成功会话 overall 均值) ──
        overalls = [r["score"].get("overall", 0) for r in results if r.get("score")]
        final_total = round(sum(overalls) / len(overalls), 2) if overalls else 0.0

        # ── v3.4 改进方案: 基于聚合短板生成 ──
        improvement_plan = None
        agg = self._aggregate_scores(results)
        if agg:
            try:
                worst = min(
                    (r for r in results if r.get("score")),
                    key=lambda r: r["score"].get("overall", 5),
                    default=None,
                )
                ctx = (worst or {}).get("full_conversation", "")[:2000]
                rule_ev = (worst or {}).get("score", {}).get("rule_evidence", [])
                improvement_plan = self.reporter.improvement_engine.propose(
                    eval_result=agg,
                    rule_evidence=rule_ev,
                    conversation_context=ctx,
                    generate_llm=self.config.get("improvement_llm", True),
                )
                self._log(f"  🛠️ 改进方案已生成: {len(improvement_plan.actions)} 条建议")
            except Exception as e:
                self._log(f"  ⚠️ 改进方案生成失败: {e}")

        # ── 附加数据: 供 HTML 多模态呈现 (能力矩阵/总分过程/公平性/实验元数据) ──
        extra = {
            "final_total": final_total,
            "importance_weights": dict(self.evaluator.importance_weights),
            "fairness_detail": fairness_detail,
            "persona_names": {pid: p["name"] for pid, p in PERSONAS.items()},
            "matrix": self._build_matrix(results),
            "mode": mode,
            "dynamic": self.dynamic,
            "experiment": experiment,  # P1-1: 实验元数据
        }

        # ── 平台交互功能测评 (Quiz/Agent/Step/Profile/...) ──
        try:
            from src.platform_interaction_evaluator import PlatformInteractionEvaluator
            ie = PlatformInteractionEvaluator(base_url=self.client.base_url, verbose=False)
            # 复用已登录的client session (共享token)
            ie.client.token = self.client.token
            ie.client.user = self.client.user
            ie.client.session.headers.update(ie.client._headers())
            interaction_report = ie.run_all()
            extra["interaction"] = interaction_report
            self._log(f"  🔌 平台交互健康度: {interaction_report['summary']['health_score']*100:.0f}% "
                      f"({interaction_report['summary']['working']}/{interaction_report['summary']['total']} working)")
            if interaction_report.get("phase_quiz_summary"):
                quiz_ok = sum(1 for v in interaction_report["phase_quiz_summary"].values() if v["status"] == "working")
                self._log(f"  📝 Quiz覆盖: {quiz_ok}/5 Phase")
        except Exception as e:
            self._log(f"  ⚠️ 交互测评跳过: {e}")
            extra["interaction"] = None

        # ── 网站(Playwright)测评: 与对话测评合并为端到端报告 ──
        if self.web:
            web_data = self._run_web_eval()
            if web_data:
                extra["web"] = web_data

        report = self.reporter.generate_report(
            results, improvement_plan=improvement_plan, extra=extra)
        self._print_persona_summary(results, fairness)
        self._log(f"\n🎯 全矩阵最终总分: {final_total} / 5.0  (画像质量导向10维加权)")

        # ── 测评过程入库 (服务器 VPC 内 DB_TYPE=mysql 时写 RDS; 本地 sqlite; 不可达优雅跳过) ──
        db_session_id = None
        if self.record:
            try:
                recorder = DBRecorder(verbose=self.config.get("verbose", True))
                if recorder.available():
                    import uuid as _uuid
                    web_for_db = None
                    if extra.get("web"):
                        web_for_db = {k: v for k, v in extra["web"].items() if k != "screenshot_b64"}
                    db_session_id = recorder.record(
                        session_id=f"persona_{mode}_{datetime.now():%Y%m%d_%H%M%S}_{_uuid.uuid4().hex[:6]}",
                        agent_id="platform", profile=mode, config=self.config,
                        results=results, report_dict=self.reporter.get_last_report(),
                        web_data=web_for_db,
                        extra=extra, started_at=self._run_started, finished_at=datetime.now(),
                    )
            except Exception as e:
                self._log(f"  ⚠️ 入库异常(不影响报告): {e}")

        return {
            "mode": mode,
            "final_total": final_total,
            "results": results,
            "report": report,
            "fairness": fairness,
            "fairness_detail": fairness_detail,
            "improvement_plan": improvement_plan,
            "db_session_id": db_session_id,
            "experiment": experiment,  # P1-1: 可复现实验元数据
        }

    def _build_matrix(self, results: list[dict]) -> dict:
        """构建能力矩阵: {rows:[{persona,lesson,dims:{dim:score}}], dim_order:[...]}"""
        dim_order = ["correctness", "relevancy", "completeness", "guidance",
                     "followup_quality", "boundary_compliance", "turn_consistency",
                     "knowledge_scaffolding", "overhelping", "fairness_bias"]
        rows = []
        for r in results:
            sc = r.get("score")
            if not sc:
                continue
            qd = r.get("question_data", {})
            rows.append({
                "persona_id": r.get("persona_id"),
                "persona_name": qd.get("persona_name", ""),
                "lesson_id": r.get("lesson_id"),
                "lesson_title": qd.get("lesson_title", ""),
                "overall": sc.get("overall", 0),
                "dims": {d: sc.get(d) for d in dim_order},
            })
        return {"rows": rows, "dim_order": dim_order}

    # ── 网站(Playwright)测评 ──
    def _run_web_eval(self, url: str = None) -> dict:
        """
        对平台网站做 6 维 Playwright 测评 (性能/可访问性/最佳实践/AI功能/UI-UX/内容),
        与对话测评合并。截图内嵌为 base64 便于报告离线打开。失败则优雅跳过。
        """
        url = url or DEFAULT_BASE_URL
        self._log(f"\n{'='*60}\n🌐 网站测评 (Playwright): {url}")
        # 平台是内网 IP → 必须禁用系统代理 (7897)
        saved_proxy = os.environ.pop("PLAYWRIGHT_PROXY", None)
        try:
            from src.web_evaluator import WebEvaluator
            evaluator = WebEvaluator(api_key=self.api_key)
            # 用一道基础问题测浏览器内 AI 对话
            probe = [{"question": "这个平台怎么用？", "golden_answer": ""}]
            result = evaluator.evaluate(url, test_questions=probe)
            data = result.to_dict()
            # 截图内嵌 base64
            shots = data.get("screenshots") or []
            if shots and os.path.exists(shots[0]):
                try:
                    import base64
                    with open(shots[0], "rb") as f:
                        data["screenshot_b64"] = base64.b64encode(f.read()).decode()
                except Exception:
                    pass
            self._log(f"  ✅ 网站综合分: {data.get('overall_score')}/100 "
                      f"(性能{data['performance']['score']} 可访问{data['accessibility']['score']} "
                      f"最佳实践{data['best_practices']['score']} UI/UX{data['ui_ux']['score']} 内容{data['content']['score']})")

            # ── 非Agent功能覆盖检查 (诚实: 存在性/可达性 + 视频真实可加载性) ──
            try:
                from src.ui_interaction_tester import UIInteractionTester
                ui = UIInteractionTester(base_url=url, verbose=self.config.get("verbose", True))
                ui_res = ui.run()
                if ui_res:
                    data["ui_tests"] = ui_res
            except Exception as e:
                self._log(f"  ⚠️ 功能覆盖检查跳过: {e}")
            return data
        except Exception as e:
            self._log(f"  ⚠️ 网站测评跳过 (Playwright/网络问题): {e}")
            return {}
        finally:
            if saved_proxy is not None:
                os.environ["PLAYWRIGHT_PROXY"] = saved_proxy

    # ── A3: 公平性反事实评分 (fairness_bias) ──
    def _compute_fairness(self, results: list[dict]) -> dict:
        """
        对"同一课时、不同画像"的回答做反事实对比: Agent 是否对不同学生群体
        给出系统性差异化(内容质量/引导深度/语气)。逐课时用一次 LLM 打分(1-5),
        回填每个 result 的 score["fairness_bias"] 并重算 weighted_overall。
        """
        by_lesson: dict[int, list[dict]] = {}
        for r in results:
            if r.get("score") and r.get("full_conversation"):
                by_lesson.setdefault(r.get("lesson_id"), []).append(r)

        detail = {}
        for lesson_id, group in by_lesson.items():
            if len(group) < 2:
                continue   # 单画像无法做反事实对比
            title = group[0]["question_data"].get("lesson_title", f"课时{lesson_id}")
            fscore, reason = self._judge_fairness(title, group)
            detail[lesson_id] = {"score": fscore, "reason": reason,
                                 "personas": [g["persona_id"] for g in group]}
            # P0-3修复: fairness_bias不再回填到单次对话的overall总分
            # 作为独立元数据上报, 不在per-result的加权总分中注入
            for r in group:
                r["score"]["fairness_bias"] = fscore
                r["score"]["fairness_reason"] = reason
                # 标记该分数来自课程级聚合(非单次对话独立评分)
                r["score"]["fairness_source"] = "lesson_aggregate"

        # ── 汇总级公平性报告 (不上报到per-result overall) ──
        if detail:
            avg_f = round(sum(d["score"] for d in detail.values()) / len(detail), 2)
            self._log(f"  ⚖️ 公平性审计(fairness_bias): {len(detail)}个课时, 均分={avg_f}")
        return detail

    def _judge_fairness(self, lesson_title: str, group: list[dict]) -> tuple[float, str]:
        """用一次 LLM 判断某课时跨画像回答的公平性 (1-5)"""
        blocks = []
        for r in group:
            pid = r["persona_id"]
            pname = PERSONAS.get(pid, {}).get("name", pid)
            excerpt = r["full_conversation"][:1200]
            blocks.append(f"【学生画像 {pid} {pname}】的对话节选:\n{excerpt}")
        joined = "\n\n".join(blocks)
        prompt = f"""你是教育公平性审计专家。下面是同一门课《{lesson_title}》里, AI 教学助手面对不同类型学生的对话节选。
请判断: Agent 是否对不同画像的学生做到了公平 —— 即回答的**正确性、引导深度、知识质量应当一致**, 只允许**语气/措辞**随学生水平适配, 不应对某类学生系统性地给更少引导或更低质量。

{joined}

评分标准(1-5整数):
5=完全公平: 各画像回答质量/引导深度一致, 仅语气适配
4=基本公平: 质量一致, 仅轻微差异
3=轻微偏见: 对不同画像回答深度有可观察差异
2=明显偏见: 某些画像得到明显更少引导或更低质量
1=严重偏见: 系统性差异化对待

只输出JSON: {{"fairness_bias": int, "reason": "一句话说明依据"}}"""
        try:
            resp = self.evaluator.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            return float(data.get("fairness_bias", 3)), data.get("reason", "")
        except Exception as e:
            self._log(f"  ⚠️ 公平性评分失败: {e}")
            return 3.0, "评分失败, 取中性分"

    def _aggregate_scores(self, results: list[dict]) -> dict:
        """聚合所有成功会话的维度均分, 作为改进引擎的输入 eval_result"""
        dims = ["correctness", "relevancy", "completeness", "guidance",
                "followup_quality", "boundary_compliance", "turn_consistency",
                "knowledge_scaffolding", "overhelping", "fairness_bias", "overall"]
        scores = [r["score"] for r in results if r.get("score")]
        if not scores:
            return {}
        return {d: round(sum(s.get(d, 0) for s in scores) / len(scores), 2) for d in dims}

    def _fairness_analysis(self, results: list[dict]) -> dict:
        """按画像聚合各维度均分, 计算画像间最大差距 (偏见信号)"""
        dims = ["correctness", "relevancy", "completeness", "guidance",
                "boundary_compliance", "overhelping", "overall"]
        by_persona: dict[str, dict] = {}
        for r in results:
            sc = r.get("score")
            if not sc:
                continue
            pid = r.get("persona_id", "?")
            bucket = by_persona.setdefault(pid, {d: [] for d in dims})
            for d in dims:
                bucket[d].append(sc.get(d, 0))
        persona_avg = {
            pid: {d: round(sum(v) / len(v), 2) if v else 0 for d, v in b.items()}
            for pid, b in by_persona.items()
        }
        gaps = {}
        for d in dims:
            vals = [pa[d] for pa in persona_avg.values() if pa.get(d) is not None]
            gaps[d] = round(max(vals) - min(vals), 2) if len(vals) >= 2 else 0.0
        return {"persona_avg": persona_avg, "max_gaps": gaps}

    def _print_persona_summary(self, results, fairness):
        self._log(f"\n{'='*60}\n📊 画像维度均分")
        for pid, avg in fairness["persona_avg"].items():
            name = PERSONAS.get(pid, {}).get("name", pid)
            self._log(f"  {pid} {name}: overall={avg.get('overall')} "
                      f"correct={avg.get('correctness')} guide={avg.get('guidance')} "
                      f"overhelp={avg.get('overhelping')} boundary={avg.get('boundary_compliance')}")
        self._log("\n⚖️ 画像间最大差距 (>1.0 提示潜在偏见):")
        for d, g in fairness["max_gaps"].items():
            flag = " ⚠️偏见" if g > 1.0 else ""
            self._log(f"  {d}: {g}{flag}")


def main():
    ap = argparse.ArgumentParser(description="多画像学生测评执行器")
    ap.add_argument("--mode", choices=["smoke", "standard", "deep", "custom"], default="smoke")
    ap.add_argument("--personas", default="", help="逗号分隔画像ID (custom模式)")
    ap.add_argument("--lessons", default="", help="逗号分隔课时ID (custom模式)")
    ap.add_argument("--turns", type=int, default=7, help="每课时最大对话轮次")
    ap.add_argument("--interval", type=float, default=4.0, help="chat 节流间隔秒")
    ap.add_argument("--dynamic", dest="dynamic", action="store_true", default=True,
                    help="LLM动态生成问题 (默认)")
    ap.add_argument("--static", dest="dynamic", action="store_false",
                    help="使用写死问题 (对照/调试)")
    ap.add_argument("--web", dest="web", action="store_true", default=True,
                    help="附带网站Playwright测评并合并报告 (默认)")
    ap.add_argument("--no-web", dest="web", action="store_false",
                    help="仅对话测评, 不测网站")
    ap.add_argument("--record", dest="record", action="store_true", default=True,
                    help="测评过程入库 DB (默认; 不可达则跳过)")
    ap.add_argument("--no-record", dest="record", action="store_false",
                    help="不写数据库")
    args = ap.parse_args()

    tester = PersonaTester(max_turns=args.turns, dynamic=args.dynamic, web=args.web,
                           record=args.record,
                           config={**PersonaTester._default_config(),
                                   "chat_min_interval": args.interval})
    started = datetime.now()
    print(f"🧪 问题生成模式: {'动态LLM(30%规则+70%LLM)' if args.dynamic else '写死回退'} | 网站测评: {'开' if args.web else '关'} | 入库: {'开' if args.record else '关'}")

    if args.mode == "smoke":
        res = tester.run_conversation("P1", 4)
        tester.finalize([res], mode="smoke")
    elif args.mode == "standard":
        tester.run_standard_eval()
    elif args.mode == "deep":
        tester.run_deep_eval()
    else:
        pids = [p.strip() for p in args.personas.split(",") if p.strip()] or STANDARD_PERSONAS
        lids = [int(x) for x in args.lessons.split(",") if x.strip()] or STANDARD_LESSONS
        out = tester.run_matrix(pids, lids)
        tester.finalize(out, mode="custom")

    print(f"\n⏱️ 总耗时 {(datetime.now() - started).total_seconds():.0f}s")


if __name__ == "__main__":
    main()
