"""
SLA 性能规则 (Service Level Agreement Rules)

对齐:
  - CLEAR Latency: SLA Compliance Rate 的确定性基底
  - EduAgentBench R_t: Turn-level 的响应延迟/轮次效率评估
  - TEACH-AI System Usability: 交互效率的量化度量

评估 Agent 的响应时间、轮次效率、追问恰当性。
全确定性计算, 0 API 调用, <1ms 延迟。
"""

from dataclasses import dataclass, field


@dataclass
class SLAResult:
    """SLA 检查结果"""
    score: float = 0.0               # 0-5 综合分
    latency_score: float = 0.0       # 响应延迟分
    turn_efficiency_score: float = 0.0  # 轮次效率分
    success_rate_score: float = 0.0  # 成功率分
    avg_latency_ms: float = 0.0      # 平均响应延迟
    p95_latency_ms: float = 0.0      # P95 响应延迟
    total_turns: int = 0
    successful_turns: int = 0
    evidence: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


class SLARules:
    """
    SLA 性能确定性检查器

    从对话轮次中计算:
      1. 响应延迟评分 (P50/P95)
      2. 轮次效率评分 (越少轮次越高效)
      3. 成功率评分

    使用方式:
        checker = SLARules()
        result = checker.check(turns=[...])
    """

    # ── 延迟阈值 (ms) ──
    LATENCY_EXCELLENT = 3_000     # <3s: 5分
    LATENCY_GOOD = 5_000          # <5s: 4分
    LATENCY_ACCEPTABLE = 10_000   # <10s: 3分
    LATENCY_SLOW = 20_000         # <20s: 2分
    LATENCY_UNACCEPTABLE = 30_000 # >30s: 1分

    # ── 轮次效率 ──
    IDEAL_MAX_TURNS = 1           # 1轮理想
    GOOD_MAX_TURNS = 3            # 2-3轮合理
    ACCEPTABLE_MAX_TURNS = 5      # 4-5轮可接受

    def __init__(
        self,
        latency_excellent: int = 3_000,
        latency_good: int = 5_000,
        latency_acceptable: int = 10_000,
    ):
        self.latency_excellent = latency_excellent
        self.latency_good = latency_good
        self.latency_acceptable = latency_acceptable

    def check(
        self,
        turns: list[dict] = None,
    ) -> SLAResult:
        """
        执行 SLA 检查

        :param turns: 对话轮次列表 [{"turn": 1, "response": {"duration": 2.5, "status": "success"}, ...}, ...]
        :return: SLAResult
        """
        evidence: list[str] = []
        flags: list[str] = []

        turns = turns or []

        if not turns:
            return SLAResult(
                score=3.0,
                evidence=["无对话轮次数据，SLA检查返回默认分"],
                flags=["NO_TURN_DATA"],
            )

        # ── 1. 提取数据 ──
        latencies: list[float] = []
        success_count = 0
        for t in turns:
            resp = t.get("response", {})
            if isinstance(resp, dict):
                dur = resp.get("duration", resp.get("response_duration", 0))
                if dur and dur > 0:
                    latencies.append(float(dur))
                if resp.get("status", "") == "success":
                    success_count += 1

        total_turns = len(turns)

        if not latencies:
            return SLAResult(
                score=3.0,
                total_turns=total_turns,
                successful_turns=success_count,
                evidence=["无延迟数据，SLA延迟检查跳过"],
                flags=["NO_LATENCY_DATA"],
            )

        # ── 2. 延迟评分 ──
        avg_latency = sum(latencies) / len(latencies)
        sorted_lat = sorted(latencies)
        p95_idx = int(len(sorted_lat) * 0.95)
        p95_latency = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]

        # 用平均延迟评分 (以秒为单位方便阅读)
        avg_sec = avg_latency
        if avg_sec <= self.latency_excellent:
            latency_score = 5.0
        elif avg_sec <= self.latency_good:
            latency_score = 4.0
        elif avg_sec <= self.latency_acceptable:
            latency_score = 3.0
        elif avg_sec <= self.LATENCY_SLOW:
            latency_score = 2.0
        else:
            latency_score = 1.0

        evidence.append(
            f"响应延迟: 平均={avg_sec:.0f}ms P95={p95_latency:.0f}ms → 延迟分={latency_score:.1f}"
        )

        if avg_sec > self.latency_acceptable:
            flags.append(f"SLA_LATENCY:平均延迟{avg_sec:.0f}ms超阈值{self.latency_acceptable}ms")

        # ── 3. 轮次效率评分 ──
        if total_turns <= self.IDEAL_MAX_TURNS:
            turn_score = 5.0
        elif total_turns <= self.GOOD_MAX_TURNS:
            turn_score = 4.0
        elif total_turns <= self.ACCEPTABLE_MAX_TURNS:
            turn_score = 3.0
        elif total_turns <= 8:
            turn_score = 2.0
        else:
            turn_score = 1.0

        evidence.append(
            f"轮次效率: {total_turns}轮 (成功{success_count}轮) → 效率分={turn_score:.1f}"
        )

        if total_turns > self.ACCEPTABLE_MAX_TURNS:
            flags.append(f"SLA_TURNS:轮次{total_turns}超阈值{self.ACCEPTABLE_MAX_TURNS}")

        # ── 4. 成功率评分 ──
        success_rate = success_count / total_turns if total_turns > 0 else 0.0
        if success_rate >= 0.95:
            success_score = 5.0
        elif success_rate >= 0.8:
            success_score = 4.0
        elif success_rate >= 0.6:
            success_score = 3.0
        elif success_rate >= 0.4:
            success_score = 2.0
        else:
            success_score = 1.0

        evidence.append(
            f"成功率: {success_count}/{total_turns} ({success_rate:.0%}) → 成功率分={success_score:.1f}"
        )

        if success_rate < 0.6:
            flags.append(f"SLA_SUCCESS_RATE:成功率仅{success_rate:.0%}")

        # ── 综合评分 ──
        composite = latency_score * 0.35 + turn_score * 0.35 + success_score * 0.30

        return SLAResult(
            score=round(min(5.0, composite), 1),
            latency_score=round(latency_score, 1),
            turn_efficiency_score=round(turn_score, 1),
            success_rate_score=round(success_score, 1),
            avg_latency_ms=round(avg_latency, 1),
            p95_latency_ms=round(p95_latency, 1),
            total_turns=total_turns,
            successful_turns=success_count,
            evidence=evidence,
            flags=flags,
        )
