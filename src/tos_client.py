"""
火山引擎 TOS (对象存储) 客户端 — Phase 1 证据链地基

职责:
  1. 上传评测原始数据 (对话JSON / 截图 / 录屏 / 报告) 到 TOS
  2. 计算 SHA-256 指纹 (不可篡改校验)
  3. 生成预签名访问链接 (审计入口)
  4. 生命周期管理 (hot → warm → cold)

认证: 复用 volcengine_auth.VolcSigner (HMAC-SHA256 Signature V4)
兼容: S3 兼容协议, 可用 boto3 直接操作

用法:
    client = TosClient()
    key, sha256_hash = client.upload_json({"conversation": [...]}, "raw-conversations/sess-001/scen-001.json")
    url = client.presigned_url(key, ttl=3600)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TosClient:
    """TOS 对象存储客户端 — 基于火山引擎 Signature V4"""

    # TOS 兼容 S3 的 endpoint 格式
    ENDPOINT_TEMPLATE = "https://tos-cn-beijing.volces.com"

    def __init__(
        self,
        ak: str = None,
        sk: str = None,
        region: str = "cn-beijing",
        bucket: str = "agent-eval-evidence",
        endpoint: str = None,
    ):
        self.ak = ak if ak is not None else os.getenv("VOLC_ACCESS_KEY", "")
        self.sk = sk if sk is not None else os.getenv("VOLC_SECRET_KEY", "")
        self.region = region
        self.bucket = bucket
        self.endpoint = endpoint or self.ENDPOINT_TEMPLATE

        # 延迟导入, 避免未安装时阻塞其他功能
        self._s3_client = None
        self._configured = bool(self.ak and self.sk)
        if not self._configured:
            logger.warning("TOS: AK/SK 未配置, TOS 上传功能不可用 (仅计算本地SHA-256)")

    # ── S3 客户端 (惰性初始化) ──
    @property
    def s3(self):
        """惰性初始化 boto3 S3 客户端"""
        if self._s3_client is None and self._configured:
            try:
                import boto3
                from botocore.config import Config

                self._s3_client = boto3.client(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.ak,
                    aws_secret_access_key=self.sk,
                    config=Config(
                        signature_version="s3v4",
                        s3={"addressing_style": "virtual"},
                    ),
                )
                logger.info("TOS S3 client initialized: bucket=%s, region=%s",
                            self.bucket, self.region)
            except ImportError:
                logger.error("boto3 未安装: pip install boto3")
            except Exception as e:
                logger.error("TOS S3 client 初始化失败: %s", e)
        return self._s3_client

    @property
    def available(self) -> bool:
        return self._configured

    # ── 核心操作 ──

    @staticmethod
    def sha256_hex(data: bytes | str) -> str:
        """计算 SHA-256 哈希 (不可篡改指纹)"""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def sha256_file(file_path: str | Path) -> tuple[str, int]:
        """计算文件的 SHA-256 哈希和大小"""
        path = Path(file_path) if isinstance(file_path, str) else file_path
        sha = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
                size += len(chunk)
        return sha.hexdigest(), size

    def upload_json(
        self, data: dict | list, tos_key: str, compute_hash: bool = True
    ) -> tuple[str, str]:
        """上传 JSON 数据到 TOS

        Returns: (tos_key, sha256_hex)
        """
        body = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        sha256_hash = self.sha256_hex(body) if compute_hash else ""

        if self.s3 is not None:
            try:
                self.s3.put_object(
                    Bucket=self.bucket,
                    Key=tos_key,
                    Body=body.encode("utf-8"),
                    ContentType="application/json",
                    Metadata={"sha256": sha256_hash} if sha256_hash else {},
                )
                logger.info("TOS upload: %s (%d bytes, sha256=%s)",
                            tos_key, len(body), sha256_hash[:16])
            except Exception as e:
                logger.error("TOS upload failed: %s — %s", tos_key, e)
                # 上传失败不影响主流程: 至少返回本地 SHA-256
        else:
            logger.debug("TOS upload skipped (not configured): %s", tos_key)

        return tos_key, sha256_hash

    def upload_file(
        self, local_path: str | Path, tos_key: str, content_type: str = None
    ) -> tuple[str, str, int]:
        """上传本地文件到 TOS

        Returns: (tos_key, sha256_hex, file_size)
        """
        path = Path(local_path) if isinstance(local_path, str) else local_path
        sha256_hash, file_size = self.sha256_file(path)

        ct = content_type or self._guess_content_type(path)

        if self.s3 is not None:
            try:
                with open(path, "rb") as f:
                    self.s3.put_object(
                        Bucket=self.bucket,
                        Key=tos_key,
                        Body=f,
                        ContentType=ct,
                        Metadata={"sha256": sha256_hash},
                    )
                logger.info("TOS upload: %s (%d bytes, sha256=%s)",
                            tos_key, file_size, sha256_hash[:16])
            except Exception as e:
                logger.error("TOS upload failed: %s — %s", tos_key, e)

        return tos_key, sha256_hash, file_size

    def presigned_url(self, tos_key: str, ttl: int = 3600) -> str:
        """生成预签名访问链接 (审计人员点击即可下载原始文件)"""
        if self.s3 is None:
            return ""
        try:
            url = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": tos_key},
                ExpiresIn=ttl,
            )
            return url
        except Exception as e:
            logger.error("TOS presigned_url failed: %s — %s", tos_key, e)
            return ""

    def download(self, tos_key: str, local_path: str | Path) -> bool:
        """从 TOS 下载文件到本地"""
        if self.s3 is None:
            return False
        path = Path(local_path) if isinstance(local_path, str) else local_path
        try:
            self.s3.download_file(self.bucket, tos_key, str(path))
            logger.info("TOS download: %s → %s", tos_key, path)
            return True
        except Exception as e:
            logger.error("TOS download failed: %s — %s", tos_key, e)
            return False

    def verify(self, tos_key: str, expected_sha256: str) -> bool:
        """审计验证: 从 TOS 下载文件并校验 SHA-256"""
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            if not self.download(tos_key, tmp_path):
                return False
            actual_sha256, _ = self.sha256_file(tmp_path)
            match = actual_sha256 == expected_sha256
            if not match:
                logger.error("TAMPER DETECTED: %s expected=%s actual=%s",
                             tos_key, expected_sha256[:16], actual_sha256[:16])
            return match
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def object_exists(self, tos_key: str) -> bool:
        """检查 TOS 对象是否存在"""
        if self.s3 is None:
            return False
        try:
            self.s3.head_object(Bucket=self.bucket, Key=tos_key)
            return True
        except Exception:
            return False

    # ── 构建标准化的 TOS Key ──

    @staticmethod
    def make_key(session_id: str, scenario_index: int, artifact_type: str,
                 extension: str = "json") -> str:
        """生成标准化的 TOS object key

        artifact_type: conversation | screenshot | recording | report | hash_list
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return (
            f"{artifact_type}s/{session_id[:8]}/"
            f"scenario_{scenario_index:03d}_{timestamp}.{extension}"
        )

    # ── 辅助 ──

    @staticmethod
    def _guess_content_type(path: Path) -> str:
        ext = path.suffix.lower()
        return {
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".mp4": "video/mp4",
            ".pdf": "application/pdf",
            ".html": "text/html",
            ".md": "text/markdown",
            ".csv": "text/csv",
        }.get(ext, "application/octet-stream")


# ── 全局单例 ──
_tos_client: Optional[TosClient] = None


def get_tos_client() -> TosClient:
    """获取全局 TosClient 单例"""
    global _tos_client
    if _tos_client is None:
        _tos_client = TosClient()
    return _tos_client
