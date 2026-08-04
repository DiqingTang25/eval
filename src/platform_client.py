"""
AI+硬件实训平台 API 客户端 (P1)

封装 http://124.174.108.70 的 REST 接口 (API前缀 /phase3-api):
  - POST /phase3-api/auth/login   登录 → JWT
  - GET  /phase3-api/lessons      全部课时列表
  - GET  /phase3-api/lessons/:id  单课时详情 (lesson+resources+videos+steps)
  - GET  /phase3-api/phases       阶段列表
  - POST /phase3-api/agent/chat   Agent 对话 (核心, 火山知识库驱动)
  - POST /phase3-api/quiz/start   启动 Quiz (每个Lesson完成时触发)
  - POST /phase3-api/quiz/submit  提交 Quiz 答案
  - GET  /phase3-api/profile/me   学生画像 (6维雷达图)
  - POST /phase3-api/events       前端事件追踪
  - GET  /phase3-api/knowledge/search  知识库搜索

关键约束 (踩坑记录):
  - 平台有两个API前缀: /api (旧,兼容层) 和 /phase3-api (前端实际使用)
  - 两个前缀使用不同的JWT密钥, 必须用对应端点的 /auth/login 获取token
  - 默认使用 /phase3-api (前端JS中 P0="/phase3-api")
  - 平台 Agent 有 QPS 速率限制, 连续请求会返回 "QPS 已达上限" 兜底文案 →
    client 内置节流 (min_interval) + 指数退避重试。
  - WSL2 环境不能走系统代理 → session.trust_env=False + proxies=None。
  - 正确 base_url 是 http://124.174.108.70 (不是 aiagent.xjtlu.edu.cn — 那个带验证码)。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests


# ── 平台默认配置 ──
DEFAULT_BASE_URL = "http://124.174.108.70"
DEFAULT_USERNAME = "student001"
DEFAULT_PASSWORD = "123456"

# QPS 兜底文案特征 (命中即视为被限流)
_RATE_LIMIT_MARKERS = (
    "QPS",
    "每秒查询率",
    "知识库检索暂时不可用",
    "降低访问频率",
)


@dataclass
class ChatResult:
    """Agent 一次对话的结构化结果"""
    ok: bool = False
    answer: str = ""
    sources: list = field(default_factory=list)
    message_id: Optional[int] = None
    provider: str = ""
    duration: float = 0.0
    rate_limited: bool = False
    error: str = ""

    @property
    def is_usable(self) -> bool:
        """回答可用于评测 (成功且未被限流)"""
        return self.ok and not self.rate_limited and bool(self.answer.strip())


class PlatformError(Exception):
    """平台交互异常"""


class PlatformClient:
    """AI+硬件实训平台 REST 客户端 (线程内串行使用)"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
        min_interval: float = 4.0,
        timeout: int = 45,
        max_retries: int = 4,
        verbose: bool = True,
        api_prefix: str = "/phase3-api",
        content_api_prefix: str = "/api",
    ):
        """
        :param min_interval: 两次 chat 之间的最小间隔秒数 (规避 QPS 限流)
        :param timeout: 单请求超时秒数
        :param max_retries: 被限流/网络错误时的最大重试次数
        :param api_prefix: 交互API路径前缀 (/phase3-api = Quiz/Agent/Profile/Events)
        :param content_api_prefix: 内容API路径前缀 (/api = Phases/Lessons with render_payload)

        注意: /phase3-api 和 /api 使用不同的JWT密钥, 需分别登录。
              /api 返回完整Step数据(含render_payload), /phase3-api 返回轻量Step。
        """
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix.rstrip("/")
        self.content_api_prefix = content_api_prefix.rstrip("/")
        self.username = username
        self.password = password
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.verbose = verbose

        self.token: Optional[str] = None
        self.content_token: Optional[str] = None  # /api 前缀的token
        self.user: dict = {}
        self._last_chat_ts: float = 0.0

        # WSL2 下禁用系统代理, 否则连不上内网 IP
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}

    # ── 内部工具 ──
    def _log(self, msg: str):
        if self.verbose:
            print(f"[platform] {msg}")

    def _url(self, path: str, content: bool = False) -> str:
        """拼接 API URL: base_url + prefix + path.
        :param content: True=使用content_api_prefix (/api), False=使用api_prefix (/phase3-api)
        """
        prefix = self.content_api_prefix if content else self.api_prefix
        return f"{self.base_url}{prefix}{path}"

    def _headers(self, content: bool = False) -> dict:
        token = self.content_token if content else self.token
        if not token:
            prefix = "content_api" if content else "api"
            raise PlatformError(f"尚未登录 ({prefix}), 请先调用 login()")
        return {"Authorization": f"Bearer {token}"}

    def _throttle(self):
        """确保距上次 chat 至少 min_interval 秒"""
        elapsed = time.monotonic() - self._last_chat_ts
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)

    @staticmethod
    def _is_rate_limited(text: str) -> bool:
        return any(m in text for m in _RATE_LIMIT_MARKERS)

    # ── 认证 ──
    def login(self) -> dict:
        """登录两个API前缀, 缓存JWT, 返回 user 信息"""
        login_body = {"username": self.username, "password": self.password}

        # 1. 登录 /phase3-api (交互API: Quiz/Agent/Profile)
        try:
            r = self.session.post(
                f"{self.base_url}{self.api_prefix}/auth/login",
                json=login_body, timeout=self.timeout,
            )
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                self.user = data.get("user", {})
                self._log(
                    f"登录成功 ({self.api_prefix}): "
                    f"{self.user.get('display_name') or self.username} "
                    f"({self.user.get('role')})"
                )
            else:
                self._log(f"{self.api_prefix} 登录失败 HTTP {r.status_code}")
        except requests.RequestException as e:
            self._log(f"{self.api_prefix} 登录请求异常: {e}")

        # 2. 登录 /api (内容API: Phases/Lessons with render_payload)
        try:
            r2 = self.session.post(
                f"{self.base_url}{self.content_api_prefix}/auth/login",
                json=login_body, timeout=self.timeout,
            )
            if r2.status_code == 200:
                data2 = r2.json()
                self.content_token = data2.get("token")
                if not self.user:
                    self.user = data2.get("user", {})
                self._log(f"内容API ({self.content_api_prefix}) 登录成功")
            else:
                self._log(f"{self.content_api_prefix} 登录失败 HTTP {r2.status_code}")
        except requests.RequestException as e:
            self._log(f"{self.content_api_prefix} 登录请求异常: {e}")

        if not self.token and not self.content_token:
            raise PlatformError("两个API前缀均登录失败")
        return self.user

    def ensure_login(self):
        if not self.token and not self.content_token:
            self.login()

    # ── 课程 (使用 content_api_prefix=/api 获取含render_payload的完整数据) ──
    def get_lessons(self, phase_id: int = None) -> list[dict]:
        """返回课时列表 [{id,title,phase_id,...}]，可按 phase_id 筛选"""
        self.ensure_login()
        params = {}
        if phase_id is not None:
            params["phase_id"] = phase_id
        r = self.session.get(
            self._url("/lessons", content=True), headers=self._headers(content=True),
            params=params, timeout=self.timeout
        )
        r.raise_for_status()
        data = r.json()
        # API返回格式: [{id, title, phase_id, ...}] (裸数组) 或 {lessons: [...]}
        if isinstance(data, dict):
            data = data.get("lessons") or data.get("data") or []
        return data

    def get_all_lessons(self) -> list[dict]:
        """遍历所有 Phase 聚合全部课时列表"""
        phases = self.get_phases()
        all_lessons = []
        for p in phases:
            pid = p.get("id")
            if pid is not None:
                lessons = self.get_lessons(phase_id=pid)
                for l in lessons:
                    l["_phase_title"] = p.get("title", "")
                    l["_phase_code"] = p.get("phase_code", "")
                all_lessons.extend(lessons)
        return all_lessons

    def get_lesson(self, lesson_id: int) -> dict:
        """返回单课时详情 (使用 /api 前缀获取含 render_payload 的完整数据):
        {id, phase_id, title, description, day_index, order_index,
         estimated_minutes, resources: [...], videos: [...], steps: [{render_payload}]}
        """
        self.ensure_login()
        r = self.session.get(
            self._url(f"/lessons/{lesson_id}", content=True),
            headers=self._headers(content=True),
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_phases(self) -> list[dict]:
        """返回阶段列表 (使用 /api 前缀):
        [{id, phase_code, title, description, order_index}, ...]
        按 order_index 升序排列，排除 order_index>=90 的非主阶段(如VOD测试课)。
        """
        self.ensure_login()
        r = self.session.get(
            self._url("/phases", content=True), headers=self._headers(content=True),
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        # API v2: 裸数组 [{id, phase_code, title, ...}]
        # 兼容旧格式: {phases: [...]} 或 {data: [...]}
        if isinstance(data, dict):
            data = data.get("phases") or data.get("data") or []
        if not isinstance(data, list):
            return []
        return sorted(data, key=lambda p: p.get("order_index", 99))

    def get_main_phases(self) -> list[dict]:
        """返回主阶段列表 (排除 order_index>=90 的测试/VOD阶段)"""
        return [p for p in self.get_phases() if p.get("order_index", 99) < 90]

    def lesson_summary(self, lesson_id: int) -> dict:
        """
        提取课时摘要, 供评测构造 golden/context 使用:
          {id, title, phase_id, step_count, resource_count, video_count,
           step_titles, step_render_layers, resource_urls}
        """
        detail = self.get_lesson(lesson_id)
        # API v2 返回扁平结构 (不是 {lesson: {...}})
        steps = detail.get("steps") or []
        resources = detail.get("resources") or []
        videos = detail.get("videos") or []
        # 统计 render_payload 的层
        render_layers = set()
        for s in steps:
            rp = s.get("render_payload") or {}
            for layer in rp.keys():
                render_layers.add(layer)
        return {
            "id": detail.get("id", lesson_id),
            "title": detail.get("title", ""),
            "phase_id": detail.get("phase_id"),
            "day_index": detail.get("day_index"),
            "order_index": detail.get("order_index"),
            "step_count": len(steps),
            "step_titles": [s.get("title", "") for s in steps],
            "step_render_layers": sorted(render_layers),
            "resource_count": len(resources),
            "resource_urls": [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "type": r.get("resource_type", "")}
                for r in resources
            ],
            "video_count": len(videos),
            "knowledge_points_defined": sum(
                1 for s in steps if s.get("knowledge_points")
            ),
        }

    # ── Agent 对话 (核心) ──
    def chat(self, lesson_id: int, message: str) -> ChatResult:
        """
        发送一条消息给课时 Agent, 内置节流 + QPS 退避重试。

        :return: ChatResult (rate_limited=True 表示重试耗尽仍被限流)
        """
        self.ensure_login()
        url = self._url("/agent/chat")
        body = {"lesson_id": lesson_id, "message": message}

        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            start = time.monotonic()
            try:
                r = self.session.post(
                    url, headers=self._headers(), json=body, timeout=self.timeout
                )
            except requests.RequestException as e:
                last_err = f"网络错误: {e}"
                self._log(f"第{attempt}次请求异常: {e}; {2 ** attempt}s 后重试")
                time.sleep(2 ** attempt)
                self._last_chat_ts = time.monotonic()
                continue

            self._last_chat_ts = time.monotonic()
            duration = self._last_chat_ts - start

            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:150]}"
                self._log(f"第{attempt}次 {last_err}; 退避重试")
                time.sleep(2 ** attempt)
                continue

            data = r.json()
            answer = data.get("answer", "") or ""

            if self._is_rate_limited(answer):
                backoff = self.min_interval * attempt + 3
                self._log(f"第{attempt}次被限流(QPS), {backoff:.0f}s 后重试")
                time.sleep(backoff)
                continue

            return ChatResult(
                ok=bool(data.get("ok", True)),
                answer=answer,
                sources=data.get("sources", []) or [],
                message_id=data.get("message_id"),
                provider=data.get("provider", ""),
                duration=round(duration, 2),
                rate_limited=False,
            )

        # 重试耗尽
        self._log(f"chat 重试 {self.max_retries} 次仍失败: {last_err}")
        return ChatResult(
            ok=False,
            rate_limited=True,
            error=last_err or "QPS 限流重试耗尽",
        )


    # ── Quiz 交互 (前端已编码, 后端待部署) ──
    def quiz_start(self, lesson_id: int) -> dict:
        """
        启动 Lesson 级 Quiz (对应前端 lh() 函数).
        POST /api/quiz/start  body: {lesson_id}

        :return: {ok, status_code, quiz_session_id, questions, error}
        """
        self.ensure_login()
        url = self._url("/quiz/start")
        try:
            r = self.session.post(
                url, headers=self._headers(),
                json={"lesson_id": lesson_id}, timeout=self.timeout,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "ok": True, "status_code": 200,
                    "quiz_session_id": data.get("quiz_session_id"),
                    "questions": data.get("questions", []),
                    "next_lesson_id": data.get("next_lesson_id"),
                    "raw": data,
                }
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    def quiz_submit(self, quiz_session_id: str, answers: list[dict]) -> dict:
        """
        提交 Quiz 答案 (对应前端 uy() 函数).
        POST /api/quiz/submit  body: {quiz_session_id, answers: [{question_id, selected_answer}]}

        :return: {ok, status_code, score, results, next_lesson_id, error}
        """
        self.ensure_login()
        url = self._url("/quiz/submit")
        try:
            r = self.session.post(
                url, headers=self._headers(),
                json={"quiz_session_id": quiz_session_id, "answers": answers},
                timeout=self.timeout,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "ok": True, "status_code": 200,
                    "score": data.get("score"), "results": data.get("results", []),
                    "next_lesson_id": data.get("next_lesson_id"), "raw": data,
                }
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    # ── Step 交互 ──
    def step_progress(self, step_id: int, status: str = "completed") -> dict:
        """
        标记 Step 完成状态 (对应前端 du() 函数).
        POST /api/steps/{step_id}/progress  body: {status}

        :return: {ok, status_code, step_block_id, error}
        """
        self.ensure_login()
        url = self._url(f"/steps/{step_id}/progress")
        try:
            r = self.session.post(
                url, headers=self._headers(),
                json={"status": status}, timeout=self.timeout,
            )
            if r.status_code == 200:
                data = r.json()
                return {"ok": True, "status_code": 200,
                        "step_block_id": data.get("step_block_id"), "raw": data}
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    def next_step(self, lesson_id: int, from_step_id: int = None) -> dict:
        """
        获取下一Step (对应前端 dn() 函数).
        POST /api/lessons/{lesson_id}/next-step  body: {from_step_block_id}

        :return: {ok, status_code, done, step, progress, error}
        """
        self.ensure_login()
        url = self._url(f"/lessons/{lesson_id}/next-step")
        body = {}
        if from_step_id is not None:
            body["from_step_block_id"] = from_step_id
        try:
            r = self.session.post(
                url, headers=self._headers(), json=body, timeout=self.timeout,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "ok": True, "status_code": 200,
                    "done": data.get("done", False),
                    "step": data.get("step"), "progress": data.get("progress"),
                    "raw": data,
                }
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    # ── 学生画像 ──
    def get_profile(self) -> dict:
        """获取学生知识点画像. GET /api/profile/me"""
        self.ensure_login()
        url = self._url("/profile/me")
        try:
            r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
            if r.status_code == 200:
                return {"ok": True, "status_code": 200, "profile": r.json()}
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    # ── 知识搜索 ──
    def knowledge_search(self, query: str, limit: int = 4) -> dict:
        """搜索知识库. GET /api/knowledge/search?q=...&limit=..."""
        self.ensure_login()
        url = self._url("/knowledge/search")
        try:
            r = self.session.get(
                url, headers=self._headers(),
                params={"q": query, "limit": limit}, timeout=self.timeout,
            )
            if r.status_code == 200:
                data = r.json()
                return {"ok": True, "status_code": 200,
                        "chunks": data.get("chunks", []), "raw": data}
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    # ── 事件追踪 ──
    def track_event(self, event_type: str, payload: dict = None) -> dict:
        """发送前端事件. POST /api/events  body: {event_type, ...payload}"""
        self.ensure_login()
        url = self._url("/events")
        body = {"event_type": event_type}
        if payload:
            body.update(payload)
        try:
            r = self.session.post(
                url, headers=self._headers(), json=body, timeout=self.timeout,
            )
            if r.status_code in (200, 201, 204):
                return {"ok": True, "status_code": r.status_code}
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    # ── Agent 反馈 ──
    def agent_resolve(self, message_id, resolved: bool = True) -> dict:
        """标记Agent回答是否解决了问题. PATCH /api/agent/messages/{id}/resolution"""
        self.ensure_login()
        url = self._url(f"/agent/messages/{message_id}/resolution")
        try:
            r = self.session.patch(
                url, headers=self._headers(),
                json={"resolved": resolved}, timeout=self.timeout,
            )
            if r.status_code == 200:
                return {"ok": True, "status_code": 200, "raw": r.json()}
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}

    # ── 证据上传 ──
    def upload_evidence(self, step_id: int, file_path: str,
                        evidence_type: str = "screenshot") -> dict:
        """上传Step证据文件. POST /api/steps/{step_id}/evidence-files (multipart)"""
        self.ensure_login()
        url = self._url(f"/steps/{step_id}/evidence-files")
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {"evidence_type": evidence_type}
                r = self.session.post(
                    url, headers=self._headers(),
                    files=files, data=data, timeout=self.timeout,
                )
            if r.status_code == 200:
                return {"ok": True, "status_code": 200, "raw": r.json()}
            return {"ok": False, "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            return {"ok": False, "status_code": None, "error": str(e)}
        except FileNotFoundError:
            return {"ok": False, "status_code": None, "error": f"文件不存在: {file_path}"}


if __name__ == "__main__":
    # 冒烟测试
    c = PlatformClient()
    c.login()

    # Phases
    phases = c.get_phases()
    print(f"全部阶段: {len(phases)}")
    main = c.get_main_phases()
    print(f"主阶段: {len(main)}")
    for p in main:
        print(f"  [{p['phase_code']}] {p['title']} (order={p['order_index']})")

    # Lessons (按 Phase)
    for p in main:
        lessons = c.get_lessons(phase_id=p["id"])
        print(f"  {p['title']}: {len(lessons)} 课时")
        for l in lessons[:2]:
            print(f"    L{l['id']}: {l.get('title', '?')}")

    # Lesson summary
    s = c.lesson_summary(4)
    print(f"\n课时4摘要: {s['title']}, {s['step_count']} steps, "
          f"{s['resource_count']} resources, {s['video_count']} videos, "
          f"render_layers={s['step_render_layers']}")

    # Agent chat
    print("\nAgent Chat 测试:")
    res = c.chat(4, "什么是GPIO？")
    print(f"  ok={res.ok} usable={res.is_usable} len={len(res.answer)}")
    if res.answer:
        print(f"  answer: {res.answer[:120]}")
    else:
        print(f"  error: {res.error}")
