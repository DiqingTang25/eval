"""
Agent 抽象基类

所有被测 Agent 必须实现此接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    NOT_STARTED = "not_started"


@dataclass
class AgentResponse:
    """Agent 回复的统一数据结构"""
    status: AgentStatus
    text: str = ""
    duration_seconds: float = 0.0
    turn: int = 0
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """被测 Agent 抽象基类"""

    def __init__(self, name: str, config: dict = None):
        self.name = name
        self.config = config or {}
        self._conversation_history: list[AgentResponse] = []

    @abstractmethod
    def start(self) -> bool:
        """
        启动/连接 Agent

        :return: 是否成功连接
        """
        ...

    @abstractmethod
    def send_message(self, text: str, timeout: int = 180) -> AgentResponse:
        """
        发送消息并获取回复

        :param text: 消息文本
        :param timeout: 最大等待时间（秒）
        :return: Agent 回复
        """
        ...

    @abstractmethod
    def get_history(self) -> list[AgentResponse]:
        """获取对话历史"""
        ...

    @abstractmethod
    def close(self):
        """关闭连接，释放资源"""
        ...

    def is_ended(self, response: AgentResponse) -> bool:
        """
        检测对话是否应该结束

        子类可重写此方法，提供 Agent 特有的结束判断逻辑。
        """
        end_phrases = [
            "还有问题吗", "随时问我", "我讲清楚了吗",
            "还有什么可以帮你的", "可以开始尝试了",
            "祝你成功", "遇到问题随时找我", "你先试试看",
            "还有其他问题吗", "希望对你有所帮助",
        ]
        for phrase in end_phrases:
            if phrase in response.text:
                return True
        return False
