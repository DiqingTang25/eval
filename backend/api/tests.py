"""Tests API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.dependencies import get_db
from backend.models import TestSession, TestScenario, ConversationTurn, EvalScore
from backend.services.test_service import TestService

router = APIRouter()
test_service = TestService()


from pydantic import BaseModel

class MultiAgentRequest(BaseModel):
    """Multi-Agent 测试编排请求 (Agent C)"""
    strategy: str = "spot_check"       # full | spot_check | risk_driven
    phases: list[str] = []             # Phase ID 白名单 (空=全部)
    mode: str = "guided"
    headless: bool = True
    target_url: str = ""

class BrowserEvalRequest(BaseModel):
    """全平台浏览器遍历测评请求"""
    phases: list[int] = [1, 2, 3, 4, 5]
    mode: str = "guided"
    headless: bool = True
    include_quiz: bool = True
    target_url: str = ""
    agent_id: str = "platform"
    schema_driven: bool = False        # v4.0: 使用探索器发现的 schema
    platform_schema_path: str = ""     # v4.0: schema 文件路径


class TestRunRequest(BaseModel):
    agent_id: str = "platform"
    num_questions: int = 1
    max_turns: int = 3
    profile: str = "standard"
    target_url: str = ""
    schema_driven: bool = False        # v4.0
    platform_schema_path: str = ""     # v4.0


class InterventionRespondRequest(BaseModel):
    """卡点干预应答 — 评测线程 ask_user() 阻塞等待此应答"""
    session_id: str
    answer: str


@router.post("/run-multi-agent")
async def trigger_multi_agent(body: MultiAgentRequest = None):
    """启动 Multi-Agent 测试编排 (Agent C)

    Planner → Executor → Verifier → Reporter
    Schema 驱动, 三通道验证 (Text + Visual + API)
    """
    if body is None:
        body = MultiAgentRequest()
    return await test_service.start_multi_agent(
        strategy=body.strategy,
        phases=body.phases or None,
        mode=body.mode,
        headless=body.headless,
        target_url=body.target_url,
    )


@router.post("/run")
async def trigger_test(body: TestRunRequest = None):
    if body is None:
        body = TestRunRequest()
    """启动LLM问答测评"""
    return await test_service.start_run(
        agent_id=body.agent_id,
        num_questions=body.num_questions,
        max_turns=body.max_turns,
        profile=body.profile,
        target_url=body.target_url,
        schema_driven=body.schema_driven,
        platform_schema_path=body.platform_schema_path,
    )


@router.post("/run-browser")
async def trigger_browser_eval(body: BrowserEvalRequest = None):
    if body is None:
        body = BrowserEvalRequest()
    """启动全平台浏览器遍历测评 (Playwright真实模拟)

    覆盖: 登录 → 逐Phase → 逐Day → 帮帮我模式 → Step完成
          → Agent对话 → Quiz触发 → 答题验证 → 报告
    耗时: 全22 Days约18分钟, 巡检5 Days约5分钟
    """
    return await test_service.start_browser_eval(
        phases=body.phases,
        mode=body.mode,
        headless=body.headless,
        include_quiz=body.include_quiz,
        target_url=body.target_url,
    )


# ═══════════════════════════════════════════════════════════
# 卡点干预 (自动化为主, 卡点暴露询问用户)
# ═══════════════════════════════════════════════════════════

@router.post("/intervention/respond")
async def intervention_respond(body: InterventionRespondRequest):
    """回答评测线程提出的卡点问题 (登录失败/元素缺失/Schema缺失等)"""
    ok = test_service.respond_intervention(body.session_id, body.answer)
    return {
        "status": "ok" if ok else "timeout",
        "session_id": body.session_id,
        "message": "应答已接收" if ok else "该卡点问题已超时或不存在",
    }


@router.get("/intervention/pending")
async def intervention_pending():
    """当前待回答的卡点问题 (前端轮询兜底, WS 不可用时)"""
    pending = test_service.pending_intervention()
    if not pending:
        return {"pending": False}
    return {"pending": True, **pending}


@router.get("/intervention/history/{session_id}")
async def intervention_history(session_id: str):
    """某次评测会话的干预审计记录 (ask/answer/timeout 全链路)"""
    return {"history": test_service.intervention_history(session_id)}


@router.get("/metrics")
async def run_metrics():
    """运行指标 — 退出类型统计 (成功率/求助率/降级完成率)"""
    from src.run_metrics import summarize_runs
    return summarize_runs()


@router.get("/status")
async def test_status():
    """当前评测状态"""
    return {
        "running": test_service.is_running,
        "session_id": test_service.current_session_id,
    }


@router.post("/cancel")
async def cancel_test():
    """P0-15: 取消正在运行的评测"""
    return await test_service.cancel_run()


@router.get("/health")
async def test_health():
    """P0-15: 评测健康状态(Watchdog 心跳/超时检测)"""
    return await test_service.get_health()


@router.get("/sessions/{session_id}/logs")
async def get_session_logs(session_id: str, last_n: int = 500):
    """获取指定评测会话的事件日志 (历史回放)"""
    return TestService.get_logs(session_id, last_n)


@router.get("/sessions")
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """测试会话列表"""
    from sqlalchemy import func
    total_r = await db.execute(select(func.count(TestSession.id)))
    total = total_r.scalar() or 0

    sessions_r = await db.execute(
        select(TestSession)
        .order_by(desc(TestSession.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    sessions = sessions_r.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "session_id": s.session_id,
                "agent_id": s.agent_id,
                "profile": s.profile,
                "status": s.status,
                "total_scenarios": s.total_scenarios,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """获取测试会话详情 (eager loading, 1 + 2 次查询)"""
    ts_r = await db.execute(
        select(TestSession)
        .options(
            selectinload(TestSession.scenarios)
            .selectinload(TestScenario.turns),
            selectinload(TestSession.scenarios)
            .selectinload(TestScenario.scores),
        )
        .where(TestSession.session_id == session_id)
    )
    ts = ts_r.scalar_one_or_none()
    if not ts:
        raise HTTPException(404, "Session not found")

    scenario_details = []
    for sc in ts.scenarios:
        scenario_details.append({
            "id": str(sc.id),
            "scenario_index": sc.scenario_index,
            "status": sc.status,
            "error": sc.error,
            "full_conversation": sc.full_conversation,
            "turns": [
                {
                    "turn": t.turn,
                    "question": t.question,
                    "response_status": t.response_status,
                    "response_text": t.response_text,
                    "response_duration": t.response_duration,
                }
                for t in (sc.turns or [])
            ],
            "score": {
                "overall": sc.scores.overall,
                "correctness": sc.scores.correctness,
                "relevancy": sc.scores.relevancy,
                "completeness": sc.scores.completeness,
                "guidance": sc.scores.guidance,
                "followup_quality": sc.scores.followup_quality,
                "boundary_compliance": sc.scores.boundary_compliance,
                "turn_consistency": sc.scores.turn_consistency,
                "knowledge_scaffolding": sc.scores.knowledge_scaffolding,
                "boundary_status": sc.scores.boundary_status,
                "n_judges": sc.scores.n_judges,
                "judge_variance": sc.scores.judge_variance,
                "flags": sc.scores.flags,
                "needs_human_review": sc.scores.needs_human_review,
            } if sc.scores else None,
        })

    return {
        "id": str(ts.id),
        "session_id": ts.session_id,
        "agent_id": ts.agent_id,
        "profile": ts.profile,
        "status": ts.status,
        "total_scenarios": ts.total_scenarios,
        "started_at": ts.started_at.isoformat() if ts.started_at else None,
        "finished_at": ts.finished_at.isoformat() if ts.finished_at else None,
        "scenarios": scenario_details,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """删除测试会话"""
    ts_r = await db.execute(
        select(TestSession).where(TestSession.session_id == session_id)
    )
    ts = ts_r.scalar_one_or_none()
    if not ts:
        raise HTTPException(404, "Session not found")
    await db.delete(ts)
    await db.commit()
    return {"ok": True, "session_id": session_id}


@router.delete("/sessions")
async def delete_all_sessions(db: AsyncSession = Depends(get_db)):
    """删除全部测试会话 (含关联 scenarios, turns, scores, traces, reports)"""
    from sqlalchemy import delete as sa_delete

    # 先统计
    count_r = await db.execute(select(TestSession.id))
    total = len(count_r.scalars().all())

    # CASCADE 删除: sessions → scenarios → turns/scores/traces + reports
    await db.execute(sa_delete(TestSession))
    await db.commit()

    return {"ok": True, "deleted": total, "message": f"已删除 {total} 条测试会话及所有关联数据"}
