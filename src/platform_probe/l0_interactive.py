"""
L0-Interactive — 交互式登录引导 (LLM 对话 + 用户协作)

解决标准 L0 自动登录搞不定的场景:
  - 验证码 (图形/短信/滑块)
  - SSO / OAuth / 扫码 / 企业微信
  - 登录后二次确认、额外必填字段
  - 动态表单 / 非标准登录流程

工作方式 (每轮循环):
  1. 抓取页面快照 (URL + 可见输入框 + 按钮清单 + 页面文本片段)
  2. LLM 观察快照 → 决策 JSON: fill / click / ask / done
     - fill: 向第 N 个输入框填值 ({username}/{password} 占位符 → 已知凭证;
             验证码等实际文本直接填)
     - click: 点击第 N 个按钮
     - ask:  向评测用户提问 (经 QuestionBridge, 阻塞等待; 带选项)
     - done: 判定登录成功/失败, 结束循环
  3. ask 的用户回答回灌给 LLM → 下一轮继续决策 (典型: 用户给验证码 → fill)

降级保底:
  - LLM 不可用 → 规则式: 检测验证码输入框→问用户要码; 检测SSO按钮→问用户选哪种方式
  - 用户超时/跳过 → 返回 degraded (未登录), 探索器继续未登录路径
  - 轮数上限 → 结束, 返回当前状态

用法:
    from src.platform_probe.l0_interactive import InteractiveLoginAgent
    agent = InteractiveLoginAgent(ask=bridge.ask, username=..., password=...)
    result = agent.run(page=page, base_url="https://...")
    # result: {"logged_in", "auth_type_guess", "notes", "rounds",
    #          "asked_user", "degraded", "transcript"}
"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

# ── 验证码/SSO 检测关键词 ──
CAPTCHA_PATTERNS = ["验证码", "captcha", "verification code", "图形码", "短信码", "手机验证", "校验码", "获取验证码", "发送验证码"]
SMS_PATTERNS = ["短信", "手机号", "mobile", "phone", "sms"]
OAUTH_PATTERNS = ["微信", "wechat", "企业微信", "google", "github", "microsoft", "sso", "扫码", "扫一扫", "二维码", "oauth", "azure", "钉钉", "dingtalk"]

LOGIN_SUCCESS_INDICATORS = ["logout", "退出", "退出登录", "课程", "学习", "phase", "lesson",
                            "课时", "module", "dashboard", "首页", "个人中心", "我的课程"]

SYSTEM_PROMPT = """你是教学平台登录引导助手。你正在帮助一个自动探索机器人登录目标平台。
已知固定凭证: username/password (可能为空)。页面可能是标准表单, 也可能是 SSO/扫码/短信/验证码等非标准登录方式。

你的工作: 观察页面快照, 每轮输出一个 JSON 决策 (只输出 JSON, 不要解释):
- {"action":"fill","input_index":N,"value":"..."}
    向可见输入框列表中的第 N 个 (从0开始) 填入 value。
    value 可用占位符 {username} / {password} 代表已知凭证; 其他情况填实际文本 (如用户提供的验证码)。
- {"action":"click","button_index":N}
    点击按钮列表中的第 N 个 (从0开始)。用于提交表单/选择登录方式标签页/点击SSO入口等。
- {"action":"ask","question":"...","options":["..."],"purpose":"captcha|oauth|sms|credentials|other"}
    需要向评测用户询问信息。问题用中文、具体、面向非技术用户, 例如"请输入手机收到的短信验证码"。
    options 给出 2-4 个快捷选项 (如 "跳过登录")。
- {"action":"done","success":true|false,"reason":"..."}
    登录已成功 (success=true) 或确定无法继续 (success=false), 结束循环。

