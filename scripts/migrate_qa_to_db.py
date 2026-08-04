"""将 golden_qa_bank.json + qa_pending.json 迁移到 MySQL"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import QAPair
from backend.config import settings


def migrate():
    engine = create_engine(settings.sync_database_url, echo=False)
    session = Session(engine)

    total = 0
    approved = 0
    pending = 0
    rejected = 0

    # ── 1. 迁移 golden_qa_bank.json ──
    bank_path = Path(__file__).parent.parent / "data" / "golden_qa_bank.json"
    if bank_path.exists():
        with open(bank_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", data.get("qa_pairs", []))
        else:
            items = []

        print(f"golden_qa_bank.json: {len(items)} items")

        for item in items:
            qa_id = item.get("qa_id", "")
            if not qa_id:
                continue

            existing = session.query(QAPair).filter_by(qa_id=qa_id).first()
            if existing:
                continue

            source = item.get("source", {}) or {}
            qa = QAPair(
                qa_id=qa_id,
                phase=item.get("phase", ""),
                type=item.get("type", ""),
                difficulty=item.get("difficulty", "中等"),
                question=item.get("question", ""),
                golden_answer=item.get("golden_answer", ""),
                knowledge_points=item.get("knowledge_points", []) or [],
                goal=item.get("goal", ""),
                knowledge_based=item.get("knowledge_based", True),
                adversarial_type=item.get("adversarial_type"),
                source_document=source.get("document", ""),
                source_sheet=source.get("sheet", ""),
                source_excerpt=source.get("excerpt", ""),
                status="approved",
                reviewer_notes=item.get("reviewer_notes", "历史数据迁移"),
                approved_at=datetime.now(timezone.utc),
            )
            session.add(qa)
            total += 1
            approved += 1

    # ── 2. 迁移 qa_pending.json ──
    pending_path = Path(__file__).parent.parent / "data" / "qa_pending.json"
    if pending_path.exists():
        with open(pending_path, "r", encoding="utf-8") as f:
            pending_items = json.load(f)

        print(f"qa_pending.json: {len(pending_items)} items")

        for item in pending_items:
            qa_id = item.get("qa_id", "")
            if not qa_id:
                continue

            existing = session.query(QAPair).filter_by(qa_id=qa_id).first()
            if existing:
                continue

            source = item.get("source", {}) or {}
            status = item.get("status", "pending")
            qa = QAPair(
                qa_id=qa_id,
                phase=item.get("phase", ""),
                type=item.get("type", ""),
                difficulty=item.get("difficulty", "中等"),
                question=item.get("question", ""),
                golden_answer=item.get("golden_answer", ""),
                knowledge_points=item.get("knowledge_points", []) or [],
                goal=item.get("goal", ""),
                knowledge_based=item.get("knowledge_based", True),
                adversarial_type=item.get("adversarial_type"),
                source_document=source.get("document", ""),
                source_sheet=source.get("sheet", ""),
                source_excerpt=source.get("excerpt", ""),
                status=status,
                reviewer_notes=item.get("reviewer_notes", ""),
            )
            session.add(qa)
            total += 1
            if status == "approved":
                approved += 1
            elif status == "rejected":
                rejected += 1
            else:
                pending += 1

    session.commit()
    session.close()

    print(f"\nMigration done: {total} total")
    print(f"  approved: {approved} | pending: {pending} | rejected: {rejected}")


if __name__ == "__main__":
    migrate()
