"""
配置加载器 v3.4 — AHE 可证伪契约基础设施

将 L1/L2/L3 的阈值、权重、提示词从硬编码中解耦为版本化 YAML 文件。
支持:
  - 配置修改历史追踪 (history/)
  - 修改预测记录 (prediction 字段)
  - 回归验证钩子 (validated_at 字段)
  - 自动回滚支持 (FALLBACK 版本)

对齐:
  - AHE (arXiv:2604.25850): 组件可观测性 + 决策可观测性
  - Self-Harness (arXiv:2606.09498): 配置作为可编辑文件

用法:
    from src.config_loader import ConfigLoader
    loader = ConfigLoader()
    l1 = loader.l1_thresholds   # L1规则阈值
    dims = loader.dimensions     # 维度定义
    weights = loader.weights     # 权重配置
    loader.validate_all()        # 检查所有prediction是否验证通过
"""

import os
import yaml
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConfigChangeRecord:
    """单次配置变更记录 (AHE 可证伪契约)"""
    file_path: str
    version_before: str
    version_after: str
    prediction: str           # 修改时声明的预期效果
    modified_at: str
    validated_at: str = ""    # 验证时间（空=未验证）
    validation_result: str = ""  # "pass" / "fail" / "pending"
    validation_note: str = ""
    rollback_to: str = ""     # 如果验证失败，回滚到的版本


class ConfigLoader:
    """
    统一配置加载器 — 从 YAML 文件加载所有可调参数

    配置文件:
      config/l1_thresholds.yaml          — L1规则阈值
      config/l3_judge_prompts/           — L3 Judge 提示词
      config/dimension_weights.yaml      — 维度权重
    """

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._cache: dict = {}
        self._change_log: list[ConfigChangeRecord] = []

        # 确保 history 目录存在
        (self.config_dir / "history").mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════
    # L1 阈值
    # ═══════════════════════════════════════════════════

    @property
    def l1_thresholds(self) -> dict:
        """L1 规则层阈值配置"""
        return self._load("l1_thresholds.yaml")

    @property
    def fact_thresholds(self) -> dict:
        return self.l1_thresholds.get("fact_rules", {})

    @property
    def structure_thresholds(self) -> dict:
        return self.l1_thresholds.get("structure_rules", {})

    @property
    def sla_thresholds(self) -> dict:
        return self.l1_thresholds.get("sla_rules", {})

    @property
    def safety_thresholds(self) -> dict:
        return self.l1_thresholds.get("safety_rules", {})

    @property
    def overhelping_thresholds(self) -> dict:
        return self.l1_thresholds.get("overhelping_rules", {})

    # ═══════════════════════════════════════════════════
    # L3 Judge 提示词
    # ═══════════════════════════════════════════════════

    @property
    def dimensions(self) -> dict:
        """所有维度的定义和提示词"""
        return self._load("l3_judge_prompts/dimension_definitions.yaml")

    def get_dim_prompt(self, dim_name: str) -> str:
        """获取单个维度的 Judge 提示词"""
        dims = self.dimensions.get("dimensions", {})
        dim = dims.get(dim_name, {})
        return dim.get("prompt", "")

    def get_dim_weight(self, dim_name: str) -> dict:
        """获取单个维度的 L1/L3 权重"""
        dims = self.dimensions.get("dimensions", {})
        dim = dims.get(dim_name, {})
        return dim.get("weight", {"rule": 0.30, "llm": 0.70})

    def get_dim_prediction(self, dim_name: str) -> str:
        """获取单个维度的预期效果声明"""
        dims = self.dimensions.get("dimensions", {})
        dim = dims.get(dim_name, {})
        return dim.get("prediction", "")

    # ═══════════════════════════════════════════════════
    # 权重配置
    # ═══════════════════════════════════════════════════

    @property
    def weights(self) -> dict:
        """维度权重配置"""
        return self._load("dimension_weights.yaml")

    def get_global_weights(self) -> dict:
        """全局 L1/L2/L3 权重"""
        return self.weights.get("global", {"rule_weight": 0.30, "llm_weight": 0.70})

    def get_dimension_weights(self) -> dict:
        """所有维度的权重分配"""
        raw = self.weights.get("dimensions", {})
        return {
            dim: {"rule": cfg["rule"], "llm": cfg["llm"]}
            for dim, cfg in raw.items()
        }

    def get_adversarial_weights(self) -> dict:
        """对抗性测试的权重调整"""
        return self.weights.get("adversarial_weights", {})

    # ═══════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════

    def _load(self, rel_path: str) -> dict:
        """加载 YAML 配置（带缓存）"""
        if rel_path in self._cache:
            return self._cache[rel_path]

        file_path = self.config_dir / rel_path
        if not file_path.exists():
            print(f"  ⚠️ 配置文件不存在: {file_path}，使用默认值")
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self._cache[rel_path] = data
        return data

    def invalidate_cache(self):
        """清除缓存（配置热更新时调用）"""
        self._cache.clear()

    # ═══════════════════════════════════════════════════
    # AHE 可证伪契约
    # ═══════════════════════════════════════════════════

    def record_change(
        self,
        file_path: str,
        version_before: str,
        version_after: str,
        prediction: str,
    ) -> ConfigChangeRecord:
        """记录一次配置变更"""
        record = ConfigChangeRecord(
            file_path=file_path,
            version_before=version_before,
            version_after=version_after,
            prediction=prediction,
            modified_at=datetime.now().isoformat(),
            validated_at="",
            validation_result="pending",
        )
        self._change_log.append(record)

        # 备份旧版本到 history/
        src = self.config_dir / file_path
        if src.exists():
            history_name = f"{file_path.replace('/', '_')}.v{version_before}.yaml"
            shutil.copy2(src, self.config_dir / "history" / history_name)

        return record

    def validate_prediction(
        self,
        record: ConfigChangeRecord,
        passed: bool,
        note: str = "",
    ):
        """验证配置变更的预测是否成立"""
        record.validated_at = datetime.now().isoformat()
        record.validation_result = "pass" if passed else "fail"
        record.validation_note = note

        if not passed:
            print(f"  ⛔ 配置变更验证失败: {record.file_path}")
            print(f"     预测: {record.prediction}")
            print(f"     实际: {note}")
            print(f"     建议回滚至版本: {record.version_before}")

    def validate_all(self) -> dict:
        """检查所有变更记录的验证状态"""
        pending = [r for r in self._change_log if r.validation_result == "pending"]
        failed = [r for r in self._change_log if r.validation_result == "fail"]
        passed = [r for r in self._change_log if r.validation_result == "pass"]

        return {
            "total": len(self._change_log),
            "pending": len(pending),
            "passed": len(passed),
            "failed": len(failed),
            "needs_attention": len(failed) > 0 or len(pending) > 10,
            "failed_records": [
                {
                    "file": r.file_path,
                    "prediction": r.prediction,
                    "note": r.validation_note,
                    "rollback_to": r.version_before,
                }
                for r in failed
            ],
        }

    def get_change_history(self) -> list[dict]:
        """获取所有配置变更历史"""
        return [
            {
                "file": r.file_path,
                "version": f"{r.version_before} → {r.version_after}",
                "prediction": r.prediction,
                "status": r.validation_result,
                "modified": r.modified_at,
                "validated": r.validated_at,
            }
            for r in self._change_log
        ]
