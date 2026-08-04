"""
EvalTrace / KBRetrievalLog / JudgeDecision — 完整审计追踪

审计原则: 每个测试步骤都公开可追溯, 确保公平公正
  - eval_traces: L1/L2/L3 各层详细过程
  - kb_retrieval_logs: 每次KB检索的查询/结果
  - judge_decisions: 每个Judge的独立评分+理由
"""

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk


class EvalTrace(Base, TimestampMixin):
    """
    评测过程追踪 — 每个场景一条记录, 包含完整的 L1→L2→L3 过程

    L1 规则层: rule_scores, keywords_matched, structure_checks
    L2 算法层: embedding_score, kb_search_summary
    L3 LLM层: judge_count, judge_variance, judge_decisions (关联)
    最终融合: final_scores (30%L1 + 70%L3 加权)
    """
    __tablename__ = "eval_traces"

    id: Mapped[str] = uuid_pk()
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_scenarios.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="冗余, 方便按Session查询",
    )

    # ── 评测阶段标记 ──
    eval_status: Mapped[str] = mapped_column(
        String(16), default="pending",
        comment="pending | l1_done | l2_done | l3_done | completed | error",
    )
    eval_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")

    # ── L1 规则层详情 ──
    l1_structure_score: Mapped[float] = mapped_column(Float, nullable=True)
    l1_structure_details: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="长度/格式/语言/Markdown 检查结果")
    l1_fact_score: Mapped[float] = mapped_column(Float, nullable=True)
    l1_fact_details: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="关键词命中/数字匹配/否定方向")
    l1_sla_score: Mapped[float] = mapped_column(Float, nullable=True)
    l1_sla_details: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="延迟P50+P95/轮次效率/成功率")
    l1_safety_score: Mapped[float] = mapped_column(Float, nullable=True)
    l1_safety_details: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="PII/敏感话题拒绝/角色越界")
    l1_composite_score: Mapped[float] = mapped_column(Float, nullable=True,
        comment="L1 综合分 (30%权重基底)")
    l1_skip_dims: Mapped[list | None] = mapped_column(JSON, nullable=True,
        comment="L1高分跳过的维度列表")
    l1_veto_dims: Mapped[list | None] = mapped_column(JSON, nullable=True,
        comment="L1一票否决的维度列表")
    l1_duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # ── L2 算法层详情 ──
    l2_embedding_score: Mapped[float] = mapped_column(Float, nullable=True,
        comment="SentenceTransformer 语义相似度")
    l2_structure_coverage: Mapped[float] = mapped_column(Float, nullable=True,
        comment="结构化覆盖度")
    l2_boundary_kb_score: Mapped[float] = mapped_column(Float, nullable=True,
        comment="KB检索综合分数")
    l2_boundary_kb_backend: Mapped[str] = mapped_column(String(32), nullable=True,
        comment="hiagent_kb | volcano | dify | none")
    l2_keywords_matched: Mapped[list | None] = mapped_column(JSON, nullable=True)
    l2_keyword_hit_rate: Mapped[float] = mapped_column(Float, nullable=True)
    l2_duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # ── L3 LLM Judge 层摘要 ──
    l3_judge_count: Mapped[int] = mapped_column(Integer, default=0)
    l3_judge_models: Mapped[list | None] = mapped_column(JSON, nullable=True,
        comment="使用的Judge模型列表")
    l3_judge_variance: Mapped[float] = mapped_column(Float, nullable=True,
        comment="Judge间方差")
    l3_needs_human_review: Mapped[bool] = mapped_column(default=False,
        comment="方差过大需要人工复核")
    l3_duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # ── L3 Token 成本追踪 (migration 0003) ──
    l3_total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0,
        comment="所有 Judge 的 prompt token 总和")
    l3_total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0,
        comment="所有 Judge 的 completion token 总和")
    l3_total_cost: Mapped[float] = mapped_column(Float, default=0.0,
        comment="所有 Judge 调用的估算总成本 (USD)")

    # ── 最终8维度评分 (30%L1 + 70%L3) ──
    final_correctness: Mapped[float] = mapped_column(Float, nullable=True)
    final_relevancy: Mapped[float] = mapped_column(Float, nullable=True)
    final_completeness: Mapped[float] = mapped_column(Float, nullable=True)
    final_guidance: Mapped[float] = mapped_column(Float, nullable=True)
    final_followup_quality: Mapped[float] = mapped_column(Float, nullable=True)
    final_boundary_compliance: Mapped[float] = mapped_column(Float, nullable=True)
    final_turn_consistency: Mapped[float] = mapped_column(Float, nullable=True)
    final_knowledge_scaffolding: Mapped[float] = mapped_column(Float, nullable=True)
    final_overall: Mapped[float] = mapped_column(Float, nullable=True)

    # ── 原始数据 (完整可追溯) ──
    raw_agent_response: Mapped[str] = mapped_column(Text, default="",
        comment="Agent 原始回复全文")
    raw_question: Mapped[str] = mapped_column(Text, default="",
        comment="原始问题")
    raw_golden_answer: Mapped[str] = mapped_column(Text, default="",
        comment="标准答案")
    raw_l3_prompts: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="发送给LLM Judge的完整prompt")
    raw_l3_responses: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="LLM Judge的完整原始回复")

    # ── 可复现性标记 ──
    reproducible: Mapped[bool] = mapped_column(default=True,
        comment="是否可复现 (根据方差/错误判断)")
    trace_version: Mapped[str] = mapped_column(String(16), default="3.3",
        comment="评测架构版本号")

    # 关系
    scenario: Mapped["TestScenario"] = relationship(back_populates="eval_trace")
    judge_decisions: Mapped[list["JudgeDecision"]] = relationship(
        back_populates="eval_trace", cascade="all, delete-orphan"
    )
    kb_retrieval_logs: Mapped[list["KBRetrievalLog"]] = relationship(
        back_populates="eval_trace", cascade="all, delete-orphan"
    )


class KBRetrievalLog(Base, TimestampMixin):
    """
    KB 检索日志 — 每次知识库查询的可追溯记录

    记录: 哪个KB / 查询什么 / 返回什么 / 耗时多少
    用于验证边界检测的公平性
    """
    __tablename__ = "kb_retrieval_logs"

    id: Mapped[str] = uuid_pk()
    eval_trace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_traces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    phase: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="phase1 | phase2 | phase3_4 | phase5",
    )
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kb_name: Mapped[str] = mapped_column(String(256), default="")
    backend: Mapped[str] = mapped_column(String(32), default="volcano")

    # 查询信息
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    query_duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # 结果
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    top_score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    results_json: Mapped[dict | None] = mapped_column(JSON, nullable=True,
        comment="完整返回结果 (chunks+scores)")

    # 错误
    error_message: Mapped[str] = mapped_column(Text, default="")

    eval_trace: Mapped["EvalTrace"] = relationship(back_populates="kb_retrieval_logs")


class JudgeDecision(Base, TimestampMixin):
    """
    Judge 决策记录 — 每个LLM Judge的独立评分

    多Judge投票机制: 每个Judge独立打分, 最终取中位数
    此表记录每个Judge的完整评分过程, 确保透明可追溯
    """
    __tablename__ = "judge_decisions"

    id: Mapped[str] = uuid_pk()
    eval_trace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_traces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Judge 信息
    judge_index: Mapped[int] = mapped_column(Integer, nullable=False,
        comment="Judge编号 (1-based)")
    judge_model: Mapped[str] = mapped_column(String(64), nullable=False,
        comment="deepseek-chat | claude-sonnet-5 | gpt-4o")
    judge_provider: Mapped[str] = mapped_column(String(32), default="deepseek")

    # 8维度独立评分
    correctness: Mapped[float] = mapped_column(Float, nullable=True)
    relevancy: Mapped[float] = mapped_column(Float, nullable=True)
    completeness: Mapped[float] = mapped_column(Float, nullable=True)
    guidance: Mapped[float] = mapped_column(Float, nullable=True)
    followup_quality: Mapped[float] = mapped_column(Float, nullable=True)
    boundary_compliance: Mapped[float] = mapped_column(Float, nullable=True)
    turn_consistency: Mapped[float] = mapped_column(Float, nullable=True)
    knowledge_scaffolding: Mapped[float] = mapped_column(Float, nullable=True)
    overall: Mapped[float] = mapped_column(Float, nullable=True)

    # Judge 置信度
    confidence: Mapped[float] = mapped_column(Float, nullable=True,
        comment="Judge自报置信度 0-1")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # 完整推理过程
    reasoning: Mapped[str] = mapped_column(Text, default="",
        comment="Judge的完整评分理由 (中文)")
    raw_prompt: Mapped[str] = mapped_column(Text, default="",
        comment="发送给Judge的完整prompt")
    raw_response: Mapped[str] = mapped_column(Text, default="",
        comment="Judge的完整原始回复")

    # 质量标记
    is_outlier: Mapped[bool] = mapped_column(default=False,
        comment="是否为离群评分 (与其他Judge偏差>1.5σ)")
    excluded_from_final: Mapped[bool] = mapped_column(default=False,
        comment="是否被排除在最终分数计算之外")

    eval_trace: Mapped["EvalTrace"] = relationship(back_populates="judge_decisions")
