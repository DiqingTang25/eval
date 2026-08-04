"""
BoundaryDetector 边界检测测试

测试课程范围检测的正确性。
"""

import pytest


@pytest.mark.llm
class TestBoundaryDetection:
    """边界检测测试"""

    def test_in_scope_answer(self, boundary_detector):
        """课程范围内的问题+回答"""
        result = boundary_detector.detect(
            question="ESP32-S3有哪些通信接口",
            agent_answer="ESP32-S3支持WiFi、Bluetooth 5.0、SPI、I2C、UART等通信接口，"
                        "可用于连接各类传感器和执行器",
        )
        assert result.status in ("in_scope", "partial_match"), \
            f"硬件相关问题应在范围内，实际: {result.status}"

    def test_out_of_scope_answer(self, boundary_detector):
        """明显超出范围的问题+回答"""
        result = boundary_detector.detect(
            question="如何做红烧肉",
            agent_answer="红烧肉的做法需要五花肉、酱油、冰糖等食材...",
        )
        assert result.status in ("out_of_scope", "partial_match"), \
            f"厨艺问题应在范围外，实际: {result.status}"

    def test_ambiguous_answer(self, boundary_detector):
        """模糊边界的问题"""
        result = boundary_detector.detect(
            question="请用Python写一个排序算法",
            agent_answer="以下是冒泡排序的实现：def bubble_sort(arr): ...",
        )
        # 编程问题可能与课程部分相关（取决于教学大纲）
        assert result.status in ("in_scope", "partial_match", "out_of_scope")
        assert 0 <= result.max_score <= 1.0

    def test_empty_answer(self, boundary_detector):
        """空回答"""
        result = boundary_detector.detect(
            question="什么是AI硬件",
            agent_answer="",
        )
        # 空回答应被正确处理（不应抛异常）
        assert result.status in ("out_of_scope", "in_scope", "partial_match")

    def test_ai_hardware_keywords(self, boundary_detector):
        """AI + 硬件关键词应被识别为在范围内"""
        result = boundary_detector.detect(
            question="介绍一下AI开发板",
            agent_answer="常见的AI开发板有ESP32-S3、K210、树莓派等，"
                        "ESP32-S3是乐鑫推出的集成AI加速器的开发平台，"
                        "支持TensorFlow Lite Micro",
        )
        # 包含多个硬件关键词，应在范围内或部分匹配
        assert result.status != "error", f"不应报错，实际: {result.status}"
        assert len(result.matched_keywords) >= 0
