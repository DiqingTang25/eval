"""
L0: 认证与会话层 (Auth & Session)

借鉴: balage-core (ML表单识别 F1=0.93 — Phase 1用确定性规则替代ML)
      Periscope MCP (74工具, 含 interactive_login 处理 2FA/SSO)
      Vespasian auth injection

职责: 自动检测认证类型 → 执行登录 → 持久化会话
输出: auth_state.json + AuthSchema
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

from .models import (
    AuthType, AuthSchema, AuthField, SessionState,
)
from .confidence import auth_detection_confidence

# ── 常见登录表单关键词 ──
LOGIN_URL_PATTERNS = [
    "/login", "/signin", "/auth", "/account/login", "/user/login",
    "/oauth", "/sso", "/cas", "/auth/login", "/api/auth/login",
]

USERNAME_FIELD_PATTERNS = [
    "username", "user", "account", "email", "phone", "mobile",
    "login", "name", "userid", "user_id", "学号", "工号", "姓名",
]

PASSWORD_FIELD_PATTERNS = [
    "password", "passwd", "pwd", "pass", "pin", "密码",
]

LOGIN_BUTTON_PATTERNS = [
    "登录", "登入", "sign in", "login", "进入", "submit", "提交",
    "log in", "signin",
]


class AuthDetector:
    """认证类型检测器 (Phase 1: 确定性规则版, Phase 2 可升级为 balage-core ML)"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def detect(self, page: Page, base_url: str) -> tuple[AuthType, float, dict]:
        """
        检测认证类型
        :returns: (auth_type, confidence, detection_details)
        """
        details = {
            "has_login_form": False,
            "has_username_field": False,
            "has_password_field": False,
            "has_oauth_redirect": False,
            "has_sso_domain": False,
            "login_url": "",
            "fields": [],
        }

        current_url = page.url

        # 1. 检查当前页面是否就是登录页
        parsed = urlparse(current_url)
        is_login_page = any(p in parsed.path.lower() for p in LOGIN_URL_PATTERNS)

        # 2. 查找页面上的表单
        forms = page.locator("form").all()
        login_form = None

        for form in forms:
            form_html = form.inner_html().lower()
            # 检查是否包含用户名/密码字段
            has_user = any(p in form_html for p in USERNAME_FIELD_PATTERNS)
            has_pass = any(p in form_html for p in PASSWORD_FIELD_PATTERNS)
            if has_user and has_pass:
                login_form = form
                details["has_login_form"] = True
                details["has_username_field"] = True
                details["has_password_field"] = True
                break

        # 3. 如果没找到完整表单, 检查单个输入框
        if not login_form:
            # 查找所有 input 元素
            inputs = page.locator("input").all()
            for inp in inputs:
                try:
                    name = (inp.get_attribute("name") or "").lower()
                    placeholder = (inp.get_attribute("placeholder") or "").lower()
                    input_type = (inp.get_attribute("type") or "").lower()

                    if input_type == "password":
                        details["has_password_field"] = True
                    elif any(p in name + placeholder for p in USERNAME_FIELD_PATTERNS):
                        details["has_username_field"] = True
                except Exception:
                    continue

        # 4. 收集登录字段详情
        if details["has_username_field"] or details["has_password_field"]:
            details["login_url"] = current_url if is_login_page else ""
            details["fields"] = self._extract_form_fields(page)

        # 5. 检测 OAuth/SSO
        page_text = page.content().lower()
        if "oauth" in page_text or "第三方登录" in page_text or "authorize" in page_text:
            details["has_oauth_redirect"] = True
        if "sso" in page_text or "统一认证" in page_text or "cas" in page_text:
            details["has_sso_domain"] = True

        # 6. 综合判断认证类型
        if not details["has_username_field"] and not details["has_password_field"]:
            # 检查是否有重定向到登录页
            if "login" in current_url.lower() or "auth" in current_url.lower():
                auth_type = AuthType.UNKNOWN
            else:
                auth_type = AuthType.NONE  # 可能无需认证
        elif details["has_sso_domain"]:
            auth_type = AuthType.SSO
        elif details["has_oauth_redirect"]:
            auth_type = AuthType.OAUTH
        elif details["has_login_form"]:
            auth_type = AuthType.FORM
        else:
            auth_type = AuthType.FORM  # 默认假设表单登录

        confidence = auth_detection_confidence(
            has_login_form=details["has_login_form"],
            has_username_field=details["has_username_field"],
            has_password_field=details["has_password_field"],
            has_oauth_redirect=details["has_oauth_redirect"],
            has_sso_domain=details["has_sso_domain"],
        )

        if self.verbose:
            print(f"  🔍 Auth 检测: type={auth_type.value}, confidence={confidence:.2f}")

        return auth_type, confidence, details

    def _extract_form_fields(self, page: Page) -> list[dict]:
        """提取登录表单字段信息"""
        fields = []
        inputs = page.locator("input:visible").all()
        for inp in inputs:
            try:
                name = inp.get_attribute("name") or ""
                input_type = inp.get_attribute("type") or "text"
                placeholder = inp.get_attribute("placeholder") or ""
                label = ""
                # 尝试找关联的 label
                try:
                    label_el = inp.locator(".. label, .. .label").first
                    label = label_el.inner_text() if label_el else ""
                except Exception:
                    pass

                if input_type in ("text", "password", "email", "tel", "number"):
                    fields.append({
                        "name": name,
                        "type": input_type,
                        "label": label or placeholder or name,
                        "required": inp.get_attribute("required") is not None,
                        "placeholder": placeholder,
                    })
            except Exception:
                continue
        return fields


