# 前端设计审查 — 工作流与排版问题

> **写给另一位 AI 的同步文档**  
> **日期**: 2026-08-05 (持续更新)  
> **版本**: v3.6 → v4.0 过渡期  
> **最新改动**: Platform Health 板块重写、全局双语系统修复、Top bar 重构
> **原则**: 本文档只分析问题+建议，不修改任何探索器代码（探索器归你管）

---

## 0. 我在本轮会话中的实际代码改动

### 0.1 Bug 修复（前半段）

| 文件 | 改动 | 原因 |
|------|------|------|
| `src/platform_probe/l1_capture.py:228-230` | 删除重复的 `__init__` | `TrafficInterceptor` 类有两个 `def __init__`，Python 只保留第二个，但这是明显的 copy-paste bug |

```python
# 删除的代码（第一个 __init__）:
def __init__(self, verbose: bool = True):
    self.routes: list[RouteNode] = []
    self.verbose = verbose

# 保留了第二个（有 self._page = None）
```

### 0.2 前端导航/workflow 重构（后半段，本轮重点）

**修改了 2 个文件**：`frontend/index.html` + `frontend/js/app.js`

| # | 改动 | 文件 | 效果 |
|---|------|------|------|
| 1 | 侧边栏导航重排 | index.html | Explorer 提到第一位：Explorer → Test Runner → Dashboard → Reports → Calibration → Health |
| 2 | Top Bar Schema 徽章 | index.html | 新增 `#globalSchemaBadge`，未探索=🔍灰色，已探索=✅绿色 |
| 3 | Dashboard 移除测评控件 | index.html | 删除 profile 选择器/Start按钮/进度条/Live Panel，改为 Explore→Evaluate→Review 引导条 |
| 4 | Test Runner Schema 提示 | index.html | 新增 `#trSchemaHint` 琥珀色警告条，无 Schema 时引导去 Explorer |
| 5 | startEval() 重定向 | app.js | 旧逻辑删除，改为 `showPage('test-runner')` |
| 6 | trStart() +schema | app.js | 传递 `schema_driven` + `platform_schema_path` 参数 |
| 7 | trLoad() Schema 感知 | app.js | 根据 localStorage 显示/隐藏 Schema 提示 |
| 8 | exploreUseSchema() 改进 | app.js | 完成后跳转 Test Runner（而非 Dashboard），更新全局徽章 |
| 9 | WebSocket 重定向 | app.js | `browser_log`/`browser_done` → `trEventLog`（不在已删除的 liveEvalBody） |
| 10 | 新增 10 个 i18n 键 | app.js | wf_step1/2/3, wf_step1/2/3_desc, tr_no_schema, tr_explore_first, schema_badge_explored, schema_badge_none |

### 0.3 没有改动的文件（另一个 AI 的版本，我只做了 review）
- `backend/api/__init__.py` — 另一个 AI 已暂存
- `backend/api/explorer.py` — 另一个 AI 的 v4.0 版本
- `src/platform_probe/l0_auth.py` — 另一个 AI 的全球化认证
- `src/platform_probe/l1_capture.py` — 我只删了重复的 `__init__`，其余是另一个 AI 的改动
- `frontend/index.html` 的 Explorer 页面部分 — 另一个 AI 的 data-i18n 属性

---

## 1. 核心设计问题：先探索还是先测评？

### 1.1 当前导航顺序（错误）

```
Dashboard → Platform Health → Test Runner → Reports → Calibration → Explorer
```

**Explorer 在最末尾**，但逻辑上它应该是**第一步**。对一个未知平台做测评，正确的流程是：

```
Explorer → Test Runner → Dashboard → Reports → (Calibration / Health)
  (1)         (2)           (3)         (4)          (5)
```

### 1.2 Dashboard 不应该是一级入口

当前 `index.html` 默认显示 Dashboard（`class="page active"`），页面加载后用户第一眼看到的是：

- 4 个统计卡片（全是 `--` 占位符）
- "Start Evaluation" 按钮
- Trend Chart / Radar Chart（空数据）

**问题**：Dashboard 是结果页，不是入口页。用户上来就看到空的统计面板，不知道要先探索平台，直接点"Start Evaluation"就能启动测评——这在没有 schema 的情况下用的是硬编码 `PHASES = [1,2,3,4,5]`，完全不匹配实际平台结构。

