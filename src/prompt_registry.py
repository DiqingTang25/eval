"""
评分Prompt版本注册表 v1.0 (P1-4)

功能:
- Prompt模板版本管理 (SHA256哈希 + 语义版本号)
- 评分时自动记录使用的Prompt版本
- Prompt变更检测与审计轨迹
- 历史版本回溯

用法:
    registry = PromptRegistry()

    # 注册当前prompt版本
    version_id = registry.register(
        name="evaluator_judge_v1",
        template=prompt_template_text,
        variables=["question", "agent_answer", "golden_answer", "goal", ...],
    )

    # 评分时记录
    registry.record_usage(version_id, session_id="session_001")

    # 获取审计轨迹
    history = registry.get_history("evaluator_judge_v1")
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class PromptVersion:
    """Prompt版本记录"""
    version_id: str               # SHA256 前12位
    name: str                     # 逻辑名称, 如 "evaluator_judge_v1"
    semantic_version: str         # 语义版本 "1.0.0"
    description: str
    template_hash: str            # 完整SHA256
    template_preview: str         # 前200字符预览
    variables: list[str]          # 模板变量列表
    created_at: str
    parent_version: Optional[str] = None  # 父版本ID
    change_log: str = ""          # 变更说明


@dataclass
class PromptUsage:
    """Prompt使用记录"""
    version_id: str
    name: str
    session_id: str
    used_at: str
    scenario_index: int = 0


# ── 注册表 ────────────────────────────────────────────────

class PromptRegistry:
    """评分Prompt版本注册表"""

    def __init__(self, storage_path: str = "data/prompt_registry.json"):
        self.storage_path = storage_path
        self._versions: dict[str, PromptVersion] = {}
        self._usage_log: list[PromptUsage] = []
        self._load()

    # ── 公共API ──────────────────────────────────────────

    def register(self, name: str, template: str, variables: list[str],
                 description: str = "", semantic_version: str = "1.0.0",
                 parent_version: Optional[str] = None,
                 change_log: str = "") -> str:
        """注册一个Prompt模板版本

        :param name: 逻辑名称
        :param template: 完整Prompt模板文本
        :param variables: 模板中使用的变量列表
        :param description: 版本描述
        :param semantic_version: 语义版本号
        :param parent_version: 父版本ID (用于追踪演进)
        :param change_log: 变更说明
        :return: version_id (SHA256前12位)
        """
        template_hash = self._hash(template)
        version_id = template_hash[:12]

        # 检查是否已存在（幂等）
        if version_id in self._versions:
            return version_id

        version = PromptVersion(
            version_id=version_id,
            name=name,
            semantic_version=semantic_version,
            description=description,
            template_hash=template_hash,
            template_preview=template[:200].replace("\n", "\\n"),
            variables=sorted(variables),
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_version=parent_version,
            change_log=change_log,
        )

        self._versions[version_id] = version
        self._save()
        return version_id

    def record_usage(self, version_id: str, session_id: str,
                     scenario_index: int = 0) -> None:
        """记录一次Prompt使用

        :param version_id: prompt版本ID
        :param session_id: 评测会话ID
        :param scenario_index: 场景序号
        """
        version = self._versions.get(version_id)
        if not version:
            # 未注册的版本也记录(用hash作为name)
            usage = PromptUsage(
                version_id=version_id,
                name=f"unregistered:{version_id}",
                session_id=session_id,
                used_at=datetime.now(timezone.utc).isoformat(),
                scenario_index=scenario_index,
            )
        else:
            usage = PromptUsage(
                version_id=version_id,
                name=version.name,
                session_id=session_id,
                used_at=datetime.now(timezone.utc).isoformat(),
                scenario_index=scenario_index,
            )

        self._usage_log.append(usage)
        # 不立即保存, 避免I/O风暴 — 调用 flush() 批量写入

    def flush(self) -> None:
        """批量写入使用记录到磁盘"""
        self._save()

    def get_version(self, version_id: str) -> Optional[PromptVersion]:
        """获取指定版本"""
        return self._versions.get(version_id)

    def get_latest_version(self, name: str) -> Optional[PromptVersion]:
        """获取某个Prompt名称的最新版本"""
        versions = [v for v in self._versions.values() if v.name == name]
        if not versions:
            return None
        return max(versions, key=lambda v: v.created_at)

    def get_history(self, name: str) -> list[PromptVersion]:
        """获取某个Prompt的版本演进历史（按时间排序）"""
        versions = [v for v in self._versions.values() if v.name == name]
        return sorted(versions, key=lambda v: v.created_at)

    def get_usage_for_session(self, session_id: str) -> list[PromptUsage]:
        """获取某个评测会话使用的所有Prompt版本"""
        return [u for u in self._usage_log if u.session_id == session_id]

    def list_versions(self, name: str = None) -> list[dict]:
        """列出已注册的Prompt版本

        :param name: 可选, 按名称过滤
        :return: 版本摘要列表
        """
        result = []
        for v in self._versions.values():
            if name and v.name != name:
                continue
            result.append({
                "version_id": v.version_id,
                "name": v.name,
                "semantic_version": v.semantic_version,
                "description": v.description,
                "created_at": v.created_at,
                "parent_version": v.parent_version,
                "change_log": v.change_log,
            })
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def diff_versions(self, version_id_a: str, version_id_b: str) -> dict:
        """对比两个版本的差异

        :return: {added, removed, changed_lines, a_info, b_info}
        """
        v_a = self._versions.get(version_id_a)
        v_b = self._versions.get(version_id_b)

        if not v_a or not v_b:
            return {"error": "版本不存在"}

        return {
            "version_a": {
                "id": v_a.version_id,
                "semantic_version": v_a.semantic_version,
                "created_at": v_a.created_at,
            },
            "version_b": {
                "id": v_b.version_id,
                "semantic_version": v_b.semantic_version,
                "created_at": v_b.created_at,
            },
            "hash_a": v_a.template_hash,
            "hash_b": v_b.template_hash,
            "same": v_a.template_hash == v_b.template_hash,
        }

    # ── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def hash_prompt(template: str) -> str:
        """计算Prompt模板的SHA256哈希（快捷方法, 无需注册）"""
        return PromptRegistry._hash(template)

    @staticmethod
    def hash_prompt_short(template: str) -> str:
        """计算Prompt模板的短哈希（前12位）"""
        return PromptRegistry._hash(template)[:12]

    # ── 内部方法 ──────────────────────────────────────────

    @staticmethod
    def _hash(text: str) -> str:
        """SHA256哈希"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        """从磁盘加载注册表"""
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for v_data in data.get("versions", []):
                version = PromptVersion(**v_data)
                self._versions[version.version_id] = version

            for u_data in data.get("usage_log", []):
                self._usage_log.append(PromptUsage(**u_data))

        except Exception as e:
            print(f"[PromptRegistry] 加载失败: {e}")

    def _save(self) -> None:
        """持久化到磁盘"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {
            "versions": [
                {
                    "version_id": v.version_id,
                    "name": v.name,
                    "semantic_version": v.semantic_version,
                    "description": v.description,
                    "template_hash": v.template_hash,
                    "template_preview": v.template_preview,
                    "variables": v.variables,
                    "created_at": v.created_at,
                    "parent_version": v.parent_version,
                    "change_log": v.change_log,
                }
                for v in self._versions.values()
            ],
            "usage_log": [
                {
                    "version_id": u.version_id,
                    "name": u.name,
                    "session_id": u.session_id,
                    "used_at": u.used_at,
                    "scenario_index": u.scenario_index,
                }
                for u in self._usage_log
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @property
    def version_count(self) -> int:
        return len(self._versions)

    @property
    def usage_count(self) -> int:
        return len(self._usage_log)


# ── 全局单例 ──────────────────────────────────────────────

_registry: Optional[PromptRegistry] = None


def get_registry() -> PromptRegistry:
    """获取全局Prompt注册表单例"""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry
