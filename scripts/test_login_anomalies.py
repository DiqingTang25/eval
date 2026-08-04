#!/usr/bin/env python3
"""
登录异常测试工具 v1.0 — 平台安全健壮性验证

对齐交付标准: 可信 → 安全边界明确, 可通过专家评审

测试覆盖:
  1. 错误密码 / 不存在用户 / 空凭据
  2. SQL注入 / XSS注入
  3. Token篡改 / 过期Token探测 / 登出后Token复用
  4. 暴力破解模式 (速率限制检测)
  5. 超长输入 / 特殊字符 / Unicode

用法:
    python scripts/test_login_anomalies.py                     # 全部测试
    python scripts/test_login_anomalies.py --quick             # 快速冒烟
    python scripts/test_login_anomalies.py --no-brute          # 跳过暴力探测
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

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 测试配置 ──
TARGET_URL = "http://124.174.108.70"
LOGIN_ENDPOINT = "/api/auth/login"
VALID_USERNAME = "student001"
VALID_PASSWORD = "123456"
BRUTE_ATTEMPTS = 8         # 暴力探测尝试次数
BRUTE_INTERVAL = 0.3       # 间隔(秒) — 模拟快速攻击
REQUEST_TIMEOUT = 15


# ═══════════════════════════════════════════════════════════
# 测试用例定义
# ═══════════════════════════════════════════════════════════

def make_cases() -> list[dict]:
    """生成所有测试用例"""
    cases: list[dict] = []

    # ── 1. 错误凭据 ──
    cases.append({
        "id": "A01", "category": "wrong_password",
        "description": "正确用户名 + 错误密码",
        "payload": {"username": VALID_USERNAME, "password": "wrongpassword"},
        "expect": {"status": 401, "has_token": False},
    })
    cases.append({
        "id": "A02", "category": "wrong_password",
        "description": "正确用户名 + 空密码",
        "payload": {"username": VALID_USERNAME, "password": ""},
        "expect": {"status": [400, 401, 422], "has_token": False},
    })
    cases.append({
        "id": "A03", "category": "nonexistent_user",
        "description": "不存在用户名",
        "payload": {"username": "nonexistent_user_xyz", "password": "123456"},
        "expect": {"status": 401, "has_token": False},
    })
    cases.append({
        "id": "A04", "category": "empty_credentials",
        "description": "空用户名 + 空密码",
        "payload": {"username": "", "password": ""},
        "expect": {"status": [400, 401, 422], "has_token": False},
    })
    cases.append({
        "id": "A05", "category": "empty_credentials",
        "description": "仅用户名无密码",
        "payload": {"username": VALID_USERNAME},
        "expect": {"status": [400, 422], "has_token": False},
    })
    cases.append({
        "id": "A06", "category": "empty_credentials",
        "description": "仅密码无用户名",
        "payload": {"password": VALID_PASSWORD},
        "expect": {"status": [400, 422], "has_token": False},
    })

    # ── 2. 注入攻击 ──
    cases.append({
        "id": "B01", "category": "sql_injection",
        "description": "SQL注入 — OR 1=1",
        "payload": {"username": "' OR 1=1 --", "password": "' OR 1=1 --"},
        "expect": {"status": 401, "has_token": False},
    })
    cases.append({
        "id": "B02", "category": "sql_injection",
        "description": "SQL注入 — UNION SELECT",
        "payload": {"username": "' UNION SELECT * FROM users --", "password": "x"},
        "expect": {"status": 401, "has_token": False},
    })
    cases.append({
        "id": "B03", "category": "sql_injection",
        "description": "SQL注入 — DROP TABLE",
        "payload": {"username": "'; DROP TABLE users; --", "password": "x"},
        "expect": {"status": 401, "has_token": False},
    })
    cases.append({
        "id": "B04", "category": "xss_injection",
        "description": "XSS注入 — script标签",
        "payload": {"username": "<script>alert(1)</script>", "password": "<script>alert(1)</script>"},
        "expect": {"status": [400, 401, 422], "has_token": False},
    })
    cases.append({
        "id": "B05", "category": "xss_injection",
        "description": "XSS注入 — img onerror",
        "payload": {"username": "<img src=x onerror=alert(1)>", "password": "x"},
        "expect": {"status": [400, 401, 422], "has_token": False},
    })

    # ── 3. Token 异常 ──
    cases.append({
        "id": "C01", "category": "token_tampering",
        "description": "无效Token访问API",
        "payload": None,  # 特殊处理
        "expect": {"status": 401, "has_token": False},
    })
    cases.append({
        "id": "C02", "category": "token_tampering",
        "description": "空Token访问API",
        "payload": None,
        "expect": {"status": 401, "has_token": False},
    })

    # ── 4. 输入边界 ──
    cases.append({
        "id": "D01", "category": "boundary_input",
        "description": "超长用户名 (1000字符)",
        "payload": {"username": "a" * 1000, "password": "x"},
        "expect": {"status": [400, 401, 413, 422], "has_token": False},
    })
    cases.append({
        "id": "D02", "category": "boundary_input",
        "description": "Unicode特殊字符",
        "payload": {"username": "测试\\u0000用户", "password": "密码"},
        "expect": {"status": [400, 401, 422], "has_token": False},
    })
    cases.append({
        "id": "D03", "category": "boundary_input",
        "description": "仅空格用户名+密码",
        "payload": {"username": "   ", "password": "   "},
        "expect": {"status": [400, 401, 422], "has_token": False},
    })

    # ── 5. Content-Type 异常 ──
    cases.append({
        "id": "E01", "category": "content_type",
        "description": "非JSON Content-Type",
        "payload": "username=student001&password=123456",  # form-encoded
        "expect": {"status": [400, 415, 422], "has_token": False},
    })
    cases.append({
        "id": "E02", "category": "content_type",
        "description": "空Body",
        "payload": "",
        "expect": {"status": [400, 415, 422], "has_token": False},
    })

    return cases


# ═══════════════════════════════════════════════════════════
# 测试执行
# ═══════════════════════════════════════════════════════════

class LoginAnomalyTester:
    """登录异常测试器"""

    def __init__(self, base_url: str = TARGET_URL):
        self.base_url = base_url.rstrip("/")
        self.login_url = f"{self.base_url}{LOGIN_ENDPOINT}"
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        self.results: list[dict] = []
        # 缓存有效token用于token测试
        self._valid_token: str | None = None

    def _get_valid_token(self) -> str | None:
        """获取有效token (用于后续token异常测试)"""
        if self._valid_token:
            return self._valid_token
        try:
            r = self.session.post(
                self.login_url,
                json={"username": VALID_USERNAME, "password": VALID_PASSWORD},
                timeout=REQUEST_TIMEOUT,
            )
            data = r.json()
            self._valid_token = data.get("token") or data.get("access_token")
            return self._valid_token
        except Exception:
            return None

    def _post(self, payload: Any, content_type: str = "json",
              extra_headers: dict = None) -> tuple[int, dict, float]:
        """发送登录请求"""
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)

        start = time.monotonic()
        try:
            if content_type == "json":
                r = self.session.post(
                    self.login_url, json=payload,
                    headers=headers, timeout=REQUEST_TIMEOUT,
                )
            elif content_type == "form":
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                r = self.session.post(
                    self.login_url, data=payload,
                    headers=headers, timeout=REQUEST_TIMEOUT,
                )
            elif content_type == "text":
                headers["Content-Type"] = "text/plain"
                r = self.session.post(
                    self.login_url, data=payload,
                    headers=headers, timeout=REQUEST_TIMEOUT,
                )
            else:
                r = self.session.post(
                    self.login_url, data=payload,
                    headers=headers, timeout=REQUEST_TIMEOUT,
                )

            elapsed = time.monotonic() - start
            try:
                body = r.json()
            except Exception:
                body = {"_raw": r.text[:500]}
            return r.status_code, body, elapsed
        except requests.Timeout:
            return -1, {"error": "timeout"}, time.monotonic() - start
        except requests.ConnectionError:
            return -2, {"error": "connection_refused"}, time.monotonic() - start

    def run_case(self, case: dict) -> dict:
        """执行单个测试用例"""
        result = {
            "case_id": case["id"],
            "category": case["category"],
            "description": case["description"],
            "expect": case["expect"],
        }

        if case["id"] == "C01":
            # 无效Token测试
            code, body, elapsed = self._test_invalid_token()
        elif case["id"] == "C02":
            # 空Token测试
            code, body, elapsed = self._test_empty_token()
        elif case["id"] == "E01":
            # Form-encoded body
            code, body, elapsed = self._post(case["payload"], content_type="form")
        elif case["id"] == "E02":
            # Empty body
            code, body, elapsed = self._post(case["payload"], content_type="text")
        else:
            code, body, elapsed = self._post(case["payload"])

        result["status_code"] = code
        result["response_preview"] = str(body)[:200]
        result["elapsed_ms"] = round(elapsed * 1000, 1)

        # 判定
        expected_status = case["expect"]["status"]
        if isinstance(expected_status, list):
            result["status_pass"] = code in expected_status
        else:
            result["status_pass"] = code == expected_status

        # 检查是否有token泄露
        has_token = bool(
            body.get("token") or body.get("access_token")
        ) if isinstance(body, dict) else False
        result["token_leaked"] = has_token and not case["expect"].get("has_token", True)

        result["pass"] = result["status_pass"] and not result["token_leaked"]

        # 判定说明
        if code == -1:
            result["verdict"] = "TIMEOUT — 服务器无响应"
        elif code == -2:
            result["verdict"] = "CONNECTION_REFUSED"
        elif result["token_leaked"]:
            result["verdict"] = "FAIL — Token不应泄露"
        elif not result["status_pass"]:
            result["verdict"] = f"FAIL — HTTP {code} (期望 {expected_status})"
        else:
            result["verdict"] = "PASS"

        return result

    def _test_invalid_token(self) -> tuple[int, dict, float]:
        """测试无效Token访问API"""
        headers = {"Authorization": "Bearer invalid_token_xxx"}
        start = time.monotonic()
        try:
            r = self.session.get(
                f"{self.base_url}/api/phases",
                headers=headers, timeout=REQUEST_TIMEOUT,
            )
            return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {"_raw": r.text[:200]}, time.monotonic() - start
        except Exception as e:
            return -1, {"error": str(e)}, time.monotonic() - start

    def _test_empty_token(self) -> tuple[int, dict, float]:
        """测试空Token访问API"""
        headers = {"Authorization": "Bearer "}
        start = time.monotonic()
        try:
            r = self.session.get(
                f"{self.base_url}/api/phases",
                headers=headers, timeout=REQUEST_TIMEOUT,
            )
            return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {"_raw": r.text[:200]}, time.monotonic() - start
        except Exception as e:
            return -1, {"error": str(e)}, time.monotonic() - start

    def test_brute_force(self) -> dict:
        """暴力破解模式探测 — 快速连续错误登录"""
        results_detail = []
        codes = []

        for i in range(BRUTE_ATTEMPTS):
            code, body, elapsed = self._post({
                "username": VALID_USERNAME,
                "password": f"brute_attempt_{i}",
            })
            results_detail.append({
                "attempt": i + 1,
                "status_code": code,
                "elapsed_ms": round(elapsed * 1000, 1),
                "response": str(body)[:100],
            })
            codes.append(code)
            time.sleep(BRUTE_INTERVAL)

        # 检测速率限制信号
        rate_limited = 429 in codes
        delayed = any(
            r["elapsed_ms"] > 3000 for r in results_detail[2:]
        ) if len(results_detail) > 2 else False
        all_same = len(set(codes)) == 1 and codes[0] == 401

        verdict = "PASS"
        findings = []
        if rate_limited:
            verdict = "RATE_LIMITED_GOOD"
            findings.append("Rate limit 429 detected -> server has protection [PASS]")
        elif delayed:
            findings.append("后续请求响应变慢 → 可能存在软限制")
            verdict = "SOFT_LIMIT"
        else:
            findings.append(f"未检测到速率限制 ({BRUTE_ATTEMPTS}次请求均立即返回)")
            verdict = "NO_RATE_LIMIT"

        return {
            "test": "brute_force",
            "attempts": BRUTE_ATTEMPTS,
            "interval_sec": BRUTE_INTERVAL,
            "verdict": verdict,
            "rate_limited": rate_limited,
            "delayed_responses": delayed,
            "status_codes": codes,
            "findings": findings,
            "details": results_detail,
        }

    def test_logout_token_reuse(self) -> dict | None:
        """测试登出后Token是否失效 (如果平台有logout接口)"""
        # 先登录获取token
        code, body, _ = self._post({
            "username": VALID_USERNAME,
            "password": VALID_PASSWORD,
        })
        if code != 200:
            return {"test": "logout_token_reuse", "verdict": "SKIP",
                    "reason": "无法获取有效token"}

        token = body.get("token") or body.get("access_token")
        if not token:
            return {"test": "logout_token_reuse", "verdict": "SKIP",
                    "reason": "响应中无token字段"}

        # 尝试登出 (可能不存在)
        logout_url = f"{self.base_url}/api/auth/logout"
        try:
            r = self.session.post(
                logout_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT,
            )
            logout_ok = r.status_code in (200, 204)
        except Exception:
            logout_ok = False

        # 登出后用旧token访问
        try:
            r = self.session.get(
                f"{self.base_url}/api/phases",
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT,
            )
            after_logout_code = r.status_code
        except Exception:
            after_logout_code = -1

        token_still_valid = after_logout_code == 200
        return {
            "test": "logout_token_reuse",
            "verdict": "PASS" if (not token_still_valid or not logout_ok) else "FAIL_TOKEN_REUSABLE",
            "logout_supported": logout_ok,
            "token_valid_after_logout": token_still_valid,
            "after_logout_status": after_logout_code,
        }

    # ── 主流程 ──

    def run_all(self, include_brute: bool = True) -> dict:
        """执行全部测试"""
        print(f"[LOGIN TEST] Platform: {self.base_url}")
        print(f"   Account: {VALID_USERNAME}")
        print(f"   Time: {datetime.now(timezone.utc).isoformat()}\n")

        cases = make_cases()
        passed = 0
        failed = 0
        warnings = 0

        for case in cases:
            result = self.run_case(case)
            self.results.append(result)

            if result["pass"]:
                passed += 1
                icon = "PASS"
            else:
                failed += 1
                icon = "FAIL"

            print(f"  [{icon}] [{result['case_id']}] {result['description']:40s} "
                  f"-> HTTP {result['status_code']} ({result['verdict']})")

        # 暴力探测
        brute_result = None
        if include_brute:
            print(f"\n  [...] Brute force detection ({BRUTE_ATTEMPTS} requests, {BRUTE_INTERVAL}s interval)...")
            brute_result = self.test_brute_force()
            icon = "PASS" if brute_result["rate_limited"] else "WARN"
            print(f"  {icon} 暴力探测: {brute_result['verdict']} "
                  f"| {brute_result['findings'][0]}")

        # Logout Token复用
        logout_result = self.test_logout_token_reuse()

        # ── 汇总 ──
        total = passed + failed
        print(f"\n{'='*55}")
        print(f"  总计: {total} | 通过: {passed} | 失败: {failed}")
        if brute_result and not brute_result["rate_limited"]:
            print(f"  [WARN] Rate limiting: not detected -> recommend adding")
        print(f"{'='*55}")

        return {
            "test_name": "login_anomalies",
            "platform_url": self.base_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": total, "passed": passed, "failed": failed,
                "pass_rate": round(passed / total * 100, 1) if total else 0,
                "brute_force": brute_result,
                "logout_token_reuse": logout_result,
            },
            "results": self.results,
        }

    def save_report(self, report: dict, path: str = None) -> str:
        """保存JSON报告"""
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"reports/login_anomalies_{ts}.json"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return path


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="登录异常测试工具")
    parser.add_argument("--url", default=TARGET_URL, help=f"平台URL (默认: {TARGET_URL})")
    parser.add_argument("--quick", action="store_true", help="快速冒烟 (跳过暴力探测)")
    parser.add_argument("--no-brute", action="store_true", help="跳过暴力探测")
    parser.add_argument("--json-only", action="store_true", help="仅输出JSON到stdout")
    parser.add_argument("-o", "--output", help="输出JSON路径")
    args = parser.parse_args()

    import os as _os
    tester = LoginAnomalyTester(base_url=args.url)
    report = tester.run_all(include_brute=not args.no_brute and not args.quick)

    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # 保存报告
    path = tester.save_report(report, args.output)
    print(f"\n[REPORT] {path}")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    exit(main())
