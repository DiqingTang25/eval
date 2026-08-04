#!/usr/bin/env python3
"""
数据库一键迁移工具 — SQLite → MySQL (火山引擎 RDS)

用法:
  # 仅创建表结构（Alembic）
  python scripts/migrate_db.py --schema-only

  # 完整迁移（表结构 + 数据）
  python scripts/migrate_db.py --full

  # 预览数据（不写入）
  python scripts/migrate_db.py --dry-run

前提:
  1. 已配置 .env 中的 MYSQL_* 变量
  2. 火山引擎 RDS 实例已创建并可连接
"""

import argparse
import os
import sys
from pathlib import Path

# 确保项目根目录在 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# SQLite 源数据库
SQLITE_PATH = Path(__file__).parent.parent / "data" / "agent_eval.db"

# MySQL 目标连接
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "agent_eval")

MYSQL_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

# 需要迁移的表（按依赖顺序）
TABLES_IN_ORDER = [
    "qa_pairs",
    "test_sessions",
    "test_scenarios",
    "conversation_turns",
    "eval_scores",
    "reports",
    "web_eval_results",
    "knowledge_bases",
    "kb_documents",
]


def get_sqlite_engine():
    """创建 SQLite 源引擎"""
    if not SQLITE_PATH.exists():
        print(f"❌ SQLite 数据库不存在: {SQLITE_PATH}")
        sys.exit(1)
    url = f"sqlite:///{SQLITE_PATH}"
    return create_engine(url)


def get_mysql_engine():
    """创建 MySQL 目标引擎"""
    try:
        eng = create_engine(MYSQL_URL, pool_pre_ping=True)
        # 验证连接
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception as e:
        print(f"❌ 无法连接 MySQL RDS: {e}")
        print(f"   连接: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
        print(f"   请确认: 1) RDS已创建 2) IP白名单已配置 3) .env中MYSQL_*正确")
        sys.exit(1)


def run_alembic():
    """运行 Alembic 迁移创建表结构"""
    import subprocess
    alembic_dir = Path(__file__).parent.parent / "backend" / "alembic"
    print("📐 运行 Alembic 迁移...")
    result = subprocess.run(
        ["alembic", "-c", str(alembic_dir / "alembic.ini"), "upgrade", "head"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
    )
    if result.returncode != 0:
        print(f"❌ Alembic 迁移失败:\n{result.stderr}")
        return False
    print(f"✅ {result.stdout.strip()}")
    return True


def discover_table_names(engine) -> list[str]:
    """自动发现需要迁移的表"""
    insp = inspect(engine)
    return insp.get_table_names()


def migrate_table(src_engine, dst_engine, table_name: str) -> tuple[int, int]:
    """迁移单张表的数据"""
    src_session = sessionmaker(bind=src_engine)()
    dst_session = sessionmaker(bind=dst_engine)()

    try:
        # 读取源数据
        result = src_session.execute(text(f"SELECT * FROM {table_name}"))
        rows = result.fetchall()
        columns = result.keys()

        if not rows:
            return 0, 0

        # 写入目标（REPLACE INTO 避免主键冲突）
        placeholders = ", ".join([f":{col}" for col in columns])
        cols_str = ", ".join(columns)
        sql = f"REPLACE INTO {table_name} ({cols_str}) VALUES ({placeholders})"

        count = 0
        for row in rows:
            row_dict = dict(zip(columns, row))
            dst_session.execute(text(sql), row_dict)
            count += 1

        dst_session.commit()
        return count, 0

    except Exception as e:
        dst_session.rollback()
        return 0, len(rows) if rows else 0
    finally:
        src_session.close()
        dst_session.close()


def main():
    parser = argparse.ArgumentParser(description="SQLite → MySQL 数据迁移")
    parser.add_argument("--schema-only", action="store_true", help="仅创建表结构")
    parser.add_argument("--full", action="store_true", help="表结构 + 数据迁移")
    parser.add_argument("--dry-run", action="store_true", help="预览数据，不写入")
    args = parser.parse_args()

    if not any([args.schema_only, args.full, args.dry_run]):
        parser.print_help()
        print("\n示例:")
        print("  python scripts/migrate_db.py --schema-only  # 仅建表")
        print("  python scripts/migrate_db.py --full         # 完整迁移")
        print("  python scripts/migrate_db.py --dry-run      # 预览")
        return

    print("=" * 60)
    print(" 数据库迁移工具 — SQLite → MySQL (火山引擎 RDS)")
    print("=" * 60)

    # ── 连接 ──
    print(f"\n📂 SQLite: {SQLITE_PATH}")
    src = get_sqlite_engine()

    print(f"🗄️  MySQL:  {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")

    if args.dry_run:
        # 仅预览
        tables = discover_table_names(src)
        print(f"\n📋 SQLite 中的表: {tables}")
        for t in tables:
            with src.connect() as conn:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"   {t}: {count} 行")
        print("\n✅ 预览完成（未写入 MySQL）")
        return

    dst = get_mysql_engine()

    # ── 表结构迁移 ──
    print("\n" + "─" * 40)
    if not run_alembic():
        sys.exit(1)

    if args.schema_only:
        print("\n✅ 表结构创建完成！")
        return

    # ── 数据迁移 ──
    print("\n" + "─" * 40)
    print("📦 数据迁移...")

    total_ok, total_fail = 0, 0
    for table in TABLES_IN_ORDER:
        # 检查源表是否存在
        insp = inspect(src)
        if table not in insp.get_table_names():
            continue
        ok, fail = migrate_table(src, dst, table)
        total_ok += ok
        total_fail += fail
        icon = "✅" if fail == 0 else "⚠️"
        print(f"   {icon} {table}: {ok} 行")

    print(f"\n🎯 迁移完成: {total_ok} 行成功, {total_fail} 行失败")

    # 验证
    print("\n🔍 验证目标库行数...")
    for table in TABLES_IN_ORDER:
        insp = inspect(dst)
        if table in insp.get_table_names():
            with dst.connect() as conn:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                print(f"   mysql.{table}: {count} 行")


if __name__ == "__main__":
    main()