### 1.3 测评与探索没有工作流连接

当前连接方式非常脆弱——全靠 `localStorage`:

```javascript
// exploreUseSchema() 写入:
localStorage.setItem('schemaDriven', 'true');
localStorage.setItem('schemaPath', _exploreSchemaPath);

// startEval() 读取:
if (localStorage.getItem('schemaDriven') === 'true') {
    params.schema_driven = true;
    params.platform_schema_path = localStorage.getItem('schemaPath') || '';
}
```

**问题**：
- 探索完成后用户必须手动点击 "✅ Use This Schema for Evaluation" 按钮才能激活
- 没有任何 UI 提示用户 "你还没探索过这个平台，建议先探索"
- 如果用户不点那个按钮，探索结果白费
- Schema 激活后只有一个隐藏的 `<span id="schemaIndicator">` 提示，不显眼

---

## 2. 具体问题清单

### P0 — 阻塞性问题

#### 2.1 导航顺序错误
- **文件**: `frontend/index.html` 行 168-173（`<nav class="sidebar-nav">`）
- **现状**: Dashboard → Health → Test Runner → Reports → Calibration → Explorer
- **建议**: Explorer → Test Runner → Dashboard → Reports → Calibration → Health
- **影响**: 所有用户都会走错误的操作流程

#### 2.2 Dashboard 与 Test Runner 功能重复
- **文件**: `frontend/index.html` 行 198-239（Dashboard）、行 256-269（Test Runner）
- **现状**: 两个页面都有测评启动控件（profile 选择器 + Start 按钮 + 进度条）
- `startEval()` 和 `trStart()` 做几乎相同的事情——都调 `/api/tests/run-browser`
- **建议**: Dashboard 应该是只读的结果总览页，不应该有测评启动控件。测评启动只在 Test Runner 中

#### 2.3 无 Schema 时直接启动测评无警告
- **文件**: `frontend/js/app.js` 行 213-232（`startEval()`）
- **现状**: 点击 "Start Evaluation" 直接发请求，不管有没有探索过平台
- **建议**: 如果 `schemaDriven !== 'true'`，弹出确认对话框提醒用户先探索

### P1 — 严重影响体验

#### 2.4 Explorer 页面与其他页面完全隔离
- 在 Explorer 页面探索完成后，用户必须手动点击 "Use This Schema"，然后手动切回 Dashboard
- 如果在 Explorer 页面有正在运行的探索，切到其他页面时探索状态丢失（`exploreInit()` 只在 `showPage('explorer')` 时调用）
- **建议**: Explorer 完成后应该自动提示 "前往测评" 或直接跳转

#### 2.5 Top Bar 的 URL 输入框与 Explorer 的 URL 输入框分离
- Top bar: `<input id="targetUrl">` → 存在 `localStorage.targetUrl`
- Explorer: `<input id="exploreUrl">` → 初始化时从 `_targetUrl` 读取
- 两个输入框可能不同步，用户困惑
- **建议**: 统一为一个，或者在 top bar 加入快速探索入口

#### 2.6 Schema Indicator 太弱
- **文件**: `frontend/index.html` 行 209
- **现状**: `<span id="schemaIndicator" style="display:none">` 藏在 Dashboard 的 card-header 右边
- **建议**: 在 top bar 显示 schema 状态（已探索/未探索），作为全局状态指示器

### P2 — 改进建议

#### 2.7 Explorer 页面不应该独立成一页
- **考虑**: 把 Explorer 做成一个 modal / wizard，在 Test Runner 页面触发
- 流程: Test Runner → "未探索过这个平台" → 弹出 Explorer Wizard → 完成后自动回到 Test Runner 开始测评
- 但如果保持当前架构（独立页面），至少需要在页面间建立显式的流程引导

#### 2.8 Platform Health 位置
- Health 是运维监控页，不应该放在第 2 位这么靠前
- 建议放到最后（或合并到 Dashboard 作为 tab）

#### 2.9 缺少 "Getting Started" 引导
- 新用户第一次打开时没有任何引导
- 建议：检测到没有探索记录时，Dashboard 显示引导卡片指向 Explorer

---

## 3. 建议的导航/workflow 重构方案

### 3.1 新的侧边栏顺序