class AuthHandler:
    """认证执行器"""

    def __init__(self, username: str = "", password: str = "",
                 verbose: bool = True):
        self.username = username
        self.password = password
        self.verbose = verbose

    def login_form(
        self, page: Page, auth_schema: AuthSchema, base_url: str
    ) -> bool:
        """处理表单登录 (借鉴 Periscope MCP 的 form_login 工具)"""
        login_url = auth_schema.login_url or urljoin(base_url, "/login")

        if self.verbose:
            print(f"  🔑 表单登录: {login_url}")

        # 导航到登录页
        if page.url != login_url:
            page.goto(login_url, wait_until="networkidle", timeout=30000)
            time.sleep(2)

        success = False

        # 策略1: 按字段 name/placeholder 精确填充
        for field in auth_schema.fields:
            try:
                field_type = field.get("type", "text")
                field_name = field.get("name", "")

                if field_type == "password":
                    value = self.password
                elif any(kw in field_name.lower() for kw in ["email", "mail"]):
                    value = self.username if "@" in self.username else ""
                elif any(kw in field_name.lower() for kw in ["phone", "mobile", "tel"]):
                    value = self.username if self.username.isdigit() else ""
                else:
                    value = self.username

                if not value:
                    continue

                # 尝试多种选择器
                selectors = [
                    f"input[name='{field_name}']",
                    f"input[placeholder*='{field.get('placeholder', '')}']" if field.get("placeholder") else "",
                    f"input[type='{field_type}']",
                ]
                filled = False
                for sel in selectors:
                    if not sel:
                        continue
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=2000):
                            el.click()
                            el.fill(value)
                            filled = True
                            if self.verbose:
                                print(f"    ✓ 填充 {field_name}: {value[:3]}***")
                            break
                    except Exception:
                        continue

                if not filled and self.verbose:
                    print(f"    ⚠ 未找到字段: {field_name}")

            except Exception as e:
                if self.verbose:
                    print(f"    ⚠ 填充失败 {field.get('name', '?')}: {e}")

        # 点击登录按钮
        try:
            for btn_text in LOGIN_BUTTON_PATTERNS:
                try:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        success = True
                        break
                except Exception:
                    continue

            if not success:
                # 尝试 type=submit
                try:
                    btn = page.locator("button[type='submit'], input[type='submit']").first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        success = True
                except Exception:
                    pass

            if not success:
                # 按 Enter
                page.keyboard.press("Enter")
                success = True

        except Exception as e:
            if self.verbose:
                print(f"    ❌ 登录提交失败: {e}")

        # 等待登录结果
        time.sleep(3)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # 验证登录成功 (URL变化 或 不再有登录表单)
        logged_in = "login" not in page.url.lower() or self._check_logged_in(page)

        if self.verbose:
            status = "✅" if logged_in else "❌"
            print(f"  {status} 登录{'成功' if logged_in else '失败'} (当前URL: {page.url[:80]})")

        return logged_in

    def _check_logged_in(self, page: Page) -> bool:
        """检测是否已登录"""
        try:
            page_text = page.content().lower()
            logout_indicators = ["logout", "退出", "登出", "profile", "个人中心", "我的"]
            return any(ind in page_text for ind in logout_indicators)
        except Exception:
            return False

    def login_interactive(self, page: Page, reason: str = "") -> bool:
        """
        交互式登录 (处理 2FA/SSO/验证码)
        借鉴 Periscope MCP interactive_login: 打开可见窗口, 等待人工完成
        """
        if self.verbose:
            print(f"  🖐 需要交互式登录: {reason}")
            print(f"  请在浏览器中完成登录, 完成后按 Enter 继续...")
        input("  > 按 Enter 继续...")
        return True


