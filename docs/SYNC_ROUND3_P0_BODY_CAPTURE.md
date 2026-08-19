# 🔄 AI-A ↔ AI-B 协同同步文档 — Round 3

> **时间**: 2026-08-05  
> **主题**: P0 响应体捕获修复 + Agent B 3项修复审查 + SPA交互探索增强  
> **状态**: ✅ AI-A 完成, AI-B 已交付, 待云端部署验证

---

## 一、AI-A 本轮改动 (数据采集层)

### 1.1 P0: 响应体捕获修复 (`l1_capture.py`)

**问题**: `run_l1_capture()` 硬编码 `capture_bodies=False`，所有 API 响应体从未被捕获。

**根因**: 
- `page.on("response")` 只记录 URL，不读 `response.body()`
- `page.route()` 完整实现存在但未启用
- `explorer.py` 的 L1.55/L1.6 是手动 workaround，覆盖面有限

**修复 (3处)**:

| # | 改动 | 位置 | 影响 |
|---|------|------|------|
| 1 | `_install_response_mode()` 增加 `response.body()` 捕获 | L355-430 | 即使轻量模式也能捕获 JSON 响应体 |
| 2 | `run_l1_capture()` 新增 `capture_bodies=True` 参数 | L768-778 | 默认启用 route 模式 |
| 3 | `_install_route_mode()` 扩面 + XHR/fetch 兜底 | L258-384 | 6个具体模式 + `**/*` 兜底所有 XHR/fetch |

**数据流**:
```
页面加载 → XHR/fetch 发出
  → page.route() 拦截
    → request.post_data (请求体)
    → route.fetch() (完整响应)
    → response_sample (JSON解析)
    → route.fulfill() (返回浏览器, 页面不感知)
    → RouteNode → CaptureResult.routes
      → L2 parser (extract_structure)
      → L3 classifier
      → L4 schema
```

### 1.2 SPA 交互探索增强 (`l1_capture.py`)

**问题**: SPA 探索只在 BFS 找到 <5 页面时触发，且只点 career cards。

**修复**:
- `NavigationExplorer.explore()`: SPA 探索**始终执行**（去掉了 `<5` 条件）
- `_explore_spa_fast()`: 改为三层递进点击
  - 第一层: Career/Subject 卡片
  - 第二层: Phase/Module 卡片 (在 Career 页面内)
  - 第三层: Lesson/Step 卡片 (在 Phase 页面内)
- 每层点击触发 API 调用 → route 拦截器捕获 → L2 提取 Lesson/Step

### 1.3 BFS 深度确认

- `MAX_CRAWL_DEPTH = 3`, `MAX_PAGES = 50` ✅ (已是目标值)
- 旧的截断 bug (`min(max_depth, 2)`, `min(max_pages, 10)`) 已修复 ✅
- `explorer.py` 默认 `max_depth=3, max_pages=50` ✅

---

## 二、AI-B 本轮改动审查 (智能分析层)

### 2.1 改动总览

| # | 文件 | 改动 | 风险评估 |
|---|------|------|---------|
| 1 | `models.py:302,320` | `ExplorationReport` + `PlatformSchema` 新增 `fuzz_findings` 字段 | ✅ 向后兼容 (default_factory=list) |
| 2 | `l4_schema.py:453,498,530,577-606` | `run_l4_schema()` 接受 `fuzz_findings` 参数 → 写入 YAML security 节点 + Markdown 报告 | ✅ |
| 3 | `explorer.py:262-292` | L3.5 fuzz 结果传递到 L4 | ✅ |
| 4 | `l2_structure.py:177-215` | `_unwrap_response()` (6种包装器) + `_find_list_recursive()` (递归搜索) | ✅ 降级安全 (fallback 到原逻辑) |
| 5 | `confidence.py:350-450` | `URL_PATTERN_INDICATORS` + `classify_step_type()` 3信号融合 (DOM+文本+URL) | ✅ |
| 6 | `l3_classify.py` | Step 分类调用更新 | ✅ |

### 2.2 接口契约验证

**fuzz_findings 数据流** (Agent B):
```
explorer.py L3.5: fuzz_findings = run_l3_fuzzer(...)
  → run_l4_schema(..., fuzz_findings=fuzz_findings)
    → PlatformSchema.fuzz_findings
    → ExplorationReport.fuzz_findings
      → YAML: security.fuzz_findings
      → Markdown: 「安全 Fuzz 发现」章节
```

与 AI-A 的边界: **无冲突** ✅
- `fuzz_findings` 是独立字段，不影响现有报告结构
- AI-A 的 Health/Dashboard/Reports 前端不需要感知这个字段

**L2 parser 自适应** (Agent B):
- `_unwrap_response({"data": {...}})` → 自动解包
- `_find_list_recursive(data, max_depth=4)` → 递归搜索
- 主 pattern 失败 → fallback → 不影响现有逻辑

与 AI-A 的边界: **依赖 graph-source 响应体被捕获** ⚠️
- `extract_structure()` 只处理 `r.response_sample` 为真的 route (line 71)
- 需要 AI-A 的 P0 修复确保 graph-source 响应体已填充