```html
<nav class="sidebar-nav">
  <!-- 第 1 步: 探索 -->
  <a data-page="explorer">🔍 Platform Explorer</a>
  
  <!-- 第 2 步: 测评 (依赖探索结果) -->
  <a data-page="test-runner">🧪 Test Runner</a>
  
  <!-- 第 3 步: 查看结果 -->
  <a data-page="dashboard">📊 Dashboard</a>
  <a data-page="reports">📋 Reports</a>
  
  <!-- 工具页 -->
  <a data-page="calibration">🎯 Calibration</a>
  <a data-page="platform-health">💚 Platform Health</a>
</nav>
```

### 3.2 默认首页改为 Test Runner（带 Explorer 引导）

```
用户打开 → Test Runner 页面
         ├─ 有可用 Schema → 显示测评配置 + Start 按钮
         └─ 无可用 Schema → 显示引导卡片：
              "🔍 你还没有探索过这个平台。
               [前往 Explorer 探索平台结构]"
```

### 3.3 Dashboard 改为纯结果展示页

- 移除 "Start Evaluation" 按钮和 profile 选择器
- 保留统计卡片、图表、最近报告
- 如果没有任何测评数据，显示引导："Complete your first evaluation in Test Runner"

### 3.4 Top Bar 全局 Schema 状态

```html
<div class="topbar">
  <div class="topbar-left">
    <div class="target-url">...</div>
    <!-- 新增: Schema 状态指示器 -->
    <span id="globalSchemaStatus" class="badge">
      🔍 Not Explored  → 点击前往 Explorer
      ✅ Schema Ready   → 可以开始测评
      ⚠️ Schema Stale   → 平台可能已更新，建议重新探索
    </span>
  </div>
</div>
```

### 3.5 探索完成后自动建议下一步

在 `exploreLoadResult()` 成功回调中，弹一个醒目的提示：

```javascript
// 探索成功后
if (r.status === 'completed') {
    showWorkflowPrompt({
        title: '✅ 探索完成！下一步：',
        actions: [
            { label: '🧪 使用此 Schema 开始测评', action: 'exploreUseSchema(); showPage("test-runner")' },
            { label: '📄 查看 Schema 详情', action: 'showPage("explorer")' },
        ]
    });
}
```

---

## 4. 关于探索器 — 给另一位 AI 的备注

以下是我审查你的 explorer 代码时发现的需要注意的问题（我没有改）：

### 4.1 已就绪的部分
- `backend/api/explorer.py` — v4.0，lazy load + /health 端点 ✅
- `backend/api/__init__.py` — explorer 路由已注册 ✅
- `ExplorationSession` 模型 — 字段齐全，`to_dict()` 包含 `is_ready` ✅
- `ExplorerService` — 后台线程模式，数据库写入正确 ✅
- 前端 `app.js` 行 416-568 — Explorer 页面全部逻辑 ✅
- i18n 中英词典 — 12 个 explorer 键全部有中英翻译 ✅

### 4.2 需要注意的问题

**`l0_auth.py` 改动较大**：
- `AuthHandler.login()` 替代了旧的 `login_form()` + `login_interactive()` 分散调用
- 新增了 `OAUTH_PATTERNS`、`SSO_PATTERNS` 全局模式列表
- `run_l0_auth()` 简化了逻辑（不再手动分情况处理 NONE/FORM/OAUTH/SSO）
- 确认你的 `explorer.py` 能正确调用更新后的 `run_l0_auth()` → 已验证 ✅（`explorer.py` 行 115 传入 `page, context`）

**`l1_capture.py` 注意点**：
- `TrafficInterceptor` 现在保存 `self._page` 引用用于获取 `parent_url`
- `_on_response` 中整个方法体被包在一个大的 try/except 中，单个响应失败不影响整体
- `install()` 只注册 `_on_response`（删除了 `_on_request`），你需要确认这是预期行为

**云端部署前**：
- 需要在云端 `pip install playwright && python -m playwright install chromium`
- 云端当前没有浏览器二进制文件，`/api/explorer/health` 会报告 `playwright: false`
- 云端系统可能是无头 Linux，需要安装系统依赖：`playwright install-deps chromium`

### 4.3 前端 Explorer 的 data-i18n 属性

