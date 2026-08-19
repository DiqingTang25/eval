"""
L0: 认证与会话层 — 自适应版

支持 3 种模式:
  1. 自动表单登录 (form auto-detect + fill + submit)
  2. 预认证模式 (使用已保存的 storage_state JSON, 跳过登录)
  3. 交互模式 (打开浏览器让用户手动登录, 保存 session 供后续复用)

借鉴: Periscope MCP (interactive_login), balage-core (form detection)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

from playwright.sync_api import Page, Browser, BrowserContext

from .models import AuthType, AuthSchema, AuthField, SessionState
from .confidence import auth_detection_confidence

# ── 通用登录模式 ──
LOGIN_URL_PATTERNS = [
    "/login", "/signin", "/sign-in", "/auth", "/account/login",
    "/user/login", "/oauth", "/sso", "/api/auth/login",
]
USERNAME_PATTERNS = [
    "username", "user", "account", "email", "phone", "mobile",
    "login", "name", "userid", "user_id", "identifier",
]
PASSWORD_PATTERNS = [
    "password", "passwd", "pwd", "pass", "pin", "passcode",
]
LOGIN_BTN_PATTERNS = [
    "登录", "登入", "sign in", "login", "进入", "submit", "提交",
    "log in", "signin", "connect", "continue", "enter",
]


class AuthDetector:
    """认证检测器"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def detect(self, page: Page, base_url: str) -> tuple[AuthType, float, dict]:
        details = {
            "has_login_form": False, "has_username_field": False,
            "has_password_field": False, "has_oauth_redirect": False,
            "has_sso_domain": False, "login_url": "", "fields": [],
        }
        current_url = page.url
        path_lower = urlparse(current_url).path.lower()
        is_login_page = any(p in path_lower for p in LOGIN_URL_PATTERNS)

        # 查找表单
        try:
            for form in page.locator("form").all():
                try:
                    fh = form.inner_html().lower()
                    if any(p in fh for p in USERNAME_PATTERNS) and any(p in fh for p in PASSWORD_PATTERNS):
                        details["has_login_form"] = True
                        details["has_username_field"] = True
                        details["has_password_field"] = True
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # 查找独立输入框 (SPA/React 无 <form>)
        if not details["has_login_form"]:
            try:
                for inp in page.locator("input:visible").all():
                    try:
                        name = (inp.get_attribute("name") or "").lower()
                        placeholder = (inp.get_attribute("placeholder") or "").lower()
                        itype = (inp.get_attribute("type") or "").lower()
                        if itype == "password":
                            details["has_password_field"] = True
                        combined = name + placeholder
                        if any(p in combined for p in USERNAME_PATTERNS):
                            details["has_username_field"] = True
                    except Exception:
                        continue
            except Exception:
                pass

        # 检测 OAuth/SSO
        try:
            html = page.content().lower()
            if any(p in html for p in ["oauth", "google", "microsoft", "github", "sso", "azure"]):
                details["has_oauth_redirect"] = True
        except Exception:
            pass

        details["login_url"] = current_url if is_login_page else ""
        details["fields"] = self._extract_fields(page)

        # 判断类型: 表单字段优先于关键词匹配
        has_form_fields = details["has_username_field"] or details["has_password_field"]
        if not has_form_fields:
            auth_type = AuthType.NONE
        elif details["has_login_form"] or details["has_password_field"]:
            auth_type = AuthType.FORM   # 有可见表单/密码框 → 表单登录优先
        elif details["has_oauth_redirect"]:
            auth_type = AuthType.OAUTH
        else:
            auth_type = AuthType.FORM  # 默认表单登录

        confidence = auth_detection_confidence(
            has_login_form=details["has_login_form"],
            has_username_field=details["has_username_field"],
            has_password_field=details["has_password_field"],
            has_oauth_redirect=details["has_oauth_redirect"],
            has_sso_domain=False,
        )
        if self.verbose:
            print(f"  🔍 Auth: type={auth_type.value}, conf={confidence:.2f}")
        return auth_type, confidence, details

    def _extract_fields(self, page: Page) -> list[dict]:
        fields = []
        try:
            for inp in page.locator("input:visible").all():
                try:
                    name = inp.get_attribute("name") or ""
                    itype = inp.get_attribute("type") or "text"
                    placeholder = inp.get_attribute("placeholder") or ""
                    fields.append({
                        "name": name, "type": itype,
                        "label": placeholder or name,
                        "placeholder": placeholder,
                    })
                except Exception:
                    continue
        except Exception:
            pass
        return fields


