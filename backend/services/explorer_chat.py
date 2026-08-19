"""
Explorer Chat Service — LLM 对话驱动的平台探索 (对话为主, 固定表单为辅)

设计原则 (2026-08-19):
  1. 用户用自然语言描述探索任务 → LLM 提取参数 (URL/凭证/范围)
  2. 缺什么就问什么 — 固定表单只作预填/兜底
  3. 参数齐备后先与用户确认, 确认后复用 ExplorerService 现有流水线启动
  4. 无 LLM key 时降级为确定性正则解析, 对话交互保持可用

状态机: collecting → confirm → running → done

边界与防护 (2026-08-19 agent1-chat 审查加固):
  - 会话 4 小时空闲过期 (last_active_ts 驱动), GC 在 start_chat/handle_message/get_history 均触发
  - 每条用户消息刷新 last_active_ts; 过期会话回复 action="expired" 并移除
  - 60 条消息上限 (保留最近 60 条)
  - 每会话 asyncio.Lock 串行化消息处理, 防止并发消息在 await 点交错 (双启动/状态错乱)
  - LLM 调用失败/无 key → 自动降级确定性正则解析
"""

import asyncio
import json
import logging
import re
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CHAT_TTL_SECONDS = 4 * 3600  # 会话 4 小时空闲过期
MAX_MESSAGES = 60            # 消息上限
LLM_TIMEOUT_SECONDS = 25     # LLM 调用超时

_SYSTEM_PROMPT = (
    "你是平台探索助手, 帮助用户用自然语言配置并启动教学平台的自动探索。\n"
    "从用户消息中提取探索参数, 输出严格的 JSON 对象, 不要输出任何其他文字。\n"
    'JSON 字段: {"intent": "confirm|status|cancel|info|update", "target_url": "", '
    '"username": "", "password": "", "headless": true, "max_depth": 3, '
    '"max_pages": 50, "no_login": false, "use_last_profile": false}\n'
    "规则:\n"
    "- intent=confirm: 用户明确表示开始/确认探索 (开始/启动/go/start/确认)\n"
    "- intent=cancel: 用户要取消\n"
    "- intent=status: 用户询问进度/状态\n"
    "- intent=update: 用户补充参数 (URL/账号/密码/深度/页数)\n"
    "- no_login=true: 用户表示平台无需登录\n"
    "- use_last_profile=true: 用户说「用上次的平台/继续上次的」\n"
    "- 字段没提到就保持原值: 用空字符串表示未提供, null 表示未提及\n"
)


