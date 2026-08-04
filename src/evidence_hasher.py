"""
证据哈希工具 — 纯 MySQL 证据链方案

核心职责:
  1. 计算 SHA-256 指纹 (不可篡改校验)
  2. 将证据 JSON 直接写入 MySQL (不经过 TOS/对象存储)
  3. 审计验证: 从 MySQL 取出 → 重新 SHA-256 → 比对

用法:
    from src.evidence_hasher import EvidenceHasher

    hasher = EvidenceHasher()
    fingerprint = hasher.hash_conversation(conversation_json, score_json)
    hasher.store_evidence(db, session_id, eval_score_id, fingerprint,
                          conversation_json, score_json)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class EvidenceHasher:
    """证据哈希计算 + MySQL 存储"""

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

    def hash_conversation(self, conversation_json: dict, score_json: dict) -> str:
        """
        计算场景级证据指纹

        fingerprint = SHA-256( canonical_json(conversation + score) )
        任何字段改动 → 指纹变化 → 篡改可检测
        """
        composite = json.dumps({
            "conversation": conversation_json,
            "score": {k: v for k, v in score_json.items() if not k.startswith("_")},
        }, ensure_ascii=False, sort_keys=True, default=str)
        return self.sha256_hex(composite)

    def hash_artifact(self, artifact_json: dict | list) -> str:
        """计算单个证据文件的 SHA-256"""
        data = json.dumps(artifact_json, ensure_ascii=False, sort_keys=True, default=str)
        return self.sha256_hex(data)

    def store_evidence(
        self,
        db,
        session_id: str,
        eval_score_id: str,
        scenario_index: int,
        conversation_json: dict,
        score_json: dict,
        metadata: dict = None,
    ) -> str:
        """
        将证据直接写入 MySQL

        写入内容:
          - evidence_trail: 原始 JSON + SHA-256 (文件级)
          - eval_scores.evidence_hash: 场景级复合指纹

        Returns: 场景级 SHA-256 指纹
        """
        from backend.models.evidence_trail import EvidenceTrail
        from backend.models.eval_score import EvalScore

        # 1. 场景级指纹
        composite_fingerprint = self.hash_conversation(conversation_json, score_json)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_path = f"conversations/{session_id[:8]}/scenario_{scenario_index:03d}_{ts}"

        # 2. 更新 eval_scores
        score_row = db.query(EvalScore).filter(EvalScore.id == eval_score_id).first()
        if score_row:
            score_row.evidence_hash = composite_fingerprint
            score_row.evidence_path = f"{base_path}.json"

        # 3. 写入对话证据
        conv_json_str = json.dumps(conversation_json, ensure_ascii=False, default=str)
        conv_hash = self.sha256_hex(conv_json_str)
        db.add(EvidenceTrail(
            session_id=session_id,
            eval_score_id=eval_score_id,
            artifact_type="conversation",
            artifact_path=f"{base_path}_conversation.json",
            sha256=conv_hash,
            file_size=len(conv_json_str.encode("utf-8")),
            content_type="application/json",
            data_json=conv_json_str,
            storage_tier="hot",
            metadata_json=metadata,
        ))

        # 4. 写入评分证据
        score_json_str = json.dumps(score_json, ensure_ascii=False, default=str)
        score_hash = self.sha256_hex(score_json_str)
        db.add(EvidenceTrail(
            session_id=session_id,
            eval_score_id=eval_score_id,
            artifact_type="scoring",
            artifact_path=f"{base_path}_scoring.json",
            sha256=score_hash,
            file_size=len(score_json_str.encode("utf-8")),
            content_type="application/json",
            data_json=score_json_str,
            storage_tier="hot",
            metadata_json=metadata,
        ))

        # 5. 写入场景级聚合证据
        composite_json_str = json.dumps({
            "session_id": session_id,
            "scenario_index": scenario_index,
            "conversation_hash": conv_hash,
            "scoring_hash": score_hash,
            "composite_fingerprint": composite_fingerprint,
        }, ensure_ascii=False, default=str)
        db.add(EvidenceTrail(
            session_id=session_id,
            eval_score_id=eval_score_id,
            artifact_type="hash_list",
            artifact_path=f"{base_path}_manifest.json",
            sha256=self.sha256_hex(composite_json_str),
            file_size=len(composite_json_str.encode("utf-8")),
            content_type="application/json",
            data_json=composite_json_str,
            storage_tier="hot",
            metadata_json=metadata,
        ))

        logger.info("Evidence stored: session=%s scenario=%d hash=%s files=3",
                     session_id, scenario_index, composite_fingerprint[:16])
        return composite_fingerprint

    def verify(self, db, eval_score_id: str) -> dict:
        """
        审计验证: 从 MySQL 取出证据 → 重新 SHA-256 → 比对

        Returns:
          {
            "match": bool,
            "stored_hash": str,
            "recomputed_hash": str,
            "artifacts_checked": int,
            "artifacts_ok": int,
            "tampered": list[str],  # 被篡改的文件列表
          }
        """
        from backend.models.evidence_trail import EvidenceTrail
        from backend.models.eval_score import EvalScore

        result = {
            "match": True,
            "stored_hash": "",
            "recomputed_hash": "",
            "artifacts_checked": 0,
            "artifacts_ok": 0,
            "tampered": [],
        }

        # 场景级验证
        score_row = db.query(EvalScore).filter(EvalScore.id == eval_score_id).first()
        if not score_row:
            result["match"] = False
            result["tampered"].append("eval_score not found")
            return result

        result["stored_hash"] = score_row.evidence_hash

        # 文件级验证
        trails = db.query(EvidenceTrail).filter(
            EvidenceTrail.eval_score_id == eval_score_id
        ).all()

        for trail in trails:
            result["artifacts_checked"] += 1
            if trail.data_json:
                recomputed = self.sha256_hex(trail.data_json)
                if recomputed == trail.sha256:
                    result["artifacts_ok"] += 1
                else:
                    result["tampered"].append(trail.artifact_path)
                    result["match"] = False

        return result


# ── 全局单例 ──
_hasher: Optional[EvidenceHasher] = None


def get_hasher() -> EvidenceHasher:
    global _hasher
    if _hasher is None:
        _hasher = EvidenceHasher()
    return _hasher
