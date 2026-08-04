import json
from openai import OpenAI

class ReportGenerator:
    def __init__(self, api_key, base_url="https://api.deepseek.com/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, summary, details, question_data, conversation_log=None):
        """
        根据评测结果生成可读分析报告
        :param summary: 汇总统计（含各维度平均分）
        :param details: 详细结果列表
        :param question_data: 原始问题数据
        :param conversation_log: 对话日志（可选，用于精准分析）
        """
        scores = summary.get("avg_scores", {})
        total = summary.get("total", 1)

        # 提取关键分数
        correctness = scores.get("correctness", 0)
        relevancy = scores.get("relevancy", 0)
        completeness = scores.get("completeness", 0)
        guidance = scores.get("guidance", 0)
        followup = scores.get("followup_quality", 0)
        overall = scores.get("overall", 0)

        # 构建分析Prompt
        prompt = f"""
你是一位专业的AI教学Agent评测专家。请根据以下评测数据，生成一份给产品团队和开发团队阅读的分析报告。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【评测数据】
- 测试场景数：{total}
- 整体综合得分：{overall} / 5.0

各维度平均分（满分5分）：
- 事实正确性 (correctness)：{correctness}
- 答案相关性 (relevancy)：{relevancy}
- 内容完整性 (completeness)：{completeness}
- 教学引导能力 (guidance)：{guidance}
- 追问响应质量 (followup_quality)：{followup}

【原始问题】
{question_data.get('question', '未知')}

【参考黄金答案】
{question_data.get('golden_answer', '未知')}

【对话日志（如有）】
{conversation_log[:1500] if conversation_log else "（无详细日志）"}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请按以下格式输出分析报告（Markdown格式）：

## 📊 总体评价
（用1-2句话总结Agent的整体表现，定性描述）

## 📈 分维度解读

### 1. 事实正确性（{correctness}/5）
- 现状描述：（具体说明得分对应的表现）
- 问题表现：（如果低分，指出具体问题）

### 2. 答案相关性（{relevancy}/5）
- 现状描述：
- 问题表现：

### 3. 内容完整性（{completeness}/5）
- 现状描述：
- 问题表现：

### 4. 教学引导能力（{guidance}/5）
- 现状描述：
- 问题表现：

### 5. 追问响应质量（{followup}/5）
- 现状描述：
- 问题表现：

## 🎯 改进建议（按优先级排序）

### 🔴 P0（紧急修复）
（列出必须立即修复的问题，每个问题说明修复方向）

### 🟡 P1（重要优化）
（列出需要优化的问题）

### 🟢 P2（长期改进）
（列出可长期改进的方向）

## ✅ 下一步行动
（给出1-2条最直接、可执行的下一步建议）

只输出上述Markdown格式的报告，不要额外内容。
"""
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        return response.choices[0].message.content