class SessionManager:
    """会话持久化管理器"""

    def __init__(self, output_dir: Path, verbose: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose

    def save(self, context: BrowserContext, name: str = "default") -> SessionState:
        """保存浏览器存储状态到文件"""
        storage_path = self.output_dir / f"auth_state_{name}.json"
        context.storage_state(path=str(storage_path))

        state = SessionState(
            storage_state_path=str(storage_path),
            cookies_count=len(context.cookies()),
            logged_in=True,
        )

        if self.verbose:
            print(f"  💾 会话已保存: {storage_path} ({state.cookies_count} cookies)")

        return state

    def load(self, browser: Browser, name: str = "default") -> Optional[BrowserContext]:
        """从文件恢复浏览器上下文"""
        storage_path = self.output_dir / f"auth_state_{name}.json"
        if not storage_path.exists():
            return None

        context = browser.new_context(storage_state=str(storage_path))
        if self.verbose:
            print(f"  📂 会话已加载: {storage_path}")

        return context


def run_l0_auth(
    page: Page,
    context: BrowserContext,
    base_url: str,
    username: str = "",
    password: str = "",
    output_dir: Path = Path("./output"),
    verbose: bool = True,
) -> tuple[AuthSchema, SessionState]:
    """
    L0 完整流程: 检测 → 登录 → 持久化

    :returns: (auth_schema, session_state)
    """
    detector = AuthDetector(verbose=verbose)
    handler = AuthHandler(username=username, password=password, verbose=verbose)
    session_mgr = SessionManager(output_dir=output_dir, verbose=verbose)

    # Step 1: 检测认证类型
    auth_type, confidence, details = detector.detect(page, base_url)

    # Step 2: 构建 AuthSchema
    auth_schema = AuthSchema(
        type=auth_type,
        login_url=details.get("login_url", ""),
        fields=[AuthField(**f) for f in details.get("fields", [])],
        has_captcha=False,  # Phase 1 不检测验证码
        has_mfa=False,
        notes=f"auto-detected, confidence={confidence:.2f}",
    )

    # Step 3: 执行登录 (如果需要)
    session_state = SessionState()
    if auth_type == AuthType.NONE:
        if verbose:
            print("  ℹ️ 无需认证, 跳过登录")
        session_state = SessionManager(output_dir).save(context)

    elif auth_type in (AuthType.FORM, AuthType.UNKNOWN):
        success = handler.login_form(page, auth_schema, base_url)
        if success:
            session_state = session_mgr.save(context)
        elif auth_type == AuthType.UNKNOWN:
            # 交互式登录兜底
            handler.login_interactive(page, "未知认证类型, 请人工登录")
            session_state = session_mgr.save(context)

    elif auth_type in (AuthType.OAUTH, AuthType.SSO, AuthType.MFA):
        # 复杂认证: 交互式
        handler.login_interactive(
            page, f"{auth_type.value} 认证需要人工完成 (如在浏览器中点击授权按钮)"
        )
        session_state = session_mgr.save(context)

    return auth_schema, session_state