class AuthHandler:
    """认证执行器"""

    def __init__(self, username: str = "", password: str = "",
                 verbose: bool = True):
        self.username = username
        self.password = password
        self.verbose = verbose

    def login(self, page: Page, auth_schema: AuthSchema,
              base_url: str) -> bool:
        """执行认证 — 自动选择最优策略"""
        if auth_schema.type == AuthType.NONE:
            if self.verbose:
                print("  ℹ️ 无需认证")
            return True

        if not (self.username or self.password):
            return True

        # 策略优先级: React Fiber注入 > 标准表单提交 > 按钮点击
        if self._try_react_fiber_submit(page, base_url):
            return True
        if self._try_standard_form(page, base_url):
            return True
        if self._try_button_click(page):
            return True

        return False

    def _try_react_fiber_submit(self, page: Page, base_url: str) -> bool:
        """路径4: 遍历React Fiber树 → 找到onSubmit → script标签注入触发
        这能突破所有React/Next.js的自定义认证机制。"""
        # 等待动态表单
        for i in range(20):
            time.sleep(1)
            if page.locator("input:visible").count() >= 2:
                break
        if page.locator("input:visible").count() == 0:
            return False

        # 填充表单
        try:
            page.locator("input").first.fill(self.username)
            pwds = page.locator("input[type='password']")
            if pwds.count() > 0:
                pwds.first.fill(self.password)
        except Exception:
            return False

        if self.verbose:
            print(f"  ⚛️ 尝试 React Fiber 注入...")

        # 注入script标签 → 遍历fiber → 调用onSubmit (真正fire-and-forget)
        try:
            page.evaluate('''() => {
                const script = document.createElement('script');
                script.textContent = '(' + function() {
                    setTimeout(function() {
                        var form = document.querySelector('form');
                        if (!form) return;
                        var fiberKey = Object.keys(form).find(function(k) {
                            return k.startsWith('__reactFiber');
                        });
                        if (!fiberKey) return;
                        var props = form[fiberKey].pendingProps || form[fiberKey].memoizedProps || {};
                        var onSubmit = props.onSubmit;
                        if (typeof onSubmit !== 'function') return;
                        var fakeEvent = {
                            preventDefault: function() {},
                            currentTarget: form,
                            target: form
                        };
                        onSubmit(fakeEvent);
                    }, 300);
                } + ')()';
                document.body.appendChild(script);
            }''')
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️ Fiber注入失败: {e}")
            return False

        # 等待结果 (检查密码框消失 或 POST请求发出)
        for i in range(12):
            time.sleep(2)
            try:
                if page.locator("input[type='password']:visible").count() == 0:
                    break
            except Exception:
                pass

        logged_in = self._verify(post_login_page=page)
        if self.verbose:
            print(f"  {'✅' if logged_in else '⚠️'} React Fiber {'成功' if logged_in else '待验证'}")
        return logged_in

    def _try_standard_form(self, page: Page, base_url: str) -> bool:
        """标准HTML表单提交 (fallback)"""
        try:
            form = page.locator("form").first
            if form.count() == 0:
                return False
            page.locator("input").first.fill(self.username)
            pwds = page.locator("input[type='password']")
            if pwds.count() > 0:
                pwds.first.fill(self.password)
            # 尝试 requestSubmit
            form.evaluate("el => { try { el.requestSubmit(); } catch(e) {} }")
            time.sleep(5)
            return self._verify(post_login_page=page)
        except Exception:
            return False

    def _try_button_click(self, page: Page) -> bool:
        """按钮点击 (最后fallback)"""
        for btn_text in LOGIN_BTN_PATTERNS:
            try:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                if btn.count() > 0:
                    btn.click(force=True, no_wait_after=True, timeout=5000)
                    time.sleep(5)
                    return self._verify(post_login_page=page)
            except Exception:
                continue
        return False

    def _verify(self, post_login_page: Page) -> bool:
        try:
            # 密码框还在 → 可能还在登录页
            if post_login_page.locator("input[type='password']:visible").count() > 0:
                return False
            html = post_login_page.content().lower()
            indicators = ["logout", "退出", "course", "课程", "learning", "学习",
                          "phase", "lesson", "课时", "module", "dashboard"]
            return any(ind in html for ind in indicators)
        except Exception:
            return True


