"""
Mock Agent — 测评管线验证

返回预设回答，不依赖任何外部服务。
用于验证三层级联评测架构全流程。
"""

import time
from .base import BaseAgent, AgentResponse, AgentStatus


class MockAgent(BaseAgent):
    """返回黄金答案的模拟Agent — 验证管线用"""

    def __init__(self, name: str = "mock", config: dict = None):
        super().__init__(name, config)
        self._responses = config.get("responses", []) if config else []

    def start(self) -> bool:
        print("[MockAgent] ✅ 就绪 (无外部依赖)")
        return True

    def send_message(self, text: str, timeout: int = 180) -> AgentResponse:
        """返回模拟回答 — 根据问题内容生成较相关的回答"""
        time.sleep(0.1)
        turn = len(self._conversation_history) + 1

        if turn <= len(self._responses):
            answer = self._responses[turn - 1]
        else:
            answer = self._smart_answer(text, turn)

        response = AgentResponse(
            status=AgentStatus.SUCCESS,
            text=answer,
            duration_seconds=0.5,
            turn=turn,
            metadata={"mock": True},
        )
        self._conversation_history.append(response)
        return response

    def _smart_answer(self, question: str, turn: int) -> str:
        """根据问题关键词生成较相关的模拟回答"""
        q = question.lower()

        # 3D打印相关
        if any(kw in q for kw in ['3d打印', '增材制造', 'blender', '建模']):
            return (
                "## 3D打印与增材制造\n\n"
                "3D打印是增材制造的核心技术，课程中使用Blender进行3D建模。\n\n"
                "主要步骤:\n"
                "1. 使用Blender或SolidWorks进行3D建模\n"
                "2. 导出STL格式文件\n"
                "3. 使用切片软件（如Cura）生成G-code\n"
                "4. 在3D打印机上完成物理成型\n\n"
                "AI可以通过优化支撑结构、减少材料用量来提升打印效率。"
            )

        # ESP32/嵌入式相关
        if any(kw in q for kw in ['esp32', 'adc', '传感器', '嵌入式', 'arduino']):
            return (
                "## ESP32-S3 嵌入式开发\n\n"
                "ESP32-S3搭载12位SAR型ADC，分辨率0-4095，采样率最高200ksps。\n\n"
                "开发流程:\n"
                "1. 搭建Arduino IDE或PlatformIO开发环境\n"
                "2. 使用AI协作生成GPIO控制代码\n"
                "3. 通过ADC读取传感器数据\n"
                "4. 将数据通过MQTT协议上传至云端\n\n"
                "ESP32-S3支持WiFi+BLE双模通信，适合云边协同场景。"
            )

        # HiAgent/AI平台相关
        if any(kw in q for kw in ['千帆', 'hiagent', 'agent', '大模型', 'prompt', '提示词']):
            return (
                "## HiAgent平台开发\n\n"
                "HiAgent平台支持快速构建AI Agent应用。\n\n"
                "核心能力:\n"
                "- Prompt工程：设计精准的提示词引导模型输出\n"
                "- 知识库集成：上传课程资料构建专属知识库\n"
                "- API调用：通过REST API将Agent集成到应用中\n\n"
                "在课程中，我们使用HiAgent为学生提供智能问答服务。"
            )

        # 追问（第二轮以后）
        if turn > 1:
            return (
                "很好的追问！让我进一步解释。\n\n"
                "在实际项目中，上述技术需要结合课程的核心原则："
                "硬件'乐高化'（模块化套件，不涉及电路焊接）、"
                "AI'全能化'（代码由AI生成）、"
                "实验'拼图化'（模块化组合）。\n\n"
                "你可以先在开发板上验证单个模块功能，然后逐步集成。"
            )

        # 默认回答
        return (
            f"关于「{question[:50]}」这个问题，"
            f"根据课程内容，这涉及到国产智能硬件与AI应用开发的核心知识。"
            f"建议从基础概念入手，逐步深入理解。\n\n"
            f"课程涵盖5个阶段：AI技术基础、硬件设计、环境感知、触觉反馈、具身智能控制。"
        )

    def get_history(self) -> list[AgentResponse]:
        return self._conversation_history

    def close(self):
        self._conversation_history = []
