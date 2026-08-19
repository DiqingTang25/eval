"""冒烟测试 — 对话式探索器状态机 + 评测卡点干预机制 (无浏览器/无网络依赖)

运行: ~/.venvs/agent_eval/bin/python tests/smoke_chat_intervention.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class FakeExplorerSvc:
    """模拟 ExplorerService — 只验证状态机流转, 不真正启动探索"""

    def __init__(self):
        self.started = []

    async def start_explore(self, **kw):
        self.started.append(kw)
        return {"status": "started", "session_id": "smoke_test_session"}

    async def get_status(self):
        return {"running": False}

    async def cancel_explore(self):
        return {"message": "探索已取消。"}


async def test_chat_flow():
    from backend.services.explorer_chat import ExplorerChatService

    fake = FakeExplorerSvc()
    svc = ExplorerChatService(explorer_service=fake)

    # 禁用 LLM (冒烟不依赖外部 API key)
    svc._call_llm = lambda chat: None

    # 1. 开局: 缺 URL
    r = svc.start_chat()
    assert r["missing_fields"] == ["target_url"], r

    # 2. 给 URL → 追问凭证
    cid = r["chat_id"]
    r = await svc.handle_message(cid, "探索 https://example.edu 深度 2")
    assert r["missing_fields"] == ["credentials"], r

    # 3. 给凭证 → 展示计划 (confirm)
    r = await svc.handle_message(cid, "账号 111 密码 123456")
    assert r["status"] == "confirm", r

    # 4. 开始 → 启动 (复用 FakeSvc)
    r = await svc.handle_message(cid, "开始")
    assert r["action"] == "started", r
    assert fake.started and fake.started[0]["target_url"] == "https://example.edu"

    # 5. 运行中取消
    r = await svc.handle_message(cid, "取消")
    assert r["action"] == "cancelled", r

    # 6. 表单预填 + 免登录路径
    svc2 = ExplorerChatService(explorer_service=fake)
    svc2._call_llm = lambda chat: None
    r = svc2.start_chat({"target_url": "https://open.example.org"})
    cid2 = r["chat_id"]
    r = await svc2.handle_message(cid2, "无需登录")
    assert r["status"] == "confirm", r
    r = await svc2.handle_message(cid2, "go")
    assert r["action"] == "started", r
    assert fake.started[-1]["username"] == ""

    # 7. 过期会话
    r = await svc.handle_message("nonexistent_id", "你好")
    assert r["status"] == "expired", r
    print("✅ chat 状态机冒烟 7 项 PASS")


def test_question_bridge():
    import threading
    import time
    from src.question_bridge import QuestionBridge

    # 1. 超时路径
    b = QuestionBridge(enabled=True)
    r = b.ask("需要验证码吗?", options=["跳过"], timeout_s=0.2)
    assert r["timed_out"] and r["skipped"], r

    # 2. 应答路径
    b2 = QuestionBridge(enabled=True)
    result = {}

    def _worker():
        result["r"] = b2.ask("登录页提示验证码, 请提供", options=["跳过登录"], timeout_s=5)

    t = threading.Thread(target=_worker)
    t.start()
    for _ in range(50):
        if b2.current_question():
            break
        time.sleep(0.05)
    assert b2.current_question() is not None, "问题未进入 pending"
    assert b2.answer_any("123456") is True
    t.join(timeout=3)
    assert not t.is_alive(), "ask 未唤醒"
    assert result["r"]["answer"] == "123456" and not result["r"]["timed_out"]

    # 3. disabled 保底
    b3 = QuestionBridge(enabled=False)
    r = b3.ask("需要帮助吗?", timeout_s=0.2)
    assert r["auto_disabled"], r
    print("✅ QuestionBridge 冒烟 3 项 PASS")


async def test_intervention_flow():
    """TestService.ask_user 超时默认 + 应答唤醒 (WS 无 main_loop 时自动跳过广播)"""
    import time
    from backend.services.test_service import TestService

    # TestService.__init__ 不连 DB/WS, 可安全实例化; 冒烟不设 _main_loop → 广播自动跳过
    svc = TestService()

    # 超时默认路径 (0.3s)
    r = svc.ask_user(
        session_id="smoke", question="登录失败, 要重试吗?",
        options=["重试", "终止"], timeout_s=0.3, default="重试",
    )
    assert r == "重试", r

    # 应答路径 (后台线程阻塞, 主线程 respond)
    import threading

    result = {}
    def _ask():
        result["r"] = svc.ask_user(
            session_id="smoke2", question="需要新凭证?",
            options=["提供", "终止"], timeout_s=5, default="终止",
        )
    t = threading.Thread(target=_ask)
    t.start()
    time.sleep(0.3)
    pend = svc.pending_intervention()
    assert pend is not None and pend["question"].startswith("需要新凭证"), pend
    assert svc.respond_intervention("smoke2", "提供") is True
    t.join(timeout=3)
    assert result["r"] == "提供", result
    # 迟到应答拒绝 (问题已被消费)
    assert svc.respond_intervention("smoke2", "再来一次") is False
    # 无 pending 时返回 None
    assert svc.pending_intervention() is None
    print("✅ 干预机制冒烟 3 项 PASS")


if __name__ == "__main__":
    asyncio.run(test_chat_flow())
    test_question_bridge()
    asyncio.run(test_intervention_flow())
    print("\n全部冒烟 PASS ✅")