class SessionManager:
    """会话持久化 — 支持保存/加载 storage_state"""

    def __init__(self, output_dir: Path, verbose: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose

    def save(self, context: BrowserContext, name: str = "default") -> SessionState:
        path = self.output_dir / f"auth_state_{name}.json"
        try:
            context.storage_state(path=str(path))
            cookies_count = len(context.cookies())
        except Exception:
            cookies_count = 0
        return SessionState(
            storage_state_path=str(path) if path.exists() else "",
            cookies_count=cookies_count, logged_in=True,
        )

    def load(self, browser: Browser, name: str = "default") -> Optional[BrowserContext]:
        path = self.output_dir / f"auth_state_{name}.json"
        if not path.exists():
            return None
        if self.verbose:
            print(f"  📂 加载已保存会话: {path}")
        return browser.new_context(storage_state=str(path))


def run_l0_auth(
    page: Page, context: BrowserContext, base_url: str,
    username: str = "", password: str = "",
    output_dir: Path = Path("./output"),
    auth_state_path: str = "",
    verbose: bool = True,
    ask_callback=None,
) -> tuple[AuthSchema, SessionState]:
    """
    L0 认证流程 — 支持预认证模式 + 交互式登录引导

    如果提供了 auth_state_path (已保存的 storage_state),
    则跳过登录直接使用, 大幅加速探索。

    交互式登录 (ask_callback 提供时自动启用):
      标准自动登录失败, 或检测到非标准登录特征 (SSO/扫码/验证码),
      或检测到登录表单但没有凭证时 → 启动 InteractiveLoginAgent,
      以 LLM 对话形式向评测用户询问补充信息 (验证码/登录方式/凭证等),
      用户回答注入浏览器继续尝试。降级: 用户超时/跳过 → 未登录继续探索。

    :param ask_callback: 问答通道 callable(text, options, context, timeout_s) -> dict
    """
    mgr = SessionManager(output_dir=output_dir, verbose=verbose)

    # ── 预认证模式: 加载已保存的会话 ──
    if auth_state_path and Path(auth_state_path).exists():
        if verbose:
            print(f"  🎫 预认证模式: {auth_state_path}")
        return AuthSchema(type=AuthType.NONE, notes="pre-authenticated"), SessionState(
            storage_state_path=auth_state_path, logged_in=True)

    # ── 正常模式: 访问页面并登录 ──
    detector = AuthDetector(verbose=verbose)
    handler = AuthHandler(username=username, password=password, verbose=verbose)

    # 访问目标页面
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto(base_url, wait_until="commit", timeout=20000)
        except Exception:
            pass

    # 等待动态内容
    for i in range(15):
        time.sleep(1)
        if page.locator("input:visible").count() >= 2:
            break
    time.sleep(1)

    # 检测 + 登录
    auth_type, confidence, details = detector.detect(page, base_url)
    auth_schema = AuthSchema(
        type=auth_type,
        login_url=details.get("login_url", ""),
        fields=[AuthField(**f) if isinstance(f, dict) else f for f in details.get("fields", [])],
        notes=f"auto-detected, confidence={confidence:.2f}",
    )

    # 即使用户提供了凭证但检测为 NONE，也尝试登录（表单可能是动态渲染的）
    if auth_type == AuthType.NONE and (username or password):
        if verbose:
            print(f"  🔄 检测无表单，但用户有凭证，强制尝试登录...")
        auth_schema.type = AuthType.FORM

    success = handler.login(page, auth_schema, base_url)

    # ── 交互式登录引导 (LLM 对话 + 用户协作) ──
    # 触发条件: 提供问答通道 且 (登录失败 / 检测到SSO扫码特征 / 有登录表单但无凭证)
    interactive_result = None
    has_oauth_hint = bool(details.get("has_oauth_redirect"))
    has_login_form = auth_type != AuthType.NONE
    should_interact = bool(ask_callback) and (
        not success
        or has_oauth_hint
        or (has_login_form and not (username and password))
    )
    if should_interact:
        try:
            from .l0_interactive import InteractiveLoginAgent
            if verbose:
                print(f"  🤝 启动交互式登录引导 (LLM对话确认登录方式)...")
            agent = InteractiveLoginAgent(
                ask=ask_callback,
                username=username,
                password=password,
                question_timeout=180.0,
                verbose=verbose,
            )
            seed = (
                f"自动检测结果: auth_type={auth_schema.type.value}, "
                f"标准自动登录={'成功' if success else '失败'}, "
                f"检测到SSO/扫码特征={has_oauth_hint}"
            )
            interactive_result = agent.run(page=page, base_url=base_url, seed_notes=seed)
            # 交互式结果附着到 auth_schema (explorer 层读取)
            auth_schema.interactive = interactive_result
            if interactive_result.get("logged_in"):
                success = True
                auth_schema.type = AuthType.FORM  # 交互完成后按已登录处理
                auth_schema.notes = interactive_result.get("notes", auth_schema.notes)
            else:
                auth_schema.notes = f"{auth_schema.notes}; {interactive_result.get('notes', '')}"
        except Exception as e:
            if verbose:
                print(f"  ⚠️ 交互式登录引导异常 (降级继续): {e}")
            try:
                auth_schema.interactive = {
                    "logged_in": False, "degraded": True,
                    "notes": f"interactive failed: {e}", "asked_user": False,
                }
            except Exception:
                pass

    # 保存会话 (供后续预认证复用)
    session_state = mgr.save(context) if success else SessionState()
    if verbose and session_state.storage_state_path:
        print(f"  💾 会话已保存 (预认证文件): {session_state.storage_state_path}")

    return auth_schema, session_state