class ExplorerChatService:
    """探索器对话编排 — 状态机 + LLM 意图解析 + 复用 ExplorerService 启动"""

    def __init__(self, explorer_service=None):
        self._chats: dict = {}       # chat_id -> state
        self._lock = threading.Lock()
        # 注入 ExplorerService 单例 (与 /api/explorer/run 共享运行状态, 避免重复启动)
        self._explorer_service = explorer_service

    def _get_explorer_service(self):
        if self._explorer_service is None:
            from backend.services.explorer_service import ExplorerService
            self._explorer_service = ExplorerService()
        return self._explorer_service

    # ── 内部工具 ──────────────────────────────────────────────

    def _new_state(self, defaults: dict) -> dict:
        return {
            "chat_id": f"chat_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
            "status": "collecting",
            "params": {
                "target_url": (defaults or {}).get("target_url", ""),
                "username": (defaults or {}).get("username", ""),
                "password": (defaults or {}).get("password", ""),
                "headless": (defaults or {}).get("headless", True),
                "max_depth": int((defaults or {}).get("max_depth") or 3),
                "max_pages": int((defaults or {}).get("max_pages") or 50),
            },
            "no_login": bool((defaults or {}).get("no_login")),
            "messages": [],           # [{role, content, ts}]
            "explore_session_id": "",
            "created_ts": time.time(),
            "last_active_ts": time.time(),   # 空闲过期基准 (每条消息刷新)
            "lock": asyncio.Lock(),          # 每会话串行化处理 (并发消息防交错)
        }

    @staticmethod
    def _push(chat: dict, role: str, content: str):
        chat["messages"].append({
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        # 防膨胀: 保留最近 MAX_MESSAGES 条
        if len(chat["messages"]) > MAX_MESSAGES:
            chat["messages"] = chat["messages"][-MAX_MESSAGES:]

    def _gc(self):
        """清理空闲过期会话 (调用方需持有 self._lock)"""
        now = time.time()
        stale = [cid for cid, c in self._chats.items()
                 if now - c.get("last_active_ts", c["created_ts"]) > CHAT_TTL_SECONDS]
        for cid in stale:
            self._chats.pop(cid, None)
        return len(stale)

    def _is_expired(self, chat: dict) -> bool:
        now = time.time()
        return now - chat.get("last_active_ts", chat["created_ts"]) > CHAT_TTL_SECONDS

    def _call_llm(self, chat: dict) -> dict | None:
        """调用文本 LLM 解析意图 → 参数 dict; 失败/无key 返回 None (降级确定性解析)"""
        try:
            from src.platform_probe.api_keys import get_api_keys
            provider = get_api_keys().get_text_llm()
            if not provider:
                return None

            history = chat["messages"][-8:]
            msgs = [{"role": "system", "content": _SYSTEM_PROMPT}]
            for m in history:
                role = "assistant" if m["role"] == "assistant" else "user"
                msgs.append({"role": role, "content": m["content"]})

            payload = json.dumps({
                "model": provider.model_id,
                "messages": msgs,
                "temperature": 0,
                "max_tokens": 400,
            }).encode("utf-8")
            url = f"{provider.base_url.rstrip('/')}/chat/completions"
            req = urllib.request.Request(
                url, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {provider.api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return self._parse_llm_json(content)
        except Exception as e:
            logger.warning("ExplorerChat LLM call failed: %s", e)
            return None

    @staticmethod
    def _parse_llm_json(content: str) -> dict | None:
        """从 LLM 输出中提取 JSON 对象 (容忍 ```json 包裹)"""
        text = content.strip()
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_deterministic(text: str) -> dict:
        """无 LLM 时的确定性解析 (正则兜底)"""
        t = text.strip()
        intent = "info"
        if re.search(r"取消|cancel", t, re.I):
            intent = "cancel"
        elif re.search(r"进度|状态|status|怎么样了", t):
            intent = "status"
        elif re.search(r"开始|启动|确认|go|start|跑起来", t, re.I):
            intent = "confirm"

        url = ""
        m = re.search(r"(https?://[^\s，。；]+)", t)
        if m:
            url = m.group(1).rstrip("，。；")
        else:
            m = re.search(r"((?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?::\d+)?(?:/[^\s，。；]*)?)", t, re.I)
            if m:
                url = ("http://" if not m.group(1).startswith("www.") else "https://") + m.group(1)

        user = ""
        m = re.search(r"(?:账号|用户名|user(?:name)?)\s*[:：]?\s*([^\s,，;:：]+)", t, re.I)
        if m:
            user = m.group(1)
        pwd = ""
        m = re.search(r"(?:密码|password|passwd)\s*[:：]?\s*([^\s,，;。]+)", t, re.I)
        if m:
            pwd = m.group(1)
        # "user/pass" 或 "user:pass" 紧凑格式 (仅当没匹配到显式账号/密码)
        # 先剔除 URL, 避免 https://... 被误判为 user/pass
        t_clean = re.sub(r"https?://[^\s，。；]+", "", t)
        if not user and not pwd:
            m = re.search(r"([A-Za-z0-9_.-]{2,20})\s*[/:]\s*(\S{3,30})(?:\s|，|。|$)", t_clean)
            if m:
                user, pwd = m.group(1), m.group(2)

        no_login = bool(re.search(r"无需登录|不用登录|免登录|no[\s-]?login", t, re.I))
        use_last = bool(re.search(r"上次|继续上次|last", t, re.I))

        max_depth = None
        m = re.search(r"(?:深度|depth)\s*[:：]?\s*(\d)", t, re.I)
        if m:
            max_depth = int(m.group(1))
        max_pages = None
        m = re.search(r"(?:页数|pages?)\s*[:：]?\s*(\d+)", t, re.I)
        if m:
            max_pages = int(m.group(1))

        return {
            "intent": intent, "target_url": url, "username": user,
            "password": pwd, "max_depth": max_depth, "max_pages": max_pages,
            "no_login": no_login, "use_last_profile": use_last,
        }

    @staticmethod
    def _latest_profile() -> dict | None:
        """读取最近一次探索的 platform_profile.json (用于「用上次的平台」)"""
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "output" / "platform_probe" / "platform_profile.json"
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    @staticmethod
    def _reply(chat: dict, text: str, **extra) -> dict:
        ExplorerChatService._push(chat, "assistant", text)
        out = {"reply": text, "status": chat["status"], "chat_id": chat["chat_id"]}
        out.update(extra)
        return out

    @staticmethod
    def _plan_text(chat: dict) -> str:
        p = chat["params"]
        return (
            f"探索计划已就绪:\n"
            f"  • 目标: {p['target_url']}\n"
            f"  • 凭证: {p['username'] or '(免登录)'}\n"
            f"  • 无头浏览器: {'是' if p['headless'] else '否'}\n"
            f"  • 深度: {p['max_depth']} / 页数: {p['max_pages']}\n"
            f"回复「开始」启动探索；需要调整请直接告诉我。"
        )

    # ── 对外接口 ──────────────────────────────────────────────

    def start_chat(self, defaults: dict | None = None) -> dict:
        """开启新对话 — 返回问候语 (预填固定表单值作为默认参数)"""
        with self._lock:
            self._gc()
            chat = self._new_state(defaults or {})
            self._chats[chat["chat_id"]] = chat

        p = chat["params"]
        has_creds = bool(p["username"] and p["password"])
        if p["target_url"] and has_creds:
            # 表单全量预填 → 直接展示计划, 等「开始」
            chat["status"] = "confirm"
            greeting = f"你好！已从表单预填探索参数:\n{self._plan_text(chat)}"
            missing = []
        elif p["target_url"]:
            greeting = (
                f"你好！我负责帮你探索教学平台。\n"
                f"已从表单预填目标平台: {p['target_url']}\n"
                f"请告诉我登录凭证 (格式: 账号 xxx 密码 xxx)，或直接说「无需登录」。\n"
                f"确认参数后我会展示探索计划，你说「开始」我就启动。"
            )
            missing = ["credentials"]
        else:
            greeting = (
                "你好！我是平台探索助手。请用自然语言告诉我探索任务，例如：\n"
                "「探索 https://xxx.com，账号 111 密码 123456，深度 3」\n"
                "也可以说「用上次的平台」。"
            )
            missing = ["target_url"]
        return self._reply(chat, greeting, missing_fields=missing, action="none")

    async def handle_message(self, chat_id: str, message: str) -> dict:
        """处理一条用户消息 — 状态机核心 (每会话串行化)"""
        with self._lock:
            self._gc()
            chat = self._chats.get(chat_id)
        if not chat:
            return {"reply": "会话不存在或已过期，请重新开始对话。", "status": "expired",
                    "chat_id": chat_id, "action": "expired"}
        if self._is_expired(chat):
            with self._lock:
                self._chats.pop(chat_id, None)
            return {"reply": "会话已过期（超过 4 小时无交流），请重新开始对话。",
                    "status": "expired", "chat_id": chat_id, "action": "expired"}

        async with chat["lock"]:
            chat["last_active_ts"] = time.time()
            self._push(chat, "user", message)

            # 运行中: 只有 取消/进度 有意义
            if chat["status"] == "running":
                parsed = self._extract_deterministic(message)
                if parsed["intent"] == "cancel":
                    return await self._do_cancel(chat)
                if parsed["intent"] in ("status", "info"):
                    st = await self._get_explorer_service().get_status()
                    if st.get("running"):
                        return self._reply(
                            chat,
                            f"探索进行中: {st.get('progress', '')}",
                            action="status",
                        )
                    return self._reply(chat, "探索已结束，可查看下方结果。", action="status")
                return self._reply(
                    chat,
                    "探索正在后台运行。你可以问我进度，或者说「取消」。",
                    action="status",
                )

            # 意图解析 (LLM 优先, 正则兜底)
            parsed = self._call_llm(chat) or self._extract_deterministic(message)

            if parsed.get("intent") == "cancel":
                chat["status"] = "collecting"
                return self._reply(chat, "好，已取消。需要调整探索参数吗？", action="cancelled")

            if parsed.get("intent") == "status":
                st_text = "当前还没有运行中的探索。"
                return self._reply(chat, st_text, action="status")

            # 参数合并
            p = chat["params"]
            if parsed.get("use_last_profile"):
                prof = self._latest_profile()
                if prof:
                    p["target_url"] = prof.get("target_url") or prof.get("url") or p["target_url"]
                    creds = prof.get("credentials") or {}
                    p["username"] = creds.get("username", p["username"])
                    p["password"] = creds.get("password", p["password"])
                    if p["username"] and p["password"]:
                        chat["no_login"] = False
                    self._push(chat, "assistant",
                               f"已载入上次探索的平台: {p['target_url'] or '(未记录)'}")
            if parsed.get("target_url"):
                p["target_url"] = parsed["target_url"]
            if parsed.get("username"):
                p["username"] = parsed["username"]
            if parsed.get("password"):
                p["password"] = parsed["password"]
            if parsed.get("max_depth"):
                p["max_depth"] = int(parsed["max_depth"])
            if parsed.get("max_pages"):
                p["max_pages"] = int(parsed["max_pages"])
            if parsed.get("no_login"):
                chat["no_login"] = True
            if p["username"] and p["password"]:
                chat["no_login"] = False

            # 缺口检查
            if not p["target_url"]:
                return self._reply(
                    chat,
                    "请先告诉我目标平台 URL，例如「探索 https://teaching.example.com」。\n"
                    "也可以说「用上次的平台」。",
                    missing_fields=["target_url"], action="none",
                )

            if not chat["no_login"] and not (p["username"] and p["password"]):
                return self._reply(
                    chat,
                    "这个平台需要登录吗？如果需要，请提供「账号 xxx 密码 xxx」；\n"
                    "如果无需登录，请回复「无需登录」。",
                    missing_fields=["credentials"], action="none",
                )

            # 参数齐备 → 展示计划待确认 (用户已明说开始时直接启动)
            if parsed.get("intent") == "confirm":
                return await self._do_start(chat)
            chat["status"] = "confirm"
            return self._reply(chat, self._plan_text(chat), action="none", params=dict(p))

    async def _do_start(self, chat: dict) -> dict:
        """确认后启动探索 (复用现有流水线)"""
        svc = self._get_explorer_service()
        p = chat["params"]
        result = await svc.start_explore(
            target_url=p["target_url"],
            username=p["username"] if not chat.get("no_login") else "",
            password=p["password"] if not chat.get("no_login") else "",
            headless=p["headless"],
            max_depth=p["max_depth"],
            max_pages=p["max_pages"],
        )
        if result.get("status") == "started":
            chat["status"] = "running"
            chat["explore_session_id"] = result["session_id"]
            return self._reply(
                chat,
                f"🚀 探索已启动！会话 {result['session_id']}\n"
                f"完成后我会更新结果。随时问我「进度」或说「取消」。",
                action="started", explore_session_id=result["session_id"],
            )
        if result.get("status") == "busy":
            return self._reply(
                chat, "已有一个探索任务在运行中，请稍候或先取消。", action="none",
            )
        return self._reply(
            chat, f"启动失败: {result.get('error', '未知错误')}", action="none",
        )

    async def _do_cancel(self, chat: dict) -> dict:
        r = await self._get_explorer_service().cancel_explore()
        chat["status"] = "collecting"
        chat["explore_session_id"] = ""
        return self._reply(chat, r.get("message", "探索已取消。"), action="cancelled")

    def get_history(self, chat_id: str) -> dict:
        with self._lock:
            self._gc()
            chat = self._chats.get(chat_id)
        if not chat:
            return {"chat_id": chat_id, "messages": [], "expired": True}
        return {
            "chat_id": chat_id,
            "status": chat["status"],
            "params": dict(chat["params"]),
            "explore_session_id": chat.get("explore_session_id", ""),
            "messages": list(chat["messages"]),
        }
