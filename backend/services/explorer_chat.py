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
    'JSON 字段: {"intent": "confirm|status|cancel|info|update|edit", "target_url": "", '
    '"username": "", "password": "", "headless": true, "max_depth": 3, '
    '"max_pages": 50, "no_login": false, "use_last_profile": false}\n'
    "规则:\n"
    "- intent=confirm: 用户明确表示开始/确认探索 (开始/启动/go/start/确认)\n"
    "- intent=cancel: 用户要取消\n"
    "- intent=status: 用户询问进度/状态\n"
    "- intent=update: 用户首次补充参数 (URL/账号/密码/深度/页数)\n"
    "- intent=edit: 用户在已有参数上做修改 (把深度改成5/换个平台/改成免登录)\n"
    "- no_login=true: 用户表示平台无需登录\n"
    "- use_last_profile=true: 用户说「用上次的平台/继续上次的」\n"
    "- 字段没提到就保持原值: 用空字符串表示未提供, null 表示未提及\n"
)

# 必填字段白名单 — 缺则阻塞追问, 绝不静默猜测
FIELD_SPEC = {
    "target_url": {"required": True, "label": "目标平台 URL"},
    "auth": {"required": True, "label": "登录方式 (账号密码 | 免登录)"},
}
# 可选字段默认值 — 用户不提就用默认, 不阻塞
OPTIONAL_DEFAULTS = {"headless": True, "max_depth": 3, "max_pages": 50}