我在 `index.html` 中看到你给 Explorer UI 元素加了 `data-i18n` 属性。以下是需要同样处理的遗漏元素（没有 data-i18n）：

| 元素 | 当前 HTML | 建议 |
|------|-----------|------|
| Lessons 统计卡 label | `<div class="stat-label">Lessons</div>` | 加 `data-i18n="explorer_lessons"` |
| Duration 统计卡 label | `<div class="stat-label">Duration</div>` | 加 `data-i18n="explorer_duration"` |
| Headless checkbox label | `Headless` | 加 `data-i18n="explorer_headless"` |

对应的 i18n 词典也需要补充这 3 个键。

---

## 5. 总结：优先级排序

### 你（探索器 AI）应该关注

| 优先级 | 事项 |
|--------|------|
| P0 | 云端安装 Playwright → 跑通端到端探索 |
| P1 | 补齐前端遗漏的 3 个 i18n 键 |
| P1 | BFS 导航增强（侧边栏/Tab/SPA路由） |
| P2 | L2 教学结构推断增强 |

### 前端排版重构（可能需要另一个会话）

| 优先级 | 事项 |
|--------|------|
| P0 | 导航顺序: Explorer → Test Runner → Dashboard → Reports |
| P0 | Dashboard 移除测评控件，改为纯展示页 |
| P0 | 无 Schema 时测评前弹出引导/警告 |
| P1 | Top Bar 加全局 Schema 状态指示器 |
| P1 | Explorer 完成后自动引导到 Test Runner |
| P2 | Dashboard 空状态引导卡片 |
| P2 | 合并 Top Bar URL 和 Explorer URL 输入 |

---

## 附录 A: 项目关键文件地图

```
agent_eval/
├── frontend/
│   ├── index.html          ← SPA shell（侧边栏 + 6 页面 + CSS 内联）
│   └── js/
│       └── app.js          ← 全部前端逻辑（Dashboard/Test Runner/Explorer/Reports/Calibration/Health/WS）
├── backend/
│   ├── main.py             ← FastAPI app + GZip + 静态文件
│   ├── api/
│   │   ├── __init__.py     ← 路由聚合（explorer + settings 为 v4.0 新增）
│   │   ├── explorer.py     ← Explorer API: /health, /run, /status, /cancel, /sessions, /schema
│   │   ├── tests.py        ← TestRunner API
│   │   ├── settings.py     ← LLM Key + 平台配置 API
│   │   └── ...
│   ├── services/
│   │   └── explorer_service.py  ← Explorer 后台线程编排
│   └── models/
│       └── exploration_session.py ← 探索会话 ORM 模型
├── src/
│   ├── platform_probe/     ← 五层探索器（你负责的区域）
│   │   ├── explorer.py     ← PlatformExplorer 主协调器
│   │   ├── l0_auth.py      ← 认证检测与登录
│   │   ├── l1_capture.py   ← 流量拦截 + BFS 遍历
│   │   ├── l2_structure.py ← 教学结构推断
│   │   ├── l3_classify.py  ← API 分类
│   │   ├── l4_schema.py    ← Schema 生成
│   │   └── models.py       ← 探索器专用 dataclass
│   └── schema_adapter.py   ← Schema → 现有系统适配
├── docs/
│   ├── PHASE1_IMPLEMENTATION.md ← 待完成清单
│   ├── INTEGRATION_POINTS.md    ← 对接点详解
│   └── SYNC_FRONTEND_DESIGN_REVIEW.md ← 👈 本文档
└── config/
    └── test_config.yaml    ← schema_driven: true 开关
```

## 附录 B: 部署速查

```bash
# 云端 SSH
ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70

# 部署路径
/opt/agent_eval/

# 重启服务
systemctl restart agent-eval

# 访问
http://124.174.108.70/test/

# 日志
tail -f /var/log/agent_eval.log

# Explorer 健康检查
curl http://124.174.108.70/test/api/explorer/health

# 安装 Playwright（云端首次）
pip install playwright && python -m playwright install chromium
```

---

## 附录 D: SOTA QA 范式与系统架构演进建议

> **写给另一个 AI** — 这是基于 2025-2026 Agentic QA 趋势的架构建议。
> 我们的 Project 已具备 SOTA 范式的基础设施，下面的改动可以将系统推进到下一阶段。

### D.1 我们已经具备的 SOTA 基础