### 2.3 潜在问题

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| 1 | `_unwrap_response()` 对 `{data: {count: 5, rows: [...]}}` 可能错误解包 (内层 key 少) | 🟡 低 | 当前逻辑 `len(inner) > len(data) * 0.5` 可防止此情况 |
| 2 | `_find_list_recursive()` 深度 4 可能找到无关列表 | 🟡 低 | 因为有 priority sort (graph-source 优先) |
| 3 | `classify_step_type()` 对无 DOM 元素页面 score 会很低 | 🟡 低 | URL pattern 兜底 (weight 0.4) |

---

## 三、接口对齐清单

### 3.1 AI-A → AI-B (数据采集层提供)

| 接口 | 状态 | 说明 |
|------|------|------|
| `CaptureResult.routes[].response_sample` | ✅ P0修复 | 现在默认捕获完整响应体 |
| `CaptureResult.routes[].request_payload` | ✅ | route 模式提取 POST body |
| `CaptureResult.pages[]` | ✅ | BFS + SPA 三层点击 |
| BFS 深度 3 / 50页 | ✅ | 无截断 |
| SPA 三层交互 | ✅ 新增 | Career→Phase→Lesson 递进点击 |

### 3.2 AI-B → AI-A (智能分析层提供)

| 接口 | 状态 | 说明 |
|------|------|------|
| `TeachingStructure` (L2) | 🔄 依赖响应体 | 需要 graph-source 中有 lessons/steps |
| `APICatalog` (L3) | ✅ | 6信号分类 + Step类型 |
| `PlatformSchema.fuzz_findings` | ✅ 新增 | 高/中风险分类 |
| `ExplorationReport.fuzz_findings` | ✅ 新增 | Markdown 安全章节 |
| `platform_profile.json` | ✅ | url + api_prefix + phases_found |

---

## 四、部署说明

### 4.1 部署文件清单

**AI-A 改动** (2个文件):
```
src/platform_probe/l1_capture.py   ← P0响应体 + SPA增强
```

**AI-B 改动** (6个文件):
```
src/platform_probe/models.py        ← fuzz_findings 字段
src/platform_probe/l2_structure.py  ← _unwrap_response + _find_list_recursive
src/platform_probe/l3_classify.py   ← Step多信号分类
src/platform_probe/l4_schema.py     ← fuzz → YAML/Markdown
src/platform_probe/confidence.py    ← URL_PATTERN_INDICATORS + 3信号融合
src/platform_probe/explorer.py      ← fuzz_findings → L4
```

### 4.2 一键部署

```bash
cd /home/jennifer07/agent_eval && tar czf - \
  --exclude='__pycache__' \
  src/platform_probe/l1_capture.py \
  src/platform_probe/models.py \
  src/platform_probe/l2_structure.py \
  src/platform_probe/l3_classify.py \
  src/platform_probe/l4_schema.py \
  src/platform_probe/confidence.py \
  src/platform_probe/explorer.py \
  | ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 \
  "cd /opt/agent_eval && tar xzf - && systemctl restart agent-eval"
```

### 4.3 验证命令

```bash
# 1. 触发探索
curl -X POST http://124.174.108.70/api/explorer/run \
  -H 'Content-Type: application/json' \
  -d '{"url": "http://124.174.108.70/personalized-secure", "username": "111", "password": "123456"}'

# 2. 检查 capture.json 中是否有 response_sample
ssh root@124.174.108.70 "cat /opt/agent_eval/output/platform_probe/explore_*/capture.json | python3 -c '
import json, sys
data = json.load(sys.stdin)
with_body = [r for r in data[\"routes\"] if r.get(\"response_size\", 0) > 0]
print(f\"Routes with body: {len(with_body)}/{len(data[\"routes\"])}\")
'"

# 3. 检查 platform_schema.yaml 中是否有 security 节点
ssh root@124.174.108.70 "grep -A5 'security:' /opt/agent_eval/output/platform_probe/platform_profile.json 2>/dev/null || echo 'checking schema...'"
```

---

## 五、待解决 / 下次

### 5.1 验证项
- [ ] 云端运行探索，确认 `capture.json` 中 `response_sample` 不再为空
- [ ] 确认 L2 parser 从 graph-source 响应中提取到 Lesson/Step
- [ ] 确认 fuzz_findings 出现在 Markdown 报告中
- [ ] 确认 SPA 三层点击不会导致超时 (每层 1.5s × 8 cards × 3 layers = 36s)

### 5.2 前端待做 (下次会话)
- [ ] Test Runner 预检面板从 schema 动态读取 Phase 列表
- [ ] Dashboard 图表空状态 Canvas 文字改成 i18n
- [ ] 平台画像卡在 Explorer 完成后刷新 (目前需手动刷新页面)

### 5.3 AI-B 下次建议
- [ ] `_explore_spa_full` (L549-626) 是死代码 — 考虑删除或重构到 `_explore_spa_fast`
- [ ] `capture_bodies=True` 后 L1.55/L1.6 可逐步退役 (route 模式已捕获)
- [ ] graph-source 响应体中 `modules` 嵌套结构的利用

---

## 六、快速参考

| 项目 | 值 |
|------|-----|
| 云端地址 | `http://124.174.108.70/test/` |
| SSH | `ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70` |
| 目标平台 | `http://124.174.108.70/personalized-secure` |
| API 前缀 | `/personalized-secure-api/v1` |
| 登录凭证 | `111 / 123456` |
| systemd | `systemctl restart agent-eval` |
| 日志 | `journalctl -u agent-eval --no-pager -n 30` |
| 探索器直接运行 | `./venv/bin/python3 -m src.platform_probe --url ...` |
