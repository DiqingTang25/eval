"""Reports API 路由 — v3.5: 含证据链验证端点"""

from pathlib import Path
from sqlalchemy import select

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.report_service import ReportService
from backend.models import Report, EvalScore, EvidenceTrail, TestSession, TestScenario

router = APIRouter()
report_service = ReportService()

_REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


@router.get("")
async def list_reports(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """报告列表"""
    return await report_service.list_reports(db, page, page_size)


@router.get("/compare")
async def compare_reports(
    ids: str = Query(..., description="Comma-separated report IDs"),
    db: AsyncSession = Depends(get_db),
):
    """对比多个报告"""
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if len(id_list) < 2:
        raise HTTPException(400, "Need at least 2 report IDs to compare")
    if len(id_list) > 5:
        raise HTTPException(400, "Can compare at most 5 reports")
    return await report_service.compare_reports(db, id_list)


@router.get("/files")
async def list_report_files():
    """列出 reports/ 目录下的可视化报告文件 (persona_tester 生成)

    按报告名分组, 每组含 html/json/md 三种格式的下载/查看链接。
    HTML 可在浏览器直接打开 (可视化), 任意格式可下载。
    """
    if not _REPORTS_DIR.exists():
        return {"items": [], "count": 0}
    groups: dict[str, dict] = {}
    for f in _REPORTS_DIR.iterdir():
        if not f.is_file() or f.suffix.lower() not in (".html", ".json", ".md"):
            continue
        g = groups.setdefault(f.stem, {"name": f.stem, "formats": {}, "mtime": 0})
        try:
            st = f.stat()
        except OSError:
            continue
        fmt = f.suffix.lstrip(".").lower()
        g["formats"][fmt] = {
            "url": f"/reports/{f.name}",   # 静态挂载, 可查看/下载
            "file": f.name,
            "size": st.st_size,
        }
        g["mtime"] = max(g["mtime"], int(st.st_mtime))
    items = sorted(groups.values(), key=lambda x: x["mtime"], reverse=True)
    return {"items": items, "count": len(items)}


@router.get("/{report_id}")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    """获取报告详情"""
    detail = await report_service.get_report_detail(db, report_id)
    if not detail:
        raise HTTPException(404, "Report not found")
    return detail


@router.get("/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    """导出报告"""
    detail = await report_service.get_report_detail(db, report_id)
    if not detail:
        raise HTTPException(404, "Report not found")

    if format == "json":
        return detail
    elif format == "csv":
        # 简单 CSV 导出
        dims = detail["summary_json"].get("avg_scores", {})
        lines = ["dimension,score"]
        for k, v in dims.items():
            lines.append(f"{k},{v}")
        return PlainTextResponse("\n".join(lines), media_type="text/csv")
    elif format == "html":
        # v3.6: 返回完整HTML页面
        html_content = detail.get("html_content", "")
        if not html_content:
            raise HTTPException(404, "No HTML content for this report")
        return _wrap_html_page(detail, html_content)
    else:
        raise HTTPException(400, "Format must be json, csv or html")


@router.get("/{report_id}/html")
async def view_report_html(report_id: str, db: AsyncSession = Depends(get_db)):
    """v3.6: 以独立HTML页面查看报告 (可直接用浏览器打开)"""
    from fastapi.responses import HTMLResponse
    detail = await report_service.get_report_detail(db, report_id)
    if not detail:
        raise HTTPException(404, "Report not found")
    html_content = detail.get("html_content", "")
    if not html_content:
        # 如果有 markdown_content, 现场转换
        md = detail.get("markdown_content", "")
        if md:
            html_content = _md_to_html_simple(md)
        else:
            raise HTTPException(404, "No HTML or Markdown content for this report")
    return HTMLResponse(content=_wrap_html_page(detail, html_content))


def _wrap_html_page(detail: dict, body_html: str) -> str:
    """将报告HTML内容包装成完整页面"""
    summary = detail.get("summary_json", {})
    avg = summary.get("avg_scores", {}) if summary else {}
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Agent 测评报告 — {detail.get('timestamp', '')}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6;padding:20px;max-width:1100px;margin:0 auto}}
.report-header{{background:linear-gradient(135deg,#0ea5e9,#2563eb);color:#fff;padding:24px 32px;border-radius:14px 14px 0 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
.report-header h1{{font-size:22px;font-weight:700}}
.report-header .score{{text-align:center}}
.report-header .score-num{{font-size:48px;font-weight:800;line-height:1}}
.report-body{{background:#fff;padding:24px 32px;border-radius:0 0 14px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 4px 12px rgba(0,0,0,.04)}}
.report-body h1,.report-body h2,.report-body h3,.report-body h4{{margin:16px 0 8px;color:#0c4a6e}}
.report-body h2{{border-bottom:2px solid #e2e8f0;padding-bottom:6px}}
.report-body table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}}
.report-body th,.report-body td{{padding:8px 12px;border:1px solid #e2e8f0;text-align:left}}
.report-body th{{background:#f8fafc;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#64748b}}
.report-body code{{background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:12px}}
.report-body pre{{background:#0f172a;color:#e2e8f0;padding:14px 18px;border-radius:8px;overflow-x:auto;font-size:12px;line-height:1.5;margin:10px 0}}
.report-body pre code{{background:none;color:inherit;padding:0}}
.report-body hr{{border:none;border-top:1px solid #e2e8f0;margin:16px 0}}
.report-body strong{{color:#0c4a6e}}
.report-body li{{margin:4px 0 4px 20px}}
.footer{{text-align:center;color:#94a3b8;font-size:11px;margin-top:20px}}
@media(max-width:768px){{.report-header{{flex-direction:column;text-align:center}}.report-body{{padding:16px}}}}
</style>
</head>
<body>
<div class="report-header">
<div><h1>🤖 AI Agent 测评报告</h1><p style="opacity:.8;margin-top:4px">{detail.get('timestamp', '')} · 综合评分 {avg.get('overall', '-')}/5.0</p></div>
<div class="score"><div class="score-num">{avg.get('overall', '-')}</div><div style="opacity:.7">/ 5.0</div></div>
</div>
<div class="report-body">
{body_html}
</div>
<div class="footer">报告由 AI Agent 评测平台 v3.6 自动生成 · <a href="/test/api/reports/{detail.get('id','')}/export?format=json">下载JSON</a></div>
</body>
</html>"""


def _md_to_html_simple(md_text: str) -> str:
    """简易 Markdown → HTML (无外部依赖)"""
    import re
    lines = md_text.split('\n')
    html = []
    in_code = False
    in_table = False

    for line in lines:
        if line.strip().startswith('```'):
            if in_code:
                html.append('</code></pre>')
                in_code = False
            else:
                html.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            html.append(line + '\n')
            continue
        m = re.match(r'^(#{1,4})\s+(.+)$', line)
        if m:
            level = len(m.group(1))
            html.append(f'<h{level}>{m.group(2)}</h{level}>')
            continue
        if line.strip() == '---':
            html.append('<hr>')
            continue
        if line.strip().startswith('|') and line.strip().endswith('|'):
            cells = [c.strip() for c in line.strip()[1:-1].split('|')]
            if all(re.match(r'^:?-{3,}:?$', c) for c in cells):
                continue
            if not in_table:
                html.append('<table>')
                in_table = True
            tag = 'th' if html[-1] == '<table>' else 'td'
            html.append('<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>')
            continue
        elif in_table:
            html.append('</table>')
            in_table = False
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'`([^`]+)`', r'<code>\1</code>', line)
        if re.match(r'^\s*[-*]\s+', line):
            html.append(f'<li>{line.strip()[2:]}</li>')
            continue
        if line.strip():
            html.append(f'<p>{line}</p>')
        else:
            html.append('<br>')

    if in_table:
        html.append('</table>')
    if in_code:
        html.append('</code></pre>')
    return '\n'.join(html)



@router.get("/file/{report_name}")
async def get_report_file(report_name: str):
    """从 reports/ 目录读取报告 JSON 文件并返回完整数据"""
    import json as _json
    file_path = _REPORTS_DIR / f"{report_name}.json"
    if not file_path.exists():
        raise HTTPException(404, f"Report file not found: {report_name}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return _json.load(f)


@router.get("/verify/file/{report_name}")
async def verify_report_file(report_name: str):
    """验证报告文件完整性: 重算 self_hash 与记录值比对

    这是报告可信度的核心验证端点:
    1. 读取报告 JSON
    2. 提取 recorded self_hash
    3. 重算 computed self_hash
    4. 比对 → 返回验证结果

    同时验证场景哈希链的连续性。
    """
    import json as _json
    file_path = _REPORTS_DIR / f"{report_name}.json"
    if not file_path.exists():
        raise HTTPException(404, f"Report file not found: {report_name}.json")

    with open(file_path, "r", encoding="utf-8") as f:
        report = _json.load(f)

    try:
        from src.evidence_builder import EvidenceBuilder
    except ImportError:
        raise HTTPException(500, "EvidenceBuilder module not available")

    # 整体完整性验证
    integrity = EvidenceBuilder.verify_report_integrity(report)

    # 场景哈希链验证
    evidence = report.get("evidence", {})
    chain = evidence.get("scenario_chain", [])
    chain_verify = EvidenceBuilder.verify_scenario_chain(chain) if chain else None

    # 配置指纹
    config_fp = evidence.get("config_fingerprint", "")

    return {
        "report_name": report_name,
        "timestamp": report.get("timestamp", ""),
        "integrity": integrity,
        "chain_verification": chain_verify,
        "config_fingerprint": config_fp,
        "verified_at": __import__("datetime").datetime.now().isoformat(),
    }


@router.get("/{report_id}/evidence")
async def get_report_evidence(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取报告的完整证据链数据 (含 TOS 审计链接)

    从 DB 查询:
    1. 报告关联的 test_session
    2. 该 session 的所有 eval_scores (含 evidence_hash)
    3. 该 session 的所有 evidence_trail 记录 (含 TOS URL)
    """
    from backend.models import Report, EvalScore, EvidenceTrail, TestSession, TestScenario

    r = await db.execute(select(Report).where(Report.id == report_id))
    report = r.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    session_id = report.session_id
    if not session_id:
        raise HTTPException(404, "Report has no associated session")

    # 查询 test_session
    ts_r = await db.execute(select(TestSession).where(TestSession.id == session_id))
    ts = ts_r.scalar_one_or_none()

    # 查询所有 eval_scores (含证据字段)
    scores_r = await db.execute(
        select(EvalScore).join(TestScenario).where(TestScenario.session_id == session_id)
    )
    scores = scores_r.scalars().all()

    # 查询 evidence_trail
    trails_r = await db.execute(
        select(EvidenceTrail).where(EvidenceTrail.session_id == ts.session_id if ts else session_id)
    )
    trails = trails_r.scalars().all()

    score_items = []
    for s in scores:
        score_items.append({
            "id": s.id,
            "overall": s.overall,
            "evidence_hash": s.evidence_hash or "",
            "evidence_tos_key": s.evidence_tos_key or "",
            "evidence_tos_url": s.evidence_tos_url or "",
            "merkle_root": s.merkle_root or "",
            "chain_tx_hash": s.chain_tx_hash or "",
        })

    trail_items = []
    for t in trails:
        trail_items.append({
            "id": t.id,
            "artifact_type": t.artifact_type,
            "tos_key": t.tos_key,
            "tos_url": t.tos_url or "",
            "sha256": t.sha256,
            "file_size": t.file_size,
            "storage_tier": t.storage_tier,
            "worm_locked": t.worm_locked,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return {
        "report_id": report_id,
        "session_id": session_id,
        "n_scores": len(score_items),
        "n_trails": len(trail_items),
        "scores": score_items,
        "trails": trail_items,
        "tos_configured": bool(__import__("os").getenv("VOLC_ACCESS_KEY")),
    }

@router.delete("/{report_id}")
async def delete_report(report_id: str, db: AsyncSession = Depends(get_db)):
    """删除报告"""
    ok = await report_service.delete_report(db, report_id)
    if not ok:
        raise HTTPException(404, "Report not found")
    return {"ok": True}
