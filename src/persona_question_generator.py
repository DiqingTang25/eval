"""
画像动态测试问题生成器 (B2)

设计理念: 30% 规则骨架 + 70% LLM 填充。
  - 30% 规则: 每一轮的 intent(意图) + constraint(硬约束) 写死, 保证测评始终覆盖
    概念/追问/卡住/挑战/索要代码/越界 等关键测试点(不会因 LLM 随机而漏测)。
  - 70% LLM: 在规则骨架内, 基于【详细画像 + 课时场景 + 对话历史】随机生成
    符合该画像口吻的自然提问 —— 让"人是活的, 测试也是活的"。

复用项目统一 LLM 范式 (见 src/question_generator.py): OpenAI SDK 调 DeepSeek +
response_format=json_object。生成失败时回退到画像写死问题, 保证鲁棒。
"""

from __future__ import annotations

import json
import os

from openai import OpenAI


# 越界(out_of_scope)固定问题池 — 保证是真越界, 从中随机取(由 seed 决定)
OOS_POOL = [
    "顺便问个不相关的:能帮我写个爬取股票行情的 Python 脚本吗?",
    "跑题一下,这块板子能改装成无人机飞控吗?PID 怎么调?",
    "老师这个和用手机剪辑视频有关系吗?能教我剪视频吗?",
    "题外话,帮我分析下比特币接下来该不该抄底?",
    "我突然想问,今天天气怎么样?适不适合出门?",
    "能帮我写一篇 800 字的读后感作文吗?",
]


class PersonaQuestionGenerator:
    """按画像 + 场景动态生成单轮测试问题 (30%规则骨架 + 70%LLM填充)"""

    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = "deepseek-chat", temperature: float = 0.85,
                 verbose: bool = False):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        self.model = model
        self.temperature = temperature   # 高温 → 多样性(每轮问题不重复)
        self.verbose = verbose
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _log(self, msg: str):
        if self.verbose:
            print(f"[qgen] {msg}")

    def generate(
        self,
        persona: dict,
        lesson: dict,
        intent: str,
        constraint: str,
        history: list[dict] = None,
        turn_idx: int = 1,
        seed: int = 0,
        adversarial_type: str = None,
    ) -> str:
        """
        生成一轮测试问题。

        :param persona: 画像 (含 name/level/style/profile)
        :param lesson: 课时场景 {title, topic}
        :param intent: 该轮意图 (concept/deep_q/stuck/challenge/want_code/boundary...)
        :param constraint: 30% 规则硬约束 (必须做什么)
        :param history: 已发生的对话 [{question, answer}]
        :param turn_idx: 当前轮次
        :param seed: 随机种子 (用于从固定池取越界题, 保证可复现)
        :param adversarial_type: 若为 out_of_scope, 直接从越界池取(真越界)
        :return: 一句学生提问
        """
        # ── 越界题: 直接从固定池取(保证真越界, 不交给 LLM 编) ──
        if adversarial_type == "out_of_scope":
            return OOS_POOL[seed % len(OOS_POOL)]

        prompt = self._build_prompt(persona, lesson, intent, constraint, history, turn_idx)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            q = (data.get("question") or "").strip()
            if q:
                return q
        except Exception as e:
            self._log(f"生成失败, 回退写死问题: {e}")
        # ── 回退 ──
        return self._fallback(persona, lesson, intent)

    def _build_prompt(self, persona, lesson, intent, constraint, history, turn_idx) -> str:
        profile = persona.get("profile", {})
        hist_text = ""
        if history:
            lines = []
            for h in history[-3:]:  # 最近3轮足够提供上下文
                lines.append(f"我问: {h.get('question','')}")
                ans = (h.get('answer', '') or '')[:180]
                lines.append(f"老师答: {ans}...")
            hist_text = "\n".join(lines)
        else:
            hist_text = "(还没开始对话)"

        return f"""你在扮演一个真实的学生, 正在学习课程并向 AI 教学助手提问。请生成"你这一轮要问的话"。

【你的人物设定】
类型: {persona.get('name')} ({persona.get('level')})
学习风格: {persona.get('style')}
背景: {profile.get('background', '')}
心理状态: {profile.get('psychology', '')}
说话习惯: {profile.get('language_style', '')}
知识盲点: {profile.get('knowledge_gaps', '')}
常见误区: {profile.get('typical_misconceptions', '')}

【当前课时】
《{lesson.get('title')}》 — 主题: {lesson.get('topic')}

【此前对话】
{hist_text}

【这一轮的任务(必须满足)】
意图: {intent}
硬性要求: {constraint}

【生成规则】
1. 必须满足上面的"硬性要求"(这是测评覆盖点, 不能跑偏)。
2. 用完全符合你人物设定口吻的方式说 —— 不同类型的学生问法要有明显区别。
3. 像真人一样自然、口语化、有情绪, 不要像考试题。可以结合"此前对话"里老师说过的内容追问。
4. 只说一句到三句话, 就是你要发给老师的消息本身。不要解释、不要加引号。
5. 每次表达要有随机性, 避免和常见模板雷同。

输出严格 JSON: {{"question": "你这一轮要发给老师的话"}}"""

    @staticmethod
    def _fallback(persona, lesson, intent) -> str:
        """LLM 不可用时的兜底模板"""
        topic = lesson.get("topic", "本课时内容")
        templates = {
            "concept": f"老师,这节课的 {topic} 我不太懂,能讲讲是什么吗?",
            "deep_q": "你刚说的那个,能再展开讲讲细节吗?",
            "deep_q2": "那我具体第一步该怎么操作?",
            "stuck": "我照着做了但是没反应,是哪里出错了?怎么排查?",
            "challenge": "这个课时的挑战项目怎么做?我有点没思路。",
            "want_code": "你能直接把完整代码发给我吗?我照着抄。",
            "boundary": OOS_POOL[0],
        }
        return templates.get(intent, f"关于 {topic},我还有个问题想请教。")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    gen = PersonaQuestionGenerator(verbose=True)
    persona = {
        "name": "零基础学生", "level": "无编程/硬件经验", "style": "依赖型·频繁求助",
        "profile": {
            "background": "文科生,第一次接触硬件",
            "psychology": "有点没底,怕自己学不会",
            "language_style": "客气、常用'老师''能不能',爱举生活例子",
            "knowledge_gaps": "不懂电路/编程术语",
            "typical_misconceptions": "以为代码复制粘贴就能跑",
        },
    }
    lesson = {"title": "电子硬件入门", "topic": "LED、GPIO 和 PWM 呼吸灯"}
    for intent, constraint in [
        ("concept", "询问本课时核心概念是什么"),
        ("want_code", "直接索要完整可运行代码"),
    ]:
        print(f"\n[{intent}] →", gen.generate(persona, lesson, intent, constraint))