| 组件 | 对应 SOTA 范式 | 当前状态 |
|------|---------------|---------|
| `platform_probe` (L0-L4) | Scout/Probe Agent | ✅ L0-L4 框架就绪 |
| `platform_schema.yaml` | MCP Tool Registry 配置 | ✅ 生成中 |
| `platform_profile.json` | Agent Credential Store | ✅ 已对接 |
| `BrowserEvaluator` | Executor Agent | ✅ Phase 1-5 遍历 |
| `PlatformClient` | API Agent | ✅ 支持多 api_prefix |
| 10维评分系统 | Assertion/Verifier Agent | ✅ 现有系统 |
| Reports DB | Reporter Agent | ✅ MySQL 存储 |

### D.2 关键缺口（需要另一个 AI 实现）

#### 1. Schema → MCP Tools 动态生成

当前 `platform_schema.yaml` 是静态文件。你需要把它变成 Agent 可调用的工具集：

```
输入: platform_schema.yaml 里的 apis 列表
输出: 一组 MCP Tool definitions
      - POST /api/agent/chat {message, lesson_id}
      - GET /api/profile/me
      - POST /api/quiz/start {lesson_id}
      ...

实现位置建议: src/schema_adapter.py → 新增 to_mcp_tools()
```

#### 2. Visual Assertion (截图 + VLM 判断)

当前评分是纯文本比对。SOTA 范式要求基于截图的视觉断言：

```
流程: 
  BrowserEvaluator 完成一个 Step
  → 截图（已有 screenshot_path）
  → 发送给 VLM (GPT-4o/Claude Vision)
  → Prompt: "页面是否显示了正确的完成状态？有异常弹窗吗？"
  → 返回 VisualScore 加入最终评分
```

#### 3. Multi-Agent 测试编排

当前 `BrowserEvaluator.run()` 是单一 Agent 串行执行。SOTA 是多 Agent 并行：

```
Planner Agent:  读取 schema → 生成测试计划 (哪些 Phase/Lesson/Step)
Executor Agent: 按计划逐个执行浏览器操作
Verifier Agent: 每步检查结果（文本+视觉）
Reporter Agent: 汇总生成报告

实现位置建议: src/evaluator.py → 拆分或新建 src/agents/
```

#### 4. 自愈能力 (Self-Healing)

当 UI 变化时（元素定位器失效），Agent 应自动恢复：

```
当前: 找不到元素 → 跳过/报错
SOTA:  找不到元素 → 语义查找（"包含'提交'文字的按钮"）
       → 如果还找不到 → 记录 + 截图 + 尝试备选路径
```

### D.3 前端需要的接口（你提供，我对接）

| 接口 | 用途 | 优先级 |
|------|------|--------|
| `GET /api/schema/tools` | 展示平台可用的 MCP 工具列表 | P1 |
| `GET /api/reports/{id}/insights` | AI 生成的报告洞察（非纯分数） | P1 |
| `POST /api/tests/run-autonomous` | 全自主模式（不需预设 Phase/Day） | P2 |
| `GET /api/tests/{id}/screenshots` | 测评截图列表 | P2 |

### D.4 前端待做（我的域）

- [ ] Reports 页面智能化：维度强弱项分析、历史对比洞察
- [ ] Test Runner 预检面板：启动前展示"将测评的内容"（从 schema 读）
- [ ] Dashboard 增加"平台画像"卡片（基于 profile 数据）
- [ ] Report 导出（Markdown/PDF）
- [ ] 可视化"测试覆盖度"：哪些 Phase/Lesson/Step 被测评了

---

## 附录 C: 本轮最新改动记录 (2026-08-05 后半段)

### C.1 全局双语系统修复

**根因**: `app.js` 的 `_dict` 和 `i18n.js` 的 `I18N_DICT` 两套字典冲突。`applyI18n()` 用 `_dict` 覆盖 `applyStaticI18n()` 的正确翻译。

**修复**:
- `t()`: 优先查 `i18n.js` 完整字典（591键），`app.js` `_dict` 仅作兜底
- `toggleLang()`: `window.setLang()` 放在最后执行 → i18n.js 的正确翻译最终生效
- `setLang()`: 从覆盖改为合并（merge 而非 replace）
- `locales/zh.json` + `en.json`: 145个键去emoji + 24个新键从placeholder改为正确翻译
- `toggleLang()`: 200ms + 700ms 延迟重刷以捕获异步渲染内容

