"""
HiAgent REST API 适配器 v3.6 — 直接 API 调用, 无需浏览器

API: POST https://aiagent.xjtlu.edu.cn/api/proxy/api/v1
Auth: Bearer {api_key}
Body: {"app_id": "...", "query": "...", "response_mode": "blocking", "user": "agent-eval"}
"""

import os, time, json, urllib.request, urllib.error
from dataclasses import dataclass
from .base import BaseAgent, AgentResponse, AgentStatus

PHASE_AGENTS = {
    "phase1": {"name": "Phase 1 — 国产AI技术基础",
        "app_id": os.getenv("HIAGENT_PHASE1_APPID", ""),
        "api_key": os.getenv("HIAGENT_PHASE1_APIKEY", "")},
    "phase2": {"name": "Phase 2 — 新型硬件设计",
        "app_id": os.getenv("HIAGENT_PHASE2_APPID", ""),
        "api_key": os.getenv("HIAGENT_PHASE2_APIKEY", "")},
    "phase3_4": {"name": "Phase 3&4 — 环境感知与触觉反馈",
        "app_id": os.getenv("HIAGENT_PHASE3_4_APPID", ""),
        "api_key": os.getenv("HIAGENT_PHASE3_4_APIKEY", "")},
    "phase5": {"name": "Phase 5 — 具身智能控制",
        "app_id": os.getenv("HIAGENT_PHASE5_APPID", "d90b0fd4shh7q1vt7r4g"),
        "api_key": os.getenv("HIAGENT_PHASE5_APIKEY", "d97htrd4shhd3s3p351g")},
}

API_URL = "https://aiagent.xjtlu.edu.cn/api/proxy/api/v1"


class HiApiAgent(BaseAgent):
    def __init__(self, name="hi_api", config=None):
        super().__init__(name, config)
        config = config or {}
        self.phase = config.get("phase", "phase5")
        pc = PHASE_AGENTS.get(self.phase, PHASE_AGENTS["phase5"])
        self.app_id = config.get("app_id") or pc["app_id"]
        self.api_key = config.get("api_key") or pc["api_key"]
        self.timeout = config.get("timeout", 120)
        self.debug = config.get("debug", True)
        self._connected = False
        self._conversation_id = None

    def _log(self, msg):
        if self.debug:
            print(f"[HiAPI:{self.phase}] {msg}")

    def start(self):
        self._log(f"凭证: app_id={self.app_id[:12]}...")
        if not self.app_id or not self.api_key:
            self._log("❌ APPID 或 APIKEY 未配置")
            return False
        self._connected = True
        self._log("✅ API 凭证已就绪")
        return True

    def send_message(self, text, timeout=None):
        start = time.time()
        timeout = timeout or self.timeout
        self._log(f"发送: {text[:60]}...")
        if not self._connected:
            return AgentResponse(status=AgentStatus.ERROR, text="",
                                 metadata={"error": "未调用 start()"})

        body = {"app_id": self.app_id, "query": text,
                "response_mode": "blocking", "user": "agent-eval"}
        if self._conversation_id:
            body["conversation_id"] = self._conversation_id

        try:
            data = self._post(API_URL, body, timeout)
            answer = (data.get("answer", "") or data.get("text", "") or
                      data.get("reply", "") or data.get("message", ""))
            conv_id = (data.get("conversation_id", "") or data.get("id", "") or
                       data.get("session_id", ""))
            resp = AgentResponse(
                status=AgentStatus.SUCCESS, text=answer,
                duration_seconds=round(time.time() - start, 1),
                turn=len(self._conversation_history) + 1,
                metadata={"method": "rest_api", "phase": self.phase,
                          "conversation_id": conv_id})
            self._conversation_id = conv_id
            self._conversation_history.append(resp)
            return resp
        except Exception as e:
            return AgentResponse(status=AgentStatus.ERROR, text="",
                                 duration_seconds=round(time.time() - start, 1),
                                 metadata={"error": str(e)})

    def _post(self, url, body, timeout):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={
            "Apikey": self.api_key,
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"HTTP {e.code}: {err}")

    def get_history(self):
        return self._conversation_history

    def close(self):
        self._connected = False
        self._conversation_id = None


@dataclass
class ChatResult:
    text: str = ""
    conversation_id: str = ""
    error: str = ""
