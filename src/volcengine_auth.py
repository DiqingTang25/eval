"""
火山引擎 API Signature V4 (HMAC-SHA256) 签名工具

用法:
    from src.volcengine_auth import VolcSigner

    signer = VolcSigner(ak="your_access_key", sk="your_secret_key",
                        service="air", region="cn-north-1")
    headers = signer.sign("POST", "/api/knowledge/v1/search", body='{"query":"test"}')
    # → {"Authorization": "HMAC-SHA256 Credential=...", "X-Date": "...", ...}

参考:
    https://www.volcengine.com/docs/6369/67269
    https://www.volcengine.com/docs/84313/1254485
"""

import hashlib
import hmac
import os
from datetime import datetime, timezone


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


class VolcSigner:
    """火山引擎 Signature V4 签名器"""

    def __init__(
        self,
        ak: str = None,
        sk: str = None,
        service: str = "air",
        region: str = "cn-north-1",
    ):
        self.ak = ak or os.getenv("VOLC_ACCESS_KEY", "")
        self.sk = sk or os.getenv("VOLC_SECRET_KEY", "")
        self.service = service
        self.region = region

    @property
    def is_configured(self) -> bool:
        return bool(self.ak and self.sk)

    def sign(
        self,
        method: str = "POST",
        host: str = "",
        path: str = "/",
        query: str = "",
        body: str = "",
        headers_extra: dict = None,
    ) -> dict:
        """
        生成签名请求头

        :param method: HTTP 方法 (GET/POST)
        :param host: API域名, 如 api-knowledgebase.mlp.cn-beijing.volces.com
        :param path: 请求路径, 如 /api/knowledge/v1/search
        :param query: 查询字符串 (不含 ?)
        :param body: 请求体 (JSON字符串)
        :param headers_extra: 额外的请求头 (会合并到签名中)
        :return: 包含 Authorization, X-Date, Host, Content-Type 的请求头字典
        """
        if not host:
            raise ValueError("host 参数必填, 如 api-knowledgebase.mlp.cn-beijing.volces.com")

        now = datetime.now(timezone.utc)
        xdate = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")

        # ── 步骤1: 创建规范请求 (CanonicalRequest) ──
        # CanonicalHeaders: 按字母序, 名字小写, 值trim
        canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{xdate}\n"
        signed_headers = "content-type;host;x-date"

        payload_hash = _sha256_hex(body)
        canonical_request = (
            f"{method.upper()}\n"
            f"{path}\n"
            f"{query}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )

        # ── 步骤2: 创建待签名字符串 (StringToSign) ──
        credential_scope = f"{datestamp}/{self.region}/{self.service}/request"
        string_to_sign = (
            f"HMAC-SHA256\n"
            f"{xdate}\n"
            f"{credential_scope}\n"
            f"{_sha256_hex(canonical_request)}"
        )

        # ── 步骤3: 派生签名密钥 (kSigning) ──
        k_date = _hmac_sha256(self.sk.encode("utf-8"), datestamp)
        k_region = _hmac_sha256(k_date, self.region)
        k_service = _hmac_sha256(k_region, self.service)
        k_signing = _hmac_sha256(k_service, "request")

        # ── 步骤4: 计算签名 ──
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # ── 步骤5: 构建 Authorization 头 ──
        authorization = (
            f"HMAC-SHA256 "
            f"Credential={self.ak}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        headers = {
            "Authorization": authorization,
            "X-Date": xdate,
            "Host": host,
            "Content-Type": "application/json",
        }
        if headers_extra:
            headers.update(headers_extra)

        return headers


# ── 便捷函数: 一键创建签名器 + 签名 ──

def sign_request(
    method: str,
    host: str,
    path: str,
    body: str = "",
    query: str = "",
) -> dict:
    """
    便捷函数: 从环境变量读取 AK/SK 并签名

    需要环境变量:
        VOLC_ACCESS_KEY: 火山引擎 Access Key
        VOLC_SECRET_KEY: 火山引擎 Secret Key
    """
    signer = VolcSigner()
    if not signer.is_configured:
        raise RuntimeError("VOLC_ACCESS_KEY 和 VOLC_SECRET_KEY 未配置")
    return signer.sign(method=method, host=host, path=path, query=query, body=body)