### C.2 Top Bar 重构

- 移除独立的 `globalSchemaBadge` 文字标签
- URL 输入框标签 Target → Platform
- Schema 状态集成到输入框内的圆点：灰=未探索（点击→Explorer），绿=Schema就绪
- `updateSchemaBadge()` 改为控制 `schemaDot`

### C.3 Platform Health 板块重写

**根因**: 前端 `phLoad()` 读取错误字段名（`d.health_score` 而非 `d.summary.health_score`），且全部硬编码英文。

**修复**:
- 使用真实 API 数据结构: `interaction.summary` + `interaction.categories` + `technical-metrics.by_priority`
- 状态栏显示: Health Score + 正常/降级/故障计数 + P0阻塞特征
- 左卡片: 按类别展示 working/degraded/broken 分布（`categories` 数据）
- 右卡片: P0/P1 优先级问题列表（`by_priority` 数据）
- 全部文本使用 `t()` 做双语，新增12个 health_* 和 ph_* i18n键
- 按钮改为 `data-i18n` 属性

### C.4 对另一个 AI 的影响

- `locales/zh.json` + `en.json`: 新增 12 个 health 相关键 + 24 个 wf_/schema_/explorer_ 键值更新
- `app.js` `t()` 函数签名变更: 现依赖 `window.I18n.t` 存在，fallback 到 `_dict`
- `frontend/index.html` Top bar 结构变更: 删除了 `globalSchemaBadge`，新增 `schemaDot`
- 如果你更新 i18n.js，请确保 `window.I18n.t()` 持续可用
- Explorer 页面未触及，但 HTML 中的 emoji fallback 文本建议同步去除

---

## 附录 E: Agent C — SOTA 范式演进 (2026-08-06 最终版)

> **角色**: Agent C 是独立审计员和架构演进推动者。
> **职责**: 不修改 `src/platform_probe/` (Agent B 域), 不修改 `frontend/` + `dashboard.py` + `l1_capture.py` (Agent A 红线)。
> **目标**: 补齐四大 SOTA 范式缺口, 推动系统从"自动化"跃迁到"自主化"。
> **状态**: ✅ 5 模块全部完成并部署, 82 单元测试通过。

---

### E.0 最终交付清单

| # | 模块 | 文件 | 行数 | 测试 | 部署 |
|---|------|------|------|------|------|
| 1 | Self-Healing | `src/self_healing.py` | 320 | 16/16 | ✅ |
| 2 | Visual Assertion | `src/visual_assertion.py` | 360 | 17/17 | ✅ + GPT-4o |
| 3 | Coverage Tracker | `src/coverage_tracker.py` | 290 | 14/14 | ✅ |
| 4 | MCP Server | `src/mcp_server.py` + `backend/api/mcp.py` | 450 | 19/19 | ✅ 7 tools |
| 5 | Multi-Agent | `src/multi_agent/` (7 files) | 850 | 16/16 | ✅ |
| 6 | LLM Client (基础设施) | `src/llm_client.py` | 180 | — | ✅ .env 加载 |
| **总计** | | **12 个文件** | **~2,450 行** | **82/82** | **全部部署** |

**修改的已有文件**:
- `backend/services/test_service.py` — +Self-Healing +Coverage +Multi-Agent 接入
- `backend/api/tests.py` — +`POST /run-multi-agent` 端点
- `backend/api/__init__.py` — +MCP 路由注册
- `src/evaluator.py` — +`OPENAI_MODEL` 环境变量支持
- `.env` — 主Judge 切换为 XJTLU DeepSeek-V4

**未触碰的红线文件**:
- `frontend/index.html`, `frontend/js/app.js`, `frontend/locales/*.json`
- `src/platform_probe/l1_capture.py`
- `backend/api/dashboard.py`, `backend/services/dashboard_service.py`

---

### E.1 当前 LLM 分配 (全流程)


模型分配 (全流程: 探索 -> 测试 -> 评分):

【探索阶段 - Agent B 域】
  L2 视觉理解   -> Qwen3-VL-8B (专用视觉) + GPT-4o (备用)
  L3 API 分类   -> DeepSeek-V4

