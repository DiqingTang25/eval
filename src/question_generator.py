"""
问题生成器

基于课程大纲用 LLM 生成测试问题 + 黄金答案。
支持本地大纲 + 火山引擎知识库。
"""

import os
import json
import random
from openai import OpenAI


class QuestionGenerator:
    """基于课程大纲生成测试问题 + 黄金答案"""

    def __init__(self, api_key, syllabus_path="data/course_syllabus.txt",
                 base_url="https://api.deepseek.com/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.syllabus = ""
        try:
            with open(syllabus_path, "r", encoding="utf-8") as f:
                self.syllabus = f.read()
        except FileNotFoundError:
            print(f"  ⚠️ syllabus文件不存在: {syllabus_path}, 将使用内置大纲生成问题")
        self.question_types = ["概念解释", "操作步骤", "对比分析", "应用场景"]
        self.phases = ["PHASE 01", "PHASE 02", "PHASE 03", "PHASE 04", "PHASE 05"]

    def generate_one(self, phase=None, q_type=None):
        """生成一个问题 + 黄金答案"""
        if phase is None:
            phase = random.choice(self.phases)
        if q_type is None:
            q_type = random.choice(self.question_types)

        phase_names = {
            "PHASE 01": "国产AI技术基础（大模型部署、HiAgent平台、Prompt工程、ESP32-S3硬件嵌入、云边协同、3D建模）",
            "PHASE 02": "新型硬件设计（3D打印、激光雕刻、CNC加工、Arduino编程、AI辅助制造）",
            "PHASE 03": "环境感知（多维传感器、摄像头识别、Edge Impulse训练、音频识别、嵌入式部署）",
            "PHASE 04": "触觉反馈集成（屏幕交互、灯带/电机/舵机控制、AI标签联动、多模态反馈）",
            "PHASE 05": "具身智能控制（M5Stack生态、StackChan机器人、传感器融合、项目路演）",
        }

        prompt = f"""
你是一个课程评测专家。请基于以下课程大纲，生成一个问题及其标准答案。

【课程大纲】
{self.syllabus[:2000]}

【生成规则】
1. 问题必须涉及阶段 {phase} — {phase_names.get(phase, phase)} 中的至少一个知识点。
2. 问题类型必须是：{q_type}。
3. 问题难度设为"中等"。
4. 答案必须准确、完整，严格基于课程大纲，不要编造信息。
5. 输出JSON格式。

输出JSON：
{{
    "phase": "{phase}",
    "type": "{q_type}",
    "difficulty": "中等",
    "question": "问题内容",
    "golden_answer": "标准答案内容"
}}

只输出JSON。
"""
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        result.setdefault("phase", phase)
        result.setdefault("type", q_type)
        return result

    def generate_batch(self, count=10):
        """批量生成问题"""
        return [self.generate_one() for _ in range(count)]
