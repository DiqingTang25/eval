# 2026-07-22 变更日志

## 🎯 核心目标：修复报告系统"死页面"问题 + 报告内容存入MySQL

### 问题描述
`http://124.174.108.70/test/` 报告页面：不管点击哪个报告，跳出来的报告永远是**最新那一份**。报告内容依赖文件系统，数据库中只有空的聚合数据。

---

## 📁 改动文件清单

### 新建文件 (4个)
| 文件 | 用途 |
|------|------|
| `backend/alembic/versions/0007_report_content_mysql.py` | 数据库迁移：reports 表新增 markdown_content / html_content 列 |
| `scripts/migrate_reports_to_mysql.py` | 一次性脚本：将历史 reports/*.md 导入 MySQL |
| `CHANGELOG_20260722.md` | 本文件 |

### 修改文件 (6个)
| 文件 | 改动内容 |
|------|---------|
| `backend/models/report.py` | Report ORM 新增 `markdown_content` (Text) + `html_content` (Text) 字段 |
| `backend/services/report_service.py` | `get_report_detail()` 和 `list_reports()` 返回内容字段 + `has_html`/`has_markdown` 标记 |
| `backend/services/test_service.py` | `_persist_results()` 改为读取 Reporter 真实报告文件，不再硬编码；新增 `_read_latest_report_files()` |
| `backend/api/reports.py` | 新增 `GET /{report_id}/html` 独立HTML页面端点；新增 `format=html` 导出；新增 `_wrap_html_page()` / `_md_to_html_simple()` |
| `frontend/index.html` | **修复 `viewReportDetail(reportId)`** — 从忽略ID改为按ID从MySQL加载；新增 `.report-html-content` CSS样式 |
| `frontend/js/pages/reports.js` | **修复 `selectReport(id)`** — 按ID/time戳匹配文件；新增 `renderHtmlContent()` 直接渲染MySQL中的HTML |

### 部署操作
| 操作 | 结果 |
|------|------|
| 代码同步 → `/opt/agent_eval/` | ✅ 8个文件推送 |
| ALTER TABLE reports ADD markdown_content / html_content | ✅ SQLite 直接执行 |
| `scripts/migrate_reports_to_mysql.py` | ✅ 82/92 报告导入 (10个非报告文件跳过) |
| `systemctl restart agent-eval` | ✅ 4次重启 (15:21 → 15:26 → 15:29 → 15:32 → 15:36) |
| 健康检查 | ✅ `{"status":"ok","version":"3.6.0"}` |

---

## 🔧 技术细节

### Bug 根因
```javascript
// frontend/index.html — 修复前
async function viewReportDetail(reportId) {
    // reportId 参数被完全忽略！
    var filesR = await fetch('/test/api/reports/files');
    items.sort((a,b) => b.mtime - a.mtime);  // 按时间排序
    // 总是取第一个(最新)的文件
    var fd = await fetch('/test/api/reports/file/' + items[0].name);
    renderReportDetail(null, data, el);  // ← never uses reportId
}
```

### 修复后
```javascript
// frontend/index.html — 修复后
async function viewReportDetail(reportId) {
    // v3.6: 按ID从MySQL加载
    var detailR = await fetch(API + '/api/reports/' + reportId);
    var detail = await detailR.json();
    if (detail.html_content) {
        el.innerHTML = '...' + detail.html_content + '...';  // 直接渲染HTML
        return;
    }
    // 回退: 按ID匹配文件
    ...
}
```

### 报告内容去硬编码
```python
# backend/services/test_service.py — 修复前
md_content = self._build_report_markdown(...)  # ← 硬编码模板, 所有报告格式一样
html_content = self._markdown_to_html(md_content)

# 修复后
md_content, html_content, md_path, json_path = self._read_latest_report_files()
# ↑ 读取 src/reporter.py (Reporter.generate_report) 刚生成的真实报告文件
# 含: 维度解释 + 边界检测 + 场景详情 + 证据链SHA-256 + 置信度CV + 改进方案
```

---

## 📊 完整数据流 (v3.6)

```
用户点击"开始测评"
    │
    ▼ POST /api/tests/run
TestService.start_run()
    │
    ▼ 后台线程
TestRunner.run_all()
    │ 逐个场景: 发问→对话→追问→边界→评分
    │ WebSocket 实时推送到前端
    │
    ▼
Reporter.generate_report()          ← 真实报告生成器 (src/reporter.py)
    ├── reports/report_{ts}.json    ← 结构化数据
    ├── reports/report_{ts}.md      ← Markdown (维度解释+证据链)
    └── reports/report_{ts}.html    ← HTML (Chart.js仪表盘)
    │
    ▼
TestService._persist_results()
    ├── TestScenario / Turn / Score → MySQL
    ├── _read_latest_report_files() ← 读 Reporter 刚写的真实文件
    └── Report(markdown_content, html_content) → MySQL
    │
    ▼
前端 http://124.174.108.70/test/
    ├── loadReports() → GET /api/reports → 列表(含has_html标记)
    ├── viewReportDetail(id) → GET /api/reports/{id} → 按ID加载
    │   ├── 有html_content → 直接渲染HTML
    │   └── 无 → 回退结构化渲染
    └── GET /api/reports/{id}/html → 独立HTML页面(可打印/PDF)
```

---

## 📈 部署统计

| 指标 | 数值 |
|------|------|
| 数据库报告总数 | 89 |
| 含HTML内容 | 85 |
| 含Markdown内容 | 85 |
| 今天新增 | 87 |
| 服务重启次数 | 4 |
| 服务当前状态 | `active (running)` |
| 健康检查版本 | `3.6.0` |

---

## ⚠️ 已知问题 (未修复)
- `EvidenceMemory: KB upload HTTP 403` — 火山引擎知识库签名校验失败
- `EvidenceMemory: KB search HTTP 400` — 知识库搜索请求格式问题
- 10个历史报告缺少 .md 文件 (web_eval/concurrency/probe 等非教学评测结果)
- 服务器使用 SQLite 而非 MySQL (`DB_TYPE=sqlite`)，MySQL RDS 凭据为占位符