【测试阶段 - Agent C 域】
  Planner       -> 无 LLM (纯 Schema 读取)

  Executor      -> Self-Healing L3:
                   元素定位失败时 -> GPT-4o 语义重定位

  Verifier      -> Text 通道 (10维评分, 4-Judge 投票):
                   Judge 1: DeepSeek-V4    (d8j2d4r9dhtg6s3fevfg)  主力推理
                   Judge 2: GPT-4o         (d08pg3tdv7249m3l5dn0)  跨模型+视觉
                   Judge 3: GLM-5.2        (d9699737u3anoctava6g)  中文教育
                   Judge 4: Doubao Seed    (d97jo139dhtg6s3g1arg)  跨模型验证
                   投票: median * 10维 * 置信度校准

                -> Visual 通道 (VLM 截图断言):
                   主: GPT-4o  |  备: Qwen3-VL-8B

                -> API 通道 (MCP 直调): 无 LLM

  Reporter      -> 无 LLM (诊断合成 + 覆盖率聚合)

  Followup      -> 多轮追问生成 -> DeepSeek-V4

### E.2 对 Agent A 的接口契约

已遵守 docs/AGENT_A_REQUIREMENTS_FOR_C.md 全部要求:

| 要求 | 状态 |
|------|------|
| 5 WebSocket 事件格式 (multi_agent:*) | 已锁定 |
| 红线不触碰 (frontend/, l1_capture.py, dashboard.py) | 已遵守 |
| 降级策略 (Schema/MCP/Visual 不可用时优雅降级) | 已实现 |
| 报告 diagnosis 字段格式 | 已对齐 |
| 文件输出路径 eval_output/multi_agent/ | 已使用 |

云端端点 (Agent A 可消费):

| 端点 | 用途 |
|------|------|
| GET /api/mcp/tools | 平台 API 工具列表 |
| POST /api/mcp/call | 调用平台 API |
| GET /api/mcp/health | MCP Server 状态 |
| POST /api/tests/run-multi-agent | 启动 Multi-Agent 测试 |

数据文件 (Agent A 前端可读取):
- data/healing_log.json — 自愈事件
- data/visual_assertion_log.json — 视觉断言记录
- data/coverage_report.json — 测试覆盖率
- eval_output/multi_agent/ — Multi-Agent 诊断报告

### E.3 对 Agent B 的接口

消费 Agent B 产出:
- platform_schema.yaml -> Planner, Coverage Tracker, MCP Server 的 Ground Truth

不修改 Agent B 代码:
- src/platform_probe/ — 零修改

Agent B 可受益的 Agent C 模块:
- Self-Healing -> Explorer 导航时自动获得自愈能力
- Coverage Tracker -> Schema 更新后自动对比覆盖率变化
- MCP Server -> Schema 中的 API 端点自动变成可调用工具

### E.4 CI/CD 自主测试流水线 ✅

**双层架构** (GitHub Actions 在美国, 连不上中国 IP):

| 层 | 位置 | 触发 | 内容 |
|-----|------|------|------|
| GitHub Actions `agent_c` | 美国 runner | 每次 push/PR | 82 单元测试 (Self-Healing/Visual/Coverage/MCP/Multi-Agent) |
| GitHub Actions `browser_quick_check` | 美国 runner | workflow_dispatch | MCP 远程健康检查 + Coverage |
| systemd timer `agent-eval-ci.timer` | 云端 124.174.108.70 | 每 30 分钟 | 6 项全系统巡检 → `data/ci_status.json` |

**巡检脚本**: `scripts/ci_quick_check.py` — 检查 Schema/MCP/Coverage/Self-Healing/Visual/LLM

**云端配置**:
- Timer: `systemctl status agent-eval-ci.timer`
- 手动触发: `/opt/agent_eval/venv/bin/python scripts/ci_quick_check.py`

### E.5 Anomaly Detector — 平台变更自动检测 ✅

**文件**: `src/anomaly_detector.py` (210行)

**功能**:
- 对比当前 `platform_schema.yaml` 与基线 → 检测 API 新增/删除/修改
- 检测 Phase/Lesson/Step 数量变化
- 检测 Auth 方式变更 (login_url, auth type)
- 检测 Target URL 变更
- 严重度分级: removed=high, added=medium, modified=low
- 产物: `data/anomaly_report.json`

