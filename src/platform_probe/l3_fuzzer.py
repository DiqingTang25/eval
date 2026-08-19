"""
L3.5: 参数Fuzzing层 (Parameter Fuzzing & IDOR Detection)

借鉴: 黑盒API盲猜方法论
      RESTful规律推断 + 边界值测试

职责:
  1. 对参数化端点进行参数篡改 (ID替换/边界值/特殊字符)
  2. 重放请求并比较响应 (状态码/长度/内容差异)
  3. 检测潜在IDOR (水平越权) 和隐藏资源

用法:
  from .l3_fuzzer import ParameterFuzzer
  fuzzer = ParameterFuzzer(base_url, jwt_token)
  findings = fuzzer.fuzz_all(classified_endpoints)
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests

from .models import ClassifiedEndpoint, APICategory


# ── Fuzz payload: 参数替换候选值 ──
ID_FUZZ_VALUES = [
    ("0", "zero_boundary"),
    ("-1", "negative_boundary"),
    ("999999", "large_id"),
    ("admin", "admin_string"),
    ("1", "adjacent_id"),
    ("2", "adjacent_id"),
    ("' OR '1'='1", "sql_injection"),
    ("../../../etc/passwd", "path_traversal"),
]

# ── 高价值参数名 (优先fuzz) ──
HIGH_VALUE_PARAMS = {
    "id", "user_id", "student_id", "lesson_id", "step_id",
    "course_id", "quiz_id", "phase_id", "order_id",
    "conversation_id", "message_id", "file_id",
}


class ParameterFuzzer:
    """
    参数Fuzzer — 对捕获的API端点进行参数篡改测试

    三种策略:
      1. ID替换: 路径/查询参数中的数字ID → 替换为相邻值
      2. 边界值: 0, -1, 超大值
      3. 注入探测: SQL/路径遍历 (非破坏性)

    输出: 发现列表 [{endpoint, original_status, fuzz_status, risk_level, detail}]
    """

    def __init__(self, base_url: str, jwt_token: str = "",
                 verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.jwt_token = jwt_token
        self.verbose = verbose
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "PlatformExplorer-Fuzzer/1.0",
            "Accept": "application/json",
        })
        if jwt_token:
            self._session.headers["Authorization"] = f"Bearer {jwt_token}"

    def fuzz_all(self, endpoints: list[ClassifiedEndpoint],
                 max_per_endpoint: int = 4) -> list[dict]:
        """
        对所有端点进行fuzz测试

        :param endpoints: 分类后的端点列表
        :param max_per_endpoint: 每个端点最多尝试的fuzz值数量
        :returns: findings列表
        """
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"L3.5: 参数Fuzzing — {len(endpoints)} 个端点")
            print(f"{'='*60}")

        all_findings = []

        # 筛选有参数的端点
        fuzzable = [ep for ep in endpoints
                    if ep.parameters and (
                        ep.parameters.get("path") or
                        ep.parameters.get("query")
                    )]

        if self.verbose:
            print(f"  🎯 可Fuzz端点: {len(fuzzable)}/{len(endpoints)}")

        for ep in fuzzable:
            findings = self._fuzz_one(ep, max_per_endpoint)
            all_findings.extend(findings)

        # 分类汇总
        high_risk = [f for f in all_findings if f["risk"] == "high"]
        medium_risk = [f for f in all_findings if f["risk"] == "medium"]

        if self.verbose:
            print(f"\n  📊 Fuzz完成:")
            print(f"     🔴 高风险: {len(high_risk)} (可能IDOR/信息泄露)")
            print(f"     🟡 中风险: {len(medium_risk)} (响应差异)")
            print(f"     ⚪ 测试总数: {len(all_findings)}")

        return all_findings

    def _fuzz_one(self, ep: ClassifiedEndpoint,
                  max_values: int) -> list[dict]:
        """对单个端点fuzz"""
        findings = []
        path_params = ep.parameters.get("path", {})
        query_params = ep.parameters.get("query", {})

        # 找到原始请求中的参数值
        original_url = ep.path
        parsed = urlparse(original_url)
        original_path = parsed.path
        original_query = parse_qs(parsed.query)

        # 先发送原始请求获取基线
        baseline = self._safe_request(ep.method, original_url)
        if baseline is None:
            return findings

        baseline_status = baseline.status_code
        baseline_len = len(baseline.text)
        baseline_json = self._try_json(baseline)

        # ── 策略1: 路径参数ID替换 ──
        for param_name in path_params:
            if param_name not in HIGH_VALUE_PARAMS:
                continue
            # 从原始路径提取当前值
            segments = original_path.split("/")
            for i, seg in enumerate(segments):
                if not (seg.isdigit() or (len(seg) == 36 and seg.count("-") == 4)):
                    continue
                original_val = seg
                for fuzz_val, fuzz_type in ID_FUZZ_VALUES[:max_values]:
                    fuzzed_path = "/".join(
                        segments[:i] + [fuzz_val] + segments[i + 1:]
                    )
                    fuzzed_url = urlunparse((
                        parsed.scheme, parsed.netloc,
                        fuzzed_path, parsed.params,
                        parsed.query, parsed.fragment,
                    ))
                    finding = self._compare_response(
                        ep, fuzzed_url, fuzz_val, fuzz_type,
                        baseline_status, baseline_len, baseline_json,
                    )
                    if finding:
                        findings.append(finding)

        # ── 策略2: 查询参数值替换 ──
        for param_name, param_type in query_params.items():
            if param_name not in HIGH_VALUE_PARAMS:
                continue
            original_val = original_query.get(param_name, [""])[0]
            if not original_val:
                continue

            for fuzz_val, fuzz_type in ID_FUZZ_VALUES[:max_values]:
                new_query = original_query.copy()
                new_query[param_name] = [fuzz_val]
                fuzzed_url = urlunparse((
                    parsed.scheme, parsed.netloc,
                    parsed.path, parsed.params,
                    urlencode(new_query, doseq=True),
                    parsed.fragment,
                ))
                finding = self._compare_response(
                    ep, fuzzed_url, fuzz_val, fuzz_type,
                    baseline_status, baseline_len, baseline_json,
                )
                if finding:
                    findings.append(finding)

        return findings

    def _compare_response(
        self, ep: ClassifiedEndpoint, fuzzed_url: str,
        fuzz_val: str, fuzz_type: str,
        baseline_status: int, baseline_len: int,
        baseline_json: Optional[dict],
    ) -> Optional[dict]:
        """比较fuzz响应与基线 — 检测异常"""
        resp = self._safe_request("GET", fuzzed_url)
        if resp is None:
            return None

        status = resp.status_code
        length = len(resp.text)
        resp_json = self._try_json(resp)

        risk = None
        detail = ""

        # ── 风险判定规则 ──

        # 规则1: fuzz值返回200且响应体显著不同 → 可能IDOR
        if (status == 200 and baseline_status == 200 and
                resp_json and baseline_json and
                resp_json != baseline_json):
            # 检查是否返回了不同的数据 (不是error message)
            if not self._is_error_response(resp_json):
                risk = "high"
                detail = (
                    f"IDOR风险: {fuzz_type}={fuzz_val} 返回了不同数据. "
                    f"原始长度={baseline_len}, Fuzz长度={length}"
                )

        # 规则2: fuzz值返回200但原始返回403/401 → 权限绕过
        if status == 200 and baseline_status in (401, 403):
            risk = "high"
            detail = (
                f"权限绕过: {fuzz_type}={fuzz_val} 绕过认证 "
                f"(原始={baseline_status} → Fuzz={status})"
            )

        # 规则3: fuzz值返回不同状态码但非404 → 端点行为异常
        if (status != baseline_status and
            status not in (404, 405, 501) and
            abs(length - baseline_len) > 100):
            risk = "medium"
            detail = (
                f"响应差异: {fuzz_type}={fuzz_val} "
                f"status {baseline_status}→{status}, "
                f"len {baseline_len}→{length}"
            )

        # 规则4: 返回500 → 可能触发服务端异常
        if status >= 500:
            risk = "medium"
            detail = (
                f"服务端异常: {fuzz_type}={fuzz_val} 触发 {status}"
            )

        if risk:
            if self.verbose:
                icon = "🔴" if risk == "high" else "🟡"
                print(f"  {icon} [{risk.upper()}] {fuzzed_url[:100]}")
                print(f"     {detail[:120]}")

            return {
                "endpoint": ep.path,
                "method": ep.method,
                "fuzzed_url": fuzzed_url,
                "fuzz_type": fuzz_type,
                "fuzz_value": fuzz_val,
                "baseline_status": baseline_status,
                "fuzz_status": status,
                "baseline_length": baseline_len,
                "fuzz_length": length,
                "risk": risk,
                "detail": detail,
                "category": ep.category.value,
            }

        return None

    def _safe_request(self, method: str, url: str,
                      timeout: int = 10) -> Optional[requests.Response]:
        """安全发送HTTP请求"""
        try:
            full_url = url if url.startswith("http") else urljoin(self.base_url, url)
            return self._session.request(
                method, full_url, timeout=timeout,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.ConnectionError:
            return None
        except Exception:
            return None

    @staticmethod
    def _try_json(resp: requests.Response) -> Optional[dict]:
        """尝试解析JSON响应"""
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _is_error_response(data: dict) -> bool:
        """判断响应是否为错误信息 (而非业务数据)"""
        error_keys = {"error", "errors", "message", "statusCode",
                      "status_code", "exception"}
        # 如果顶层只有error相关key → 是错误响应
        top_keys = set(k.lower() for k in data.keys())
        if top_keys & error_keys and len(top_keys) <= 3:
            return True
        return False


# ═══════════════════════════════════════════════════════════════
# 便捷入口
# ═══════════════════════════════════════════════════════════════

def run_l3_fuzzer(
    endpoints: list[ClassifiedEndpoint],
    base_url: str,
    jwt_token: str = "",
    verbose: bool = True,
) -> list[dict]:
    """
    L3.5 Fuzz测试入口

    :param endpoints: L3分类后的端点列表
    :param base_url: 目标网站base URL
    :param jwt_token: JWT token (可选, 用于认证请求)
    :returns: findings列表
    """
    fuzzer = ParameterFuzzer(
        base_url=base_url,
        jwt_token=jwt_token,
        verbose=verbose,
    )
    return fuzzer.fuzz_all(endpoints)
