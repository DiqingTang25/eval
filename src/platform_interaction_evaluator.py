#!/usr/bin/env python3
"""
平台交互功能全量测评器 v2.0
═══════════════════════════════════════════════════════
测试平台所有可交互功能，生成平台健康度报告。

关键发现 (2026-07-16):
  - 平台使用 /phase3-api/ API前缀 (前端JS P0="/phase3-api")
  - /api/ 是兼容层，缺少Quiz/Agent/Profile等核心功能
  - /phase3-api/ 使用不同的JWT密钥，需用 /phase3-api/auth/login

当前状态 (12项功能):
  ✅ Quiz启动/提交 — 5 Phase均可用, 5-10题/Phase
  ✅ Agent对话 — 正常, 有conversation_id/message_id
  ✅ Step进度 — 正常
  ✅ Next Step — 正常 (done=True时触发Quiz)
  ✅ 学生画像 — 6维雷达图正常
  ✅ 知识搜索 — 正常
  ✅ 事件追踪 — 正常(需合法event_type)
  ✅ 资源下载 — 正常
  ⚠️ 证据上传 — API存在(422=需文件)
  ⚠️ Agent反馈 — 需真实message_id
  ⚠️ 学习模式 — 纯前端(数据完整)
  ⚠️ 视频播放 — 当前无视频

用法:
    python src/platform_interaction_evaluator.py              # 全量测试
    python src/platform_interaction_evaluator.py --phase 4    # 单Phase Quiz
    python src/platform_interaction_evaluator.py --quick      # 快速(只测P0)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_client import PlatformClient, DEFAULT_BASE_URL


# ── 功能定义 ──
FEATURE_DEFINITIONS = {
    "quiz_start": {
        "name": "Quiz启动", "category": "quiz",
        "api": "POST /phase3-api/quiz/start", "priority": "P0",
        "description": "完成最后Step后自动触发Quiz弹窗",
    },
    "quiz_submit": {
        "name": "Quiz提交", "category": "quiz",
        "api": "POST /phase3-api/quiz/submit", "priority": "P0",
        "description": "提交Quiz答案并获取分数",
    },
    "step_progress": {
        "name": "Step进度标记", "category": "step_nav",
        "api": "POST /phase3-api/steps/:id/progress", "priority": "P1",
        "description": "标记Step为已完成",
    },
    "next_step": {
        "name": "下一步导航", "category": "step_nav",
        "api": "POST /phase3-api/lessons/:id/next-step", "priority": "P1",
        "description": "获取下一Step, done时触发Quiz",
    },
    "agent_chat": {
        "name": "Agent对话", "category": "agent",
        "api": "POST /phase3-api/agent/chat", "priority": "P0",
        "description": "学生与Phase Agent实时对话",
    },
    "agent_resolve": {
        "name": "Agent反馈标记", "category": "agent",
        "api": "PATCH /phase3-api/agent/messages/:id/resolution", "priority": "P2",
        "description": "标记Agent回答已解决/未解决",
    },
    "evidence_upload": {
        "name": "证据文件上传", "category": "evidence",
        "api": "POST /phase3-api/steps/:id/evidence-files", "priority": "P2",
        "description": "上传Step的截图/照片证据",
    },
    "knowledge_search": {
        "name": "知识库搜索", "category": "knowledge",
        "api": "GET /phase3-api/knowledge/search", "priority": "P2",
        "description": "在知识库中搜索相关知识点",
    },
    "student_profile": {
        "name": "学生画像", "category": "profile",
        "api": "GET /phase3-api/profile/me", "priority": "P2",
        "description": "获取学生知识点画像(6维雷达图)",
    },
    "event_tracking": {
        "name": "事件追踪", "category": "analytics",
        "api": "POST /phase3-api/events", "priority": "P2",
        "description": "前端行为事件上报",
    },
    "resource_download": {
        "name": "资源下载", "category": "content",
        "api": "GET /resources", "priority": "P1",
        "description": "下载课时相关课件/资料文件",
    },
    "video_playback": {
        "name": "视频播放", "category": "content",
        "api": "视频资源", "priority": "P1",
        "description": "播放课时视频",
    },
    "learning_mode": {
        "name": "学习模式切换", "category": "learning",
        "api": "render_payload (guide/detailed/standard)", "priority": "P1",
        "description": "\"我自己来\" vs \"帮帮我\" 模式切换",
    },
}


class InteractionResult:
    """单个交互功能的测试结果"""

    def __init__(self, feature_key: str):
        self.feature_key = feature_key
        self.definition = FEATURE_DEFINITIONS.get(feature_key, {})
        self.status = "untested"
        self.http_status = None
        self.latency_ms = 0.0
        self.detail = ""
        self.extra = {}

    def to_dict(self) -> dict:
        d = {
            "feature_key": self.feature_key,
            "name": self.definition.get("name", self.feature_key),
            "category": self.definition.get("category", "unknown"),
            "api": self.definition.get("api", ""),
            "priority": self.definition.get("priority", "P2"),
            "status": self.status,
            "http_status": self.http_status,
            "latency_ms": round(self.latency_ms, 1),
            "detail": self.detail,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


class PlatformInteractionEvaluator:
    """平台交互功能全量测评器"""

    def __init__(self, base_url: str = None, verbose: bool = True):
        self.base_url = base_url or DEFAULT_BASE_URL
        self.verbose = verbose
        self.client = PlatformClient(base_url=self.base_url, verbose=False, timeout=15)
        self._test_lesson_id = 4
        self._test_lesson_last = 20

    def _log(self, msg: str):
        if self.verbose:
            print(f"  {msg}")

    def _timed(self, fn, *args, **kwargs):
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        elapsed = (time.monotonic() - t0) * 1000
        return result, elapsed

    # ═══════════════════════════════════════════════════════
    # 单项测试 (全部使用 /phase3-api/)
    # ═══════════════════════════════════════════════════════

    def test_quiz_start(self, lesson_id: int = None) -> InteractionResult:
        r = InteractionResult("quiz_start")
        lid = lesson_id or self._test_lesson_last
        try:
            result, elapsed = self._timed(self.client.quiz_start, lid)
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                questions = result.get("questions", [])
                r.status = "working"
                r.detail = f"L{lid} Quiz启动成功, {len(questions)}题"
                r.extra["question_count"] = len(questions)
                r.extra["quiz_session_id"] = result.get("quiz_session_id")
            else:
                r.status = "broken"
                r.detail = result.get("error", "未知错误")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_quiz_submit(self) -> InteractionResult:
        r = InteractionResult("quiz_submit")
        try:
            # 先启动Quiz获取session
            start = self.client.quiz_start(self._test_lesson_last)
            if not start.get("ok"):
                r.status = "broken"
                r.http_status = start.get("status_code", 0)
                r.detail = f"依赖quiz_start失败: {start.get('error','')[:80]}"
                return r
            session_id = start.get("quiz_session_id", "")
            questions = start.get("questions", [])
            if not questions:
                r.status = "degraded"
                r.detail = "Quiz启动成功但无题目"
                return r

            answers = []
            for q in questions:
                opts = q.get("options", [])
                if opts:
                    answers.append({
                        "question_id": q["question_id"],
                        "selected_answer": opts[0]["id"],
                    })

            result, elapsed = self._timed(self.client.quiz_submit, session_id, answers)
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                score = result.get("score", "?")
                r.status = "working"
                r.detail = f"Quiz提交成功, score={score}"
                r.extra["score"] = score
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_step_progress(self) -> InteractionResult:
        r = InteractionResult("step_progress")
        try:
            lesson = self.client.get_lesson(self._test_lesson_id)
            steps = lesson.get("steps", [])
            if not steps:
                r.status = "degraded"
                r.detail = "无Step可测试"
                return r
            result, elapsed = self._timed(self.client.step_progress, steps[0]["id"], "completed")
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                r.status = "working"
                r.detail = f"Step#{steps[0]['id']}标记成功"
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_next_step(self) -> InteractionResult:
        r = InteractionResult("next_step")
        try:
            lesson = self.client.get_lesson(self._test_lesson_id)
            steps = lesson.get("steps", [])
            if not steps:
                r.status = "degraded"
                r.detail = "无Step可测试"
                return r
            result, elapsed = self._timed(self.client.next_step, self._test_lesson_id, steps[0]["id"])
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                done = result.get("done", False)
                r.status = "working"
                r.detail = f"done={done}, has_next={result.get('step') is not None}"
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_agent_chat(self) -> InteractionResult:
        r = InteractionResult("agent_chat")
        try:
            chat_result, elapsed = self._timed(self.client.chat, self._test_lesson_id, "你好，请简介GPIO")
            r.latency_ms = elapsed
            if chat_result.is_usable:
                r.status = "working"
                r.http_status = 200
                r.detail = f"Agent回答正常, {len(chat_result.answer)}字符"
                r.extra["message_id"] = chat_result.message_id
            elif chat_result.rate_limited:
                r.status = "degraded"
                r.detail = "被限流(QPS)"
            else:
                r.status = "broken"
                r.detail = chat_result.error[:120] if chat_result.error else "未知错误"
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_agent_resolve(self) -> InteractionResult:
        r = InteractionResult("agent_resolve")
        try:
            # 先发一条消息获取message_id
            chat = self.client.chat(self._test_lesson_id, "测试消息")
            if not chat.is_usable or not chat.message_id:
                r.status = "degraded"
                r.detail = f"无法获取message_id (chat: {'ok' if chat.ok else chat.error[:50]})"
                return r
            result, elapsed = self._timed(self.client.agent_resolve, chat.message_id, True)
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                r.status = "working"
                r.detail = "Agent反馈标记成功"
            elif result.get("status_code") == 404:
                r.status = "degraded"
                r.detail = "API存在但message_id未找到(可能需要真实对话)"
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_evidence_upload(self) -> InteractionResult:
        r = InteractionResult("evidence_upload")
        try:
            import requests as req
            url = f"{self.base_url}/phase3-api/steps/1/evidence-files"
            hdrs = self.client._headers()
            resp, elapsed = self._timed(req.post, url, headers=hdrs, timeout=self.client.timeout)
            r.latency_ms = elapsed
            r.http_status = resp.status_code
            if resp.status_code == 422:
                r.status = "degraded"
                r.detail = "API存在(422=需multipart文件) — 端点已部署"
            elif resp.status_code in (200, 201):
                r.status = "working"
                r.detail = "证据上传成功"
            elif resp.status_code == 404:
                r.status = "broken"
                r.detail = "API未部署(404)"
            else:
                r.status = "broken"
                r.detail = f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_knowledge_search(self) -> InteractionResult:
        r = InteractionResult("knowledge_search")
        try:
            result, elapsed = self._timed(self.client.knowledge_search, "GPIO", 4)
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                chunks = result.get("chunks", [])
                r.status = "working"
                r.detail = f"搜索成功, {len(chunks)}条结果"
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_student_profile(self) -> InteractionResult:
        r = InteractionResult("student_profile")
        try:
            result, elapsed = self._timed(self.client.get_profile)
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                profile = result.get("profile", {})
                dims = profile.get("dimensions", [])
                r.status = "working"
                r.detail = f"画像获取成功, {len(dims)}维"
                r.extra["profile_level"] = profile.get("profile_level", "?")
                r.extra["dimensions"] = [d.get("name") for d in dims]
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_event_tracking(self) -> InteractionResult:
        r = InteractionResult("event_tracking")
        try:
            # 使用前端JS中定义的合法event_type
            result, elapsed = self._timed(
                self.client.track_event, "step_completed",
                {"lesson_id": 4, "step_block_id": 1}
            )
            r.latency_ms = elapsed
            r.http_status = result.get("status_code")
            if result.get("ok"):
                r.status = "working"
                r.detail = "事件上报成功"
            elif result.get("status_code") == 400:
                r.status = "degraded"
                r.detail = f"事件被拒绝(400): {result.get('error','')[:80]}"
            else:
                r.status = "broken"
                r.detail = result.get("error", "")[:120]
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_resource_download(self) -> InteractionResult:
        r = InteractionResult("resource_download")
        try:
            lesson = self.client.get_lesson(self._test_lesson_id)
            resources = lesson.get("resources", [])
            if not resources:
                r.status = "degraded"
                r.detail = "该课时无资源"
                return r
            first_res = resources[0]
            url = first_res.get("url", "")
            if not url:
                r.status = "degraded"
                r.detail = "资源URL为空"
                return r
            import requests as req
            full_url = url if url.startswith("http") else f"{self.base_url.rstrip('/')}{url if url.startswith('/') else '/' + url}"
            resp, elapsed = self._timed(req.head, full_url, timeout=10, allow_redirects=True)
            r.latency_ms = elapsed
            r.http_status = resp.status_code
            if resp.status_code < 400:
                r.status = "working"
                r.detail = f"资源可访问: {first_res.get('title','')[:30]}"
            else:
                r.status = "broken"
                r.detail = f"HTTP {resp.status_code}"
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_video_playback(self) -> InteractionResult:
        r = InteractionResult("video_playback")
        try:
            all_lessons = self.client.get_all_lessons()
            total_videos = 0
            for l in all_lessons[:5]:  # 抽样检查
                detail = self.client.get_lesson(l["id"])
                total_videos += len(detail.get("videos", []))
            if total_videos == 0:
                r.status = "degraded"
                r.detail = "平台当前无视频内容(0个视频)"
            else:
                r.status = "working"
                r.detail = f"发现{total_videos}个视频"
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    def test_learning_mode(self) -> InteractionResult:
        r = InteractionResult("learning_mode")
        try:
            lesson = self.client.get_lesson(self._test_lesson_id)
            steps = lesson.get("steps", [])
            if not steps:
                r.status = "degraded"
                r.detail = "无Step数据"
                return r
            first_step = steps[0]
            rp = first_step.get("render_payload", {})
            has_guide = "guide" in rp
            has_detailed = "detailed" in rp
            has_standard = "standard" in rp
            guide = rp.get("guide", {})
            has_checklist = bool(guide.get("checklist"))
            has_safety = bool(guide.get("safety_check"))
            if has_guide and has_detailed and has_checklist and has_safety:
                r.status = "working"
                r.detail = "学习模式数据完整: guide+detailed+standard, checklist+safety"
            else:
                r.status = "degraded"
                r.detail = f"不完整: guide={has_guide}, detailed={has_detailed}, checklist={has_checklist}"
        except Exception as e:
            r.status = "broken"
            r.detail = str(e)[:120]
        return r

    # ═══════════════════════════════════════════════════════
    # 全量运行
    # ═══════════════════════════════════════════════════════

    def run_all(self) -> dict:
        self._log("=" * 60)
        self._log("  平台交互功能全量测评 v2.0")
        self._log(f"  API前缀: /phase3-api")
        self._log("=" * 60)
        self.client.login()

        tests = [
            ("quiz_start", self.test_quiz_start),
            ("quiz_submit", self.test_quiz_submit),
            ("agent_chat", self.test_agent_chat),
            ("step_progress", self.test_step_progress),
            ("next_step", self.test_next_step),
            ("student_profile", self.test_student_profile),
            ("knowledge_search", self.test_knowledge_search),
            ("event_tracking", self.test_event_tracking),
            ("resource_download", self.test_resource_download),
            ("agent_resolve", self.test_agent_resolve),
            ("evidence_upload", self.test_evidence_upload),
            ("learning_mode", self.test_learning_mode),
            ("video_playback", self.test_video_playback),
        ]

        results = []
        for key, method in tests:
            self._log(f"\n[{FEATURE_DEFINITIONS[key]['priority']}] {FEATURE_DEFINITIONS[key]['name']}...")
            r = method()
            results.append(r)
            icon = {"working": "[OK]", "degraded": "[~]", "broken": "[X]", "untested": "[?]"}[r.status]
            self._log(f"  {icon} {r.status}: {r.detail[:120]}")

        report = self._build_report(results)
        self._print_summary(report)

        # Phase各最后Lesson Quiz汇总
        self._log(f"\n{'='*60}")
        self._log("  各Phase最后一天Quiz汇总")
        self._log("=" * 60)
        quiz_results = {}
        phase_last = [
            ("phase1", 20), ("phase2", 25), ("phase3", 9),
            ("phase4", 16), ("phase5", 26),
        ]
        for pc, lid in phase_last:
            qr = self.test_quiz_start(lesson_id=lid)
            quiz_results[pc] = qr.to_dict()
            icon = "[OK]" if qr.status == "working" else "[X]"
            self._log(f"  {icon} {pc} L{lid}: {qr.detail}")

        report["phase_quiz_summary"] = quiz_results
        return report

    def run_quick(self) -> dict:
        self._log("快速测试 (P0关键功能)")
        self.client.login()
        results = [
            self.test_quiz_start(),
            self.test_agent_chat(),
            self.test_step_progress(),
        ]
        report = self._build_report(results)
        self._print_summary(report)
        return report

    # ═══════════════════════════════════════════════════════
    # 报告
    # ═══════════════════════════════════════════════════════

    def _build_report(self, results: list[InteractionResult]) -> dict:
        features = {r.feature_key: r.to_dict() for r in results}
        working = sum(1 for r in results if r.status == "working")
        degraded = sum(1 for r in results if r.status == "degraded")
        broken = sum(1 for r in results if r.status == "broken")
        total = len(results)
        health_score = round((working + degraded * 0.5) / total, 2) if total else 0

        categories = {}
        for r in results:
            cat = r.definition.get("category", "unknown")
            if cat not in categories:
                categories[cat] = {"working": 0, "degraded": 0, "broken": 0, "total": 0}
            categories[cat][r.status] += 1
            categories[cat]["total"] += 1

        p0_broken = [r.feature_key for r in results
                     if r.status == "broken" and r.definition.get("priority") == "P0"]

        return {
            "evaluator_version": "2.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform_url": self.base_url,
            "api_prefix": "/phase3-api",
            "summary": {
                "total": total, "working": working, "degraded": degraded, "broken": broken,
                "health_score": health_score,
                "p0_blocked": len(p0_broken), "p0_blocked_features": p0_broken,
            },
            "categories": categories,
            "features": features,
        }

    def _print_summary(self, report: dict):
        s = report["summary"]
        print(f"\n{'='*60}")
        print(f"  平台交互健康度: {s['health_score']*100:.0f}%")
        print(f"  Working: {s['working']} | Degraded: {s['degraded']} | Broken: {s['broken']}")
        if s["p0_blocked"]:
            print(f"  [!!] P0阻塞: {s['p0_blocked_features']}")
        else:
            print(f"  [OK] 无P0阻塞")
        print(f"{'='*60}")


def main():
    ap = argparse.ArgumentParser(description="AI+X 平台交互功能全量测评器 v2.0")
    ap.add_argument("--all", action="store_true", default=True, help="全量测试 (默认)")
    ap.add_argument("--quick", action="store_true", help="快速测试 (仅P0)")
    ap.add_argument("--output", type=str, help="JSON报告输出路径")
    ap.add_argument("--url", type=str, default=DEFAULT_BASE_URL, help="平台URL")
    args = ap.parse_args()

    evaluator = PlatformInteractionEvaluator(base_url=args.url)

    if args.quick:
        report = evaluator.run_quick()
    else:
        report = evaluator.run_all()

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {args.output}")

    sys.exit(0 if not report["summary"]["p0_blocked"] else 1)


if __name__ == "__main__":
    main()