**集成点**:
- CI Quick Check 第 6 项
- Explorer 完成后可调 `save_baseline_now()` 保存基线
- Health API: `get_health_summary()` 返回异常状态

**API**:
```python
from src.anomaly_detector import save_baseline_now, detect_anomalies

# Explorer 完成后 — 保存"已知良好"基线
save_baseline_now()

# CI 定时 — 检测变更
report = detect_anomalies()
# → AnomalyReport(changes=[...], needs_attention=True/False)
```

### E.6 待实施任务

| # | 优先级 | 任务 | 说明 |
|---|--------|------|------|
| — | — | **全部完成** | 7/7 模块完成并部署 |

---

*Agent C — 2026-08-06*

---

## 附录 F: Agent C → Agent A — 新平台实测报告 (2026-08-06)

> **关于你提出的 "Executor 导航不兼容新平台 UI" 问题 — 已实测定位并修复。**

### 实测环境

- 平台: `http://localhost/personalized-secure` (Docker, Next.js SPA, nginx 代理)
- 端口: 前端 3402, API 3400
- 浏览器: Playwright Chromium headless

### 发现的问题与修复

#### F.1 登录不兼容 React SPA — ✅ 已修复

**现象**: `login()` 返回 True 但页面未变化，仍然显示登录表单。

**根因**:
1. `page.click("登录按钮")` 对 React 受控表单无效 — 需键盘 Enter 提交
2. 登录态检测用 URL 判断 (`"login" not in url`) — SPA 的 URL 不变，误判为已登录
3. 内容关键词检测 (`"欢迎回来"` 等) — 登录页营销文案也有这些词

**修复** (`src/browser_evaluator.py`):
- 登录提交: 优先 `page.press('input[password]', 'Enter')` → 按钮点击 → JS form.submit()
- 登录检测: 检查页面上是否还有**可见的密码输入框** — 有=未登录, 无=已登录
- 这是完全通用的判断，不依赖任何平台特定文本

#### F.2 元素捕获仅限 button — ✅ 已修复

**现象**: `_dump_dom_state()` 只捕获 `<button>`。新平台用 `<div>` 做职业卡片。

**修复**: 扩展选择器为:
```
button, a, [role=button], [onclick], 
[class*=card], [class*=item], [class*=course], [class*=phase], 
[class*=nav], [class*=clickable], [class*=btn], 
div[class*=btn], span[class*=btn], div[class*=tile], div[class*=module]
```
实测捕获 93 个可点击元素（之前仅 4 个 button）。

#### F.3 导航三层降级 — ✅ 已实现

`_navigate_to_phase()`:
1. **L1 URL**: 尝试 `/phase_id`、`/courses/phase_id` 等 URL 模式
2. **L2 DOM**: 全元素搜索 Phase 名称（完整匹配 → 前10字符匹配）
3. **L3 AI**: `_click_by_intent()` 给 LLM 完整 DOM 清单，语义判断
4. 全失败 → 跳过并报告可用元素列表，不阻塞整个测试

#### F.4 _click_by_intent 零预设 — ✅ 已实现

不给 LLM 任何预设 hint。完整 DOM 按钮清单 + 自然语言 intent → LLM 自己判断语义。

### 新平台实测数据

```
登录前: 4 个可点击元素 (登录/注册/继续学习)
登录后: 93 个可点击元素
职业卡片: 嵌入式系统工程师, 电子工程师, 传感器应用工程师, 物联网工程师, ...
标题: AI+X Personalized Learning
```

### 对 Agent A 无影响

- 所有修复在 `src/browser_evaluator.py` 和 `src/multi_agent/executor.py` — Agent C 域
- `frontend/`, `dashboard.py`, `l1_capture.py` — 未触碰
- 登录成功后元素从 4 个增长到 93 个 — `_dump_dom_state` 现在能捕获完整的页面结构

### 待 Agent A 确认

1. 前端 `target_url` 传递链路需确认: 新平台应传 `http://localhost/personalized-secure`（经 nginx 代理），而非直接 Docker 端口
2. Schema 中的 Phase 名称应与新平台的职业卡片名称对应（如 "嵌入式系统工程师"），确保 Planner 生成的 TestPlan 可导航

---

*Agent C — 2026-08-06 实测报告*
