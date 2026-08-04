#!/usr/bin/env python3
"""将 reports/ 目录下已有的 .md / .json 报告导入 MySQL

用法:
    python scripts/migrate_reports_to_mysql.py          # 导入全部
    python scripts/migrate_reports_to_mysql.py --dry-run  # 预览, 不写入
    python scripts/migrate_reports_to_mysql.py --report report_20260701_160012  # 单个

要求:
    1. 已运行 alembic upgrade head (确保 reports 表有 markdown_content / html_content 列)
    2. .env 中 db_type=mysql 或设置好 MYSQL_* 变量
"""

import json
import os
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime, timezone

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_DIR = PROJECT_ROOT / "reports"


def get_sync_db():
    """获取同步数据库会话"""
    from backend.config import settings
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = settings.sync_database_url
    engine = create_engine(url, echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


def parse_timestamp_from_filename(name: str) -> str:
    """从文件名提取时间戳: report_20260701_160012 -> 2026-07-01 16:00:12"""
    m = re.match(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def markdown_to_html(md_text: str) -> str:
    """将 Markdown 报告转换为简单的 HTML"""
    try:
        import markdown
        return markdown.markdown(md_text, extensions=['tables', 'fenced_code', 'codehilite'])
    except ImportError:
        pass

    # 纯 Python 简易 Markdown → HTML (不需要额外依赖)
    lines = md_text.split('\n')
    html_lines = []
    in_code_block = False
    code_lines = []

    for line in lines:
        # 代码块
        if line.strip().startswith('```'):
            if in_code_block:
                html_lines.append(f'<pre><code>{"".join(code_lines)}</code></pre>')
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_lines.append(line + '\n')
            continue

        # 标题
        if line.startswith('#### '):
            html_lines.append(f'<h4>{line[5:]}</h4>')
        elif line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
        # 水平线
        elif line.strip() == '---':
            html_lines.append('<hr>')
        # 粗体
        elif '**' in line:
            html_lines.append(re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line) + '<br>')
        # 列表项
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            html_lines.append(f'<li>{line.strip()[2:]}</li>')
        # 表格行 (简易)
        elif line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().split('|')[1:-1]]
            if all(c.startswith('---') or c.startswith(':--') for c in cells):
                continue  # 跳过分隔行
            if not html_lines or '<table>' not in ''.join(html_lines[-3:]):
                tag = 'th'
                row_html = '<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>'
                html_lines.append(row_html)
                if '<table>' not in ''.join(html_lines[-5:]):
                    html_lines.insert(-1, '<table>')
            else:
                html_lines.append(f'<tr>{"".join(f"<td>{c}</td>" for c in cells)}</tr>')
        elif line.strip():
            html_lines.append(f'<p>{line}</p>')
        else:
            html_lines.append('<br>')

    # 关闭未关闭的代码块
    if in_code_block:
        html_lines.append(f'<pre><code>{"".join(code_lines)}</code></pre>')

    return '\n'.join(html_lines)


def migrate_all(dry_run: bool = False, target_name: str = None):
    """将所有报告 .md 文件导入 MySQL"""
    from backend.models import Report

    if not REPORTS_DIR.exists():
        print(f"❌ reports/ 目录不存在: {REPORTS_DIR}")
        return

    # 收集所有 JSON 报告 (以 JSON 为基准, 因为包含结构化数据)
    json_files = {}
    for f in REPORTS_DIR.iterdir():
        if not f.is_file() or f.suffix.lower() != '.json':
            continue
        json_files[f.stem] = f

    if target_name:
        if target_name in json_files:
            json_files = {target_name: json_files[target_name]}
        else:
            print(f"❌ 未找到报告: {target_name}")
            return

    print(f"📋 发现 {len(json_files)} 个 JSON 报告")
    if dry_run:
        print("🔍 DRY RUN 模式 — 不会写入数据库\n")

    db = get_sync_db()
    imported = 0
    skipped = 0
    errors = []

    for name, json_path in sorted(json_files.items()):
        md_path = REPORTS_DIR / f"{name}.md"
        if not md_path.exists():
            errors.append(f"{name}: 缺少 .md 文件")
            continue

        try:
            # 读取 JSON (结构化数据)
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # 读取 Markdown
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            # 生成 HTML
            html_content = markdown_to_html(md_content)

            # 提取 summary
            summary = json_data.get('summary', json_data)
            timestamp = json_data.get('timestamp') or parse_timestamp_from_filename(name)

            if dry_run:
                print(f"  📄 {name}")
                print(f"     timestamp: {timestamp}")
                print(f"     overall: {summary.get('avg_scores', {}).get('overall', 'N/A')}")
                print(f"     md: {len(md_content)} chars, html: {len(html_content)} chars")
                continue

            # 检查是否已存在 (按 timestamp 匹配)
            from sqlalchemy import select
            existing = db.execute(
                select(Report).where(Report.timestamp == timestamp)
            ).scalar_one_or_none()

            if existing:
                # 更新已有记录的内容
                existing.markdown_content = md_content
                existing.html_content = html_content
                if not existing.summary_json:
                    existing.summary_json = summary
                print(f"  ✏️ 更新: {name} (id={existing.id[:8]}...)")
            else:
                # 创建新记录 (无 session_id 关联, 使用 standalone UUID)
                import uuid
                report = Report(
                    session_id=f"migrated_{uuid.uuid4().hex[:12]}",
                    timestamp=timestamp,
                    summary_json=summary,
                    markdown_path=str(md_path.relative_to(PROJECT_ROOT)),
                    json_path=str(json_path.relative_to(PROJECT_ROOT)),
                    markdown_content=md_content,
                    html_content=html_content,
                )
                db.add(report)
                print(f"  ➕ 新建: {name}")

            imported += 1

        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  ❌ {name}: {e}")

    if not dry_run:
        try:
            db.commit()
            print(f"\n✅ 已提交 {imported} 条报告到 MySQL")
        except Exception as e:
            db.rollback()
            print(f"\n❌ 提交失败: {e}")
            return

    db.close()

    if skipped:
        print(f"⏭️ 跳过 {skipped} 条 (已存在)")
    if errors:
        print(f"\n⚠️ {len(errors)} 条错误:")
        for e in errors:
            print(f"  - {e}")

    print(f"\n📊 总计: {imported} 导入, {skipped} 跳过, {len(errors)} 错误")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 reports/ 目录的 .md 报告导入 MySQL")
    parser.add_argument("--dry-run", action="store_true", help="预览模式, 不写入")
    parser.add_argument("--report", help="只导入指定报告名 (不含扩展名)")
    args = parser.parse_args()

    migrate_all(dry_run=args.dry_run, target_name=args.report)