MASK = "******"


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
                # 凭证脱敏: 明文密码绝不进入 LLM 上下文
                msgs.append({"role": role, "content": self._mask_secret(m["content"], chat)})

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
    def _is_valid_url(url: str) -> bool:
        return bool(re.match(r"^https?://[^\s，。；]+", (url or "").strip()))

    @staticmethod
    def _normalize_edits(text: str) -> str:
        """把常见修改句式归一化为可解析句式 (确定性路径的 edit 意图支持)

        「把深度改 5」→「深度 5」  「页数改成 30」→「页数 30」
        「改成免登录」→「无需登录」 「换成 https://x」→「https://x」
        """
        t = re.sub(
            r"(?:把|请)?\s*(?:深度|depth)\s*(?:改|改成|改为|调到|调整到|设为|设置)\s*[:：]?\s*(\d)",
            r"深度 \1", text, flags=re.I,
        )
        t = re.sub(
            r"(?:把|请)?\s*(?:页数|pages?)\s*(?:改|改成|改为|调到|调整到|设为|设置)\s*[:：]?\s*(\d+)",
            r"页数 \1", t, flags=re.I,
        )
        t = re.sub(r"(?:改|换)\s*(?:成|为)?\s*免登录|不用登录了", "无需登录", t, flags=re.I)
        t = re.sub(r"(?:改|换)\s*(?:成|为)?\s*(https?://[^\s，。；]+)", r"\1", t, flags=re.I)
        return t

    def _mask_secret(self, text: str, chat: dict | None = None) -> str:
        """凭证脱敏 — 明文密码绝不外发 (LLM prompt / history / plan 回复)"""
        pwd = (chat or {}).get("params", {}).get("password", "")
        if pwd:
            text = text.replace(pwd, MASK)
        return re.sub(
            r"(密码|password|passwd|pwd)\s*[:：=]?\s*\S+",
            r"\1: " + MASK, text, flags=re.I,
        )

    @staticmethod
    def _extract_deterministic(text: str) -> dict:
        """无 LLM 时的确定性解析 (正则兜底)"""
        t = ExplorerChatService._normalize_edits(text).strip()
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
        """读取最近一次探索的平台画像 (用于「用上次的平台」) — 平台库优先"""
        try:
            from src.platform_profile_store import latest_platform_profile
            prof = latest_platform_profile()
            if prof:
                return prof
        except Exception:
            pass
        try:
            from src.profile_paths import load_profile
            return load_profile()
        except Exception:
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

    def _build_plan(self, chat: dict) -> dict:
        """结构化探索计划 (前端渲染可编辑确认卡)

        必填字段在 steps 中 editable=true; 凭证密码绝不外发。
        """
        p = chat["params"]
        auth_value = "免登录" if chat.get("no_login") else f"账号 {p['username']} / 密码 {MASK}"
        return {
            "params": {k: (v if k != "password" else MASK) for k, v in p.items()},
            "steps": [
                {"field": "target_url", "label": "目标平台", "value": p["target_url"], "editable": True},
                {"field": "auth", "label": "登录方式", "value": auth_value, "editable": True},
                {"field": "headless", "label": "无头浏览器", "value": "是" if p["headless"] else "否", "editable": False},
                {"field": "max_depth", "label": "探索深度", "value": str(p["max_depth"]), "editable": True},
                {"field": "max_pages", "label": "最大页数", "value": str(p["max_pages"]), "editable": True},
            ],
        }

    def _summarize_result(self, chat: dict) -> str:
        """探索完成后的自然语言总结 — LLM 优先, 模板兜底"""
        try:
            from src.profile_paths import load_profile
            prof = load_profile() or {}
        except Exception:
            prof = {}

        stats = {
            "phases": prof.get("phases_found", "?"),
            "steps": prof.get("steps_found", "?"),
            "apis": prof.get("api_endpoints_found", "?"),
            "confidence": prof.get("overall_confidence", "?"),
        }

        # LLM 总结 (仅发送统计数字, 无凭证)
        try:
            from src.platform_probe.api_keys import get_api_keys
            provider = get_api_keys().get_text_llm()
            if provider:
                import urllib.request as _ur
                payload = json.dumps({
                    "model": provider.model_id,
                    "messages": [
                        {"role": "system", "content": (
                            "你是平台探索助手的播报员。用 2-3 句通俗中文告诉非技术用户探索结果"
                            "意味着什么, 并建议下一步 (去评测)。不要编造细节, 不要输出 JSON。"
                        )},
                        {"role": "user", "content": (
                            f"刚完成平台 {chat['params'].get('target_url','')} 的自动探索: "
                            f"发现学习模块 {stats['phases']} 个, 学习步骤 {stats['steps']} 个, "
                            f"API 接口 {stats['apis']} 个, 置信度 {stats['confidence']}。"
                        )},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 300,
                }).encode("utf-8")
                req = _ur.Request(
                    f"{provider.base_url.rstrip('/')}/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {provider.api_key}"},
                )
                with _ur.urlopen(req, timeout=20) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                text = body["choices"][0]["message"]["content"].strip()
                if text:
                    return f"✅ 探索完成。\n\n{text}"
        except Exception as e:
            logger.warning("ExplorerChat summary LLM failed: %s", e)

        # 模板兜底
        return (
            f"✅ 探索完成！我帮你看懂了 {chat['params'].get('target_url', '这个平台')} 的结构：\n"
            f"  • 学习模块: {stats['phases']} 个\n"
            f"  • 学习步骤: {stats['steps']} 个\n"
            f"  • API 接口: {stats['apis']} 个\n"
            f"  • 置信度: {stats['confidence']}\n\n"
            f"系统已自动生成平台画像和评测配置。\n"
            f"下一步：到「Test Runner」页面点开始评测，我会按照这个画像自动完成平台测评。\n"
            f"想探索别的平台，直接说「换个平台」再给网址即可。"
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
            return self._reply(chat, greeting, missing_fields=missing,
                               action="none", plan=self._build_plan(chat))
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
                    # 探索刚结束 → 自然语言解释产出 + 引导下一步
                    chat["status"] = "done"
                    return self._reply(chat, self._summarize_result(chat), action="done")
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
                # 必填字段校验: URL 必须是合法 http(s) 地址
                if not self._is_valid_url(parsed["target_url"]):
                    return self._reply(
                        chat,
                        "这个地址看起来不对。请提供完整的平台网址，以 http:// 或 https:// 开头，\n"
                        "例如「探索 https://teaching.example.com」。",
                        missing_fields=["target_url"], action="none",
                    )
                p["target_url"] = parsed["target_url"].strip()
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
            return self._reply(
                chat, self._plan_text(chat), action="none",
                plan=self._build_plan(chat),
            )

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
        # 凭证脱敏: params 与消息文本中的明文密码一律遮蔽
        masked_params = {
            k: (MASK if k == "password" and v else v)
            for k, v in chat["params"].items()
        }
        masked_messages = [
            {**m, "content": self._mask_secret(m["content"], chat)}
            for m in chat["messages"]
        ]
        return {
            "chat_id": chat_id,
            "status": chat["status"],
            "params": masked_params,
            "explore_session_id": chat.get("explore_session_id", ""),
            "messages": masked_messages,
        }