规则:
1. 优先用已有 username/password 自动完成标准表单登录, 不向用户提不必要的问题。
2. 只有遇到非标准模式 (验证码/短信码/扫码/SSO 选择/额外必填字段/二次确认) 才 ask。
3. 用户回答后, 尽量立刻用回答完成操作 (例如把验证码 fill 进对应输入框)。
4. 如果页面已出现登录成功特征 (课程/学习/退出登录等), 立即 done success=true。
5. 同一操作不要连续重复超过 2 轮; 反复失败就 done success=false。"""


class InteractiveLoginAgent:
    """交互式登录引导 Agent"""

    def __init__(
        self,
        ask: Optional[Callable] = None,
        username: str = "",
        password: str = "",
        max_rounds: int = 8,
        question_timeout: float = 180.0,
        action_wait: float = 2.5,
        verbose: bool = True,
        diag: Optional[list] = None,
    ):
        self.ask = ask  # Callable(text, options, context, timeout_s) -> dict
        self.username = username
        self.password = password
        self.max_rounds = max_rounds
        self.question_timeout = question_timeout
        self.action_wait = action_wait
        self.verbose = verbose
        self.diag = diag if diag is not None else []
        self.transcript: list[dict] = []

    # ── 页面快照 ──

    def _snapshot(self, page) -> dict:
        """紧凑页面快照: 可见输入框 + 按钮 + 文本片段"""
        snap = {"url": "", "title": "", "inputs": [], "buttons": [], "visible_text": ""}
        try:
            snap["url"] = page.url
            snap["title"] = page.title()
        except Exception:
            pass
        try:
            for inp in page.locator("input:visible").all():
                try:
                    snap["inputs"].append({
                        "type": inp.get_attribute("type") or "text",
                        "placeholder": (inp.get_attribute("placeholder") or "")[:60],
                        "name": (inp.get_attribute("name") or "")[:40],
                    })
                except Exception:
                    continue
        except Exception:
            pass
        try:
            for b in page.locator("button:visible, a:visible, [role=button]:visible").all():
                try:
                    t = (b.text_content() or "").strip()[:50]
                    if t and t not in {x["text"] for x in snap["buttons"]}:
                        snap["buttons"].append({"text": t})
                except Exception:
                    continue
        except Exception:
            pass
        try:
            snap["visible_text"] = (page.locator("body").first.text_content() or "")[:1000]
        except Exception:
            pass
        return snap

    def _verify_login(self, page) -> bool:
        """登录成功判断: 无可见密码框 + 无可见登录/注册入口 + 出现登录后特征

        反例检测修复误判: 登录模态框关闭(密码框消失)但页面仍显示「登录/注册」
        按钮时, 视为未登录 — 此前因此把失败误判为 success, 探索整轮白跑。
        """
        try:
            if page.locator("input[type='password']:visible").count() > 0:
                return False
        except Exception:
            pass
        # 反例: 仍可见登录/注册按钮 (排除 退出登录/logout)
        try:
            login_kw = ("登录", "注册", "sign in", "sign up", "login", "register", "立即登录")
            for el in page.locator("button:visible, a:visible").all():
                try:
                    t = (el.text_content() or "").strip()
                except Exception:
                    continue
                if not t or len(t) > 12:
                    continue
                tl = t.lower()
                if "退出" in t or "logout" in tl or "sign out" in tl:
                    continue
                if any(k in t or k in tl for k in login_kw):
                    return False
        except Exception:
            pass
        try:
            html = (page.content() or "").lower()
            return any(ind in html for ind in LOGIN_SUCCESS_INDICATORS)
        except Exception:
            return True

    # ── 动作执行 ──

    def _do_fill(self, page, input_index: int, value: str) -> bool:
        try:
            inputs = page.locator("input:visible").all()
            if input_index >= len(inputs):
                return False
            v = value
            if v == "{username}":
                v = self.username
            elif v == "{password}":
                v = self.password
            inputs[input_index].fill(v)
            return True
        except Exception:
            return False

    def _do_click(self, page, button_index: int) -> bool:
        try:
            els = page.locator("button:visible, a:visible, [role=button]:visible").all()
            if button_index >= len(els):
                return False
            els[button_index].click(force=True, no_wait_after=True, timeout=8000)
            return True
        except Exception:
            return False

    # ── LLM 决策 ──

    def _llm_decide(self, snap: dict, history_ctx: str) -> Optional[dict]:
        """LLM 决策一轮动作。不可用返回 None。"""
        try:
            from src.llm_client import get_llm_client
            client, model, _ = get_llm_client()
            if not client:
                return None
            snap_json = json.dumps(snap, ensure_ascii=False)
            user_msg = (
                f"已知凭证: username={self.username or '(未提供)'}, password={'***' if self.password else '(未提供)'}\n\n"
                f"当前页面快照:\n{snap_json}\n\n"
                f"{history_ctx}"
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=400,
                temperature=0.1,
                timeout=30,
            )
            content = resp.choices[0].message.content.strip()
            # 剥离可能的 markdown 代码围栏
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except Exception as e:
            if self.verbose:
                print(f"  [L0-I] LLM 决策失败: {e}")
            return None

    # ── 规则式降级决策 (LLM 不可用) ──

    def _rule_decide(self, snap: dict, asked: set) -> Optional[dict]:
        """无 LLM 时的规则式决策。"""
        # 1. 验证码输入框 → 问用户要码
        for i, inp in enumerate(snap["inputs"]):
            ph = (inp["placeholder"] + inp["name"]).lower()
            if any(k in ph for k in ["captcha", "验证码", "图形码", "校验码", "code"]):
                if "captcha" not in asked:
                    asked.add("captcha")
                    return {"action": "ask", "question": "登录页要求输入验证码，请查看登录页面并告诉我验证码内容（如果登录页没有验证码，请回复'没有验证码'）",
                            "options": ["跳过登录"], "purpose": "captcha"}
                return None
        # 2. SSO/扫码按钮 → 问用户用哪种方式
        btn_texts = [b["text"].lower() for b in snap["buttons"]]
        if any(any(k in t for k in OAUTH_PATTERNS) for t in btn_texts):
            if "oauth" not in asked:
                asked.add("oauth")
                return {"action": "ask", "question": "这个平台似乎使用第三方登录（SSO/扫码等）。请告诉我应该使用哪种登录方式，或描述登录步骤",
                        "options": ["跳过登录", "使用账号密码"], "purpose": "oauth"}
            return None
        # 3. 有密码框且有凭证 → 填凭证 + 提交
        if self.username and self.password and any(i["type"] == "password" for i in snap["inputs"]):
            return {"action": "fill", "input_index": 0, "value": "{username}"}
        return None

    # ── 主循环 ──

    def run(self, page, base_url: str, seed_notes: str = "") -> dict:
        """
        交互式登录主循环。

        :param page: Playwright Page (已导航到登录页或目标页)
        :param base_url: 目标平台 URL
        :param seed_notes: 额外上下文 (例如测评卡点说明)
        :returns: {"logged_in", "auth_type_guess", "notes", "rounds",
                   "asked_user", "degraded", "transcript"}
        """
        asked_user = False
        asked = set()
        history_ctx = seed_notes or ""
        llm_used = False
        force_asked_n = 0  # 已向用户求助次数 (最多2次, 间隔>=3轮 — 凭证无效时可再问一次)
        last_ask_rnd = 0

        def _apply_user_credentials(page, answer: str) -> bool:
            """从用户回复解析凭证, 直接填充登录表单并提交 (绕过LLM猜测)"""
            import re as _re
            u = p = ""
            m = _re.search(r'(?:账号|用户名|user(?:name)?)\s*[:：]?\s*([^\s,，;:：]+)', answer, _re.I)
            if m:
                u = m.group(1)
            m = _re.search(r'(?:密码|password|passwd)\s*[:：]?\s*([^\s,，;。]+)', answer, _re.I)
            if m:
                p = m.group(1)
            if not u or not p:
                m = _re.search(r'([A-Za-z0-9_.-]{2,20})\s*[/:]\s*(\S{3,30})', answer)
                if m:
                    u, p = m.group(1), m.group(2)
            if not (u and p):
                return False
            ok1 = self._do_fill(page, 0, u)
            ok2 = self._do_fill(page, 1, p)
            # 提交按钮 (与LLM此前确认的按钮索引一致; 失败无害, 下一轮verify兜底)
            try:
                self._do_click(page, 1)
            except Exception:
                pass
            history_ctx_local.append(f"\n[强制求助] 用户提供凭证 账号={u} 密码=***, 已直接填充并提交")
            return ok1 or ok2

        def forced_ask(page, rnd) -> bool:
            """自动登录尝试失败 → 强制向用户求助 (设计原则: 卡点必须暴露)"""
            nonlocal asked_user, force_asked_n, last_ask_rnd
            force_asked_n += 1
            last_ask_rnd = rnd
            asked_user = True
            if not self.ask:
                return False
            result = self.ask(
                text=("自动登录没成功。请帮我确认登录方式：\n"
                      "1) 提供正确凭证，格式「账号 xxx 密码 xxx」\n"
                      "2) 或一句话说明登录方式（例如：需要手机验证码 / 扫码登录 / 学校SSO）"),
                options=["跳过登录"],
                context="登录表单已自动填充但未登录成功",
                context_type="login_page",
                timeout_s=self.question_timeout,
                source="explorer",
                meta={"purpose": "login_fallback"},
            )
            if result.get("timed_out") or result.get("skipped"):
                return False
            ans = result.get("answer", "") or ""
            history_ctx_local.append(f"\n[强制求助] 用户回答: {ans[:200]}")
            return _apply_user_credentials(page, ans)

        history_ctx_local = [history_ctx]

        if self.verbose:
            print(f"  [L0-I] 交互式登录引导启动 (max_rounds={self.max_rounds})")

        for rnd in range(1, self.max_rounds + 1):
            # 每轮开始先验证是否已登录
            if self._verify_login(page):
                self.transcript.append({"round": rnd, "event": "verified_login"})
                if self.verbose:
                    print(f"  [L0-I] ✅ 已验证登录成功 (round {rnd})")
                return self._finish(True, "登录成功", rnd, asked_user, llm_used)

            # 自动尝试三轮仍未成功 → 强制向用户求助 (最多2次, 间隔>=3轮)
            if (rnd >= 3 and force_asked_n < 2 and self.ask
                    and (last_ask_rnd == 0 or rnd - last_ask_rnd >= 3)):
                if forced_ask(page, rnd):
                    time.sleep(self.action_wait)
                history_ctx = "\n".join(history_ctx_local)
                continue

            snap = self._snapshot(page)
            decision = self._llm_decide(snap, history_ctx)
            if decision is None:
                decision = self._rule_decide(snap, asked)
            else:
                llm_used = True

            if decision is None:
                # 无更多规则动作 → 先向用户求助, 仍无解则结束
                if force_asked_n < 2 and self.ask and (last_ask_rnd == 0 or rnd - last_ask_rnd >= 3):
                    forced_ask(page, rnd)
                history_ctx = "\n".join(history_ctx_local)
                return self._finish(False, "无可用登录动作", rnd, asked_user, llm_used)

            action = decision.get("action", "")
            self.transcript.append({"round": rnd, "action": action,
                                    "decision": {k: v for k, v in decision.items() if k != "question"}})

            if action == "fill":
                ok = self._do_fill(page, decision.get("input_index", 0), decision.get("value", ""))
                history_ctx += f"\n[第{rnd}轮] fill input[{decision.get('input_index', 0)}] = {decision.get('value', '')} → {'成功' if ok else '失败'}"
                if self.verbose:
                    print(f"  [L0-I] fill #{decision.get('input_index')} → {'✓' if ok else '✗'}")
                time.sleep(self.action_wait)
                continue

            if action == "click":
                ok = self._do_click(page, decision.get("button_index", 0))
                history_ctx += f"\n[第{rnd}轮] click button[{decision.get('button_index', 0)}] → {'成功' if ok else '失败'}"
                if self.verbose:
                    print(f"  [L0-I] click #{decision.get('button_index')} → {'✓' if ok else '✗'}")
                time.sleep(self.action_wait)
                continue

            if action == "ask":
                if not self.ask:
                    # 无问答通道 → 降级
                    return self._finish(False, "无用户问答通道", rnd, asked_user, llm_used)
                question = decision.get("question", "请提供登录所需信息")
                options = list(decision.get("options") or [])
                if "跳过登录" not in options:
                    options.append("跳过登录")
                asked_user = True
                if self.verbose:
                    print(f"  [L0-I] 向用户提问: {question}")
                result = self.ask(
                    text=question,
                    options=options,
                    context=json.dumps(snap, ensure_ascii=False)[:1500],
                    context_type="login_page",
                    timeout_s=self.question_timeout,
                    source="explorer",
                    meta={"purpose": decision.get("purpose", "other")},
                )
                if result.get("timed_out") or result.get("skipped"):
                    note = "用户超时未回答" if result.get("timed_out") else "用户选择跳过登录"
                    history_ctx += f"\n[第{rnd}轮] ask → {note}"
                    return self._finish(False, note, rnd, asked_user, llm_used)
                answer = result.get("answer", "")
                history_ctx += f"\n[第{rnd}轮] 用户回答: {answer}"
                self.transcript.append({"round": rnd, "event": "user_answer", "answer": answer[:200]})
                time.sleep(self.action_wait)
                continue

            if action == "done":
                success = bool(decision.get("success", False))
                reason = decision.get("reason", "")
                if not success and force_asked_n < 2 and self.ask \
                        and (last_ask_rnd == 0 or rnd - last_ask_rnd >= 3):
                    # 自动流程自认失败 → 强制向用户求助 (卡点暴露原则)
                    if forced_ask(page, rnd):
                        time.sleep(self.action_wait)
                        history_ctx = "\n".join(history_ctx_local)
                        continue
                return self._finish(success, reason or ("成功" if success else "失败"),
                                    rnd, asked_user, llm_used)

            # 未知 action → 视为无进展
            history_ctx += f"\n[第{rnd}轮] 未知动作 {action}, 跳过"
            continue

        return self._finish(False, f"达到轮数上限 {self.max_rounds}",
                            self.max_rounds, asked_user, llm_used)

    def _finish(self, logged_in: bool, reason: str, rounds: int,
                asked_user: bool, llm_used: bool) -> dict:
        notes = f"interactive_login: {'success' if logged_in else 'degraded'} — {reason} " \
                f"(rounds={rounds}, asked_user={asked_user}, llm={llm_used})"
        if self.verbose:
            print(f"  [L0-I] 结束: {notes}")
        return {
            "logged_in": logged_in,
            "auth_type_guess": "interactive" if logged_in else "unknown",
            "notes": notes,
            "rounds": rounds,
            "asked_user": asked_user,
            "llm_used": llm_used,
            "degraded": not logged_in,
            "transcript": self.transcript,
        }
