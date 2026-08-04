from openai import OpenAI

class FollowupGenerator:
    def __init__(self, api_key, base_url="https://api.deepseek.com/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_followup(self, original_question, agent_response, conversation_history):
        prompt = f"""
你是一个模拟学生，正在向教学助手请教问题。请根据对话历史，生成一个自然、合理的追问。

【原始问题】
{original_question}

【Agent的最新回答】
{agent_response[:500]}...

【完整对话历史】
{conversation_history}

【规则】
1. 追问必须基于Agent回答中提到的内容。
2. 追问要自然，像一个真实学生会说的话。
3. 如果Agent已完整回答所有要点，回复"无需追问"。

只输出追问内容。
"""
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()