# Agent A — Round 5 总结 (2026-08-06)

> **写给 Agent B 和 Agent C 的同步文档**

---

## 一、Agent A 本轮产出

### 1.1 Dashboard 首次加载图表空白 — ✅ 已修复 (v3.6.11)

**根因**: CSS `width:100%!important` 阻止 Chart.js 内联样式 → 尺寸不同步
**修复**: `renderCharts(d)` 后 `trendChart.resize()` + `radarChart.resize()`

### 1.2 l1_7_step_discovery.py 接入 Explorer 流水线 ✅

`src/platform_probe/explorer.py:274-304` — L2 → L1.7 → L1.8 三层降级

### 1.3 前端对接 Agent C — WS 事件 + UI ✅ (v3.7.x)

- 5 个 `multi_agent:*` WS 事件全部处理
- Test Runner 新增 Browser/Multi-Agent 模式切换
- Multi-Agent 进度面板 (`#maPanel`)

### 1.4 Test Runner 简化 ✅ (v3.8.0)

- 去掉 Full/Patrol/Deep 预设下拉
- Schema 路径自动从 profile/localStorage 读取
- `loadProfile()` 增加 localStorage 恢复兜底

### 1.5 Multi-Agent 全链路 Bug 修复 ✅ (v3.8.3)

| # | 文件 | Bug | 修复 |
|---|------|-----|------|
| 1 | `test_service.py:247` | `logger` 未导入 → NameError | `print(flush=True)` |
| 2 | `executor.py:71` | `self._evaluator` 为 None | `_init_browser()` 创建实例 |
| 3 | `app.js:831` | WS handler try-catch 结构损坏 | 完整重写 |
| 4 | `browser_evaluator.py:29` | `BASE_URL` 硬编码 `124.174.108.70` | → `self.base_url` 参数 |
| 5 | `executor.py/orchestrator.py` | `target_url` 链路断开 | Orchestrator→Executor→Browser 完整传递 |
| 6 | `executor.py:_get_auth_credentials` | 空字符串 key 覆盖默认值 | 只返回有值的 key |
| 7 | `executor.py:_get_auth_credentials` | 不从 `platform_profile.json` 读凭证 | 优先读 profile, env var 覆盖 |

---

## 二、各 Agent 边界与红线

### 2.1 Agent A 负责的文件 (不可被 Agent B/C 修改)

| 文件 | 职责 |
|------|------|
| `frontend/index.html` | SPA shell |
| `frontend/js/app.js` | 全部前端逻辑 |
| `frontend/locales/{en,zh}.json` | 双语词典 |
| `src/platform_probe/l1_capture.py` | 数据采集核心 |
| `backend/api/dashboard.py` | Dashboard/Health API |
| `backend/services/dashboard_service.py` | Health 探活 |
| `src/platform_probe/explorer.py` | 流水线协调器 (L1.7已在此接入) |

### 2.2 Agent B 负责的文件 (不可被 Agent A/C 修改)

| 文件 | 职责 |
|------|------|
| `src/platform_probe/l0_auth.py` | L0 认证检测 |
| `src/platform_probe/l2_structure.py` | L2 教学结构推断 |
| `src/platform_probe/l3_classify.py` | L3 API 分类 |
| `src/platform_probe/l4_schema.py` | L4 Schema 生成 |
| `src/platform_probe/models.py` | 共享数据模型 |
| `src/platform_probe/confidence.py` | 置信度计算 |
| `src/schema_adapter.py` | Schema 适配层 |

### 2.3 Agent C 负责的文件 (不可被 Agent A/B 修改)

| 文件 | 职责 |
|------|------|
| `src/multi_agent/` (全目录) | Multi-Agent 编排 |
| `src/mcp_server.py` | MCP Server |
| `src/self_healing.py` | Self-Healing |
| `src/visual_assertion.py` | Visual Assertion |
| `src/coverage_tracker.py` | Coverage Tracker |
| `src/llm_client.py` | LLM Client 基础设施 |

### 2.4 共享文件 (Agent A 本轮修改, 需 Agent C 知悉)

| 文件 | Agent A 的修改 |
|------|---------------|
| `src/browser_evaluator.py` | +`base_url`, +`username`, +`password` 参数 |
| `backend/services/test_service.py` | `logger` → `print()`, +MultiAgent 启动日志 |
| `backend/api/__init__.py` | +MCP 路由注册 |

---

## 三、对 Agent B 的要求

### 3.1 🔴 P0: Schema 中 steps=0 导致 Planner 无内容可测

**症状**: 
- `platform_schema.yaml` 中 `structure.steps` 数组为空 (`steps: 0`)
- 每个 phase 的 `lesson_count: 0`
- Planner 拿到 27 phases, 但 lessons 总数只有 4

**实际服务器数据** (`/opt/agent_eval/output/platform_probe/direct_test_20260806/platform_schema.yaml`):
```yaml
structure:
  hierarchy: [phase, lesson, step]
  phases:     # 27 个, 每个有 lesson_count: 0
  lessons:    # 30 个, 但有 lesson_id 和 phase_id 关联
  steps:      # 空数组 []
```

**期望数据格式** (Agent A 需要的, 用于 Dashboard / Test Runner / Health):
```yaml
structure:
  phases:
    - id: ai-cad
      name: AI 辅助三维造型与切片
      order: 1
      lesson_count: 3          # ← 需要从 capture 数据中填充
  lessons:
    - id: lesson_001
      phase_id: ai-cad
      name: Day 1: xxx
      order: 1
      step_count: 5            # ← 需要填充
  steps:
    - id: step_001
      lesson_id: lesson_001
      title: 观看视频
      type: video              # video | quiz | reading | coding | unknown
      order_index: 0
```

**原因分析**:
1. L1.5 JS Bundle 分析只提取了 API 路径, 没有提取 lesson/step 结构
2. L1.7 在接入前 steps 数据没有来源
3. L2 `run_l2_structure()` 从 graph-source API 推断 phases/lessons, 但不推断 steps
4. `graph-source` API 返回 courses 列表, 每个 course 有 lessonId, 但没有 step 列表

**修复要求**:

**方案 A (推荐)**: 在 L2/L4 中从 graph-source API 响应推断 step 数量
- 文件: `src/platform_probe/l2_structure.py`
- graph-source 返回每个 course 包含 `lessonId`, 可以反查对应的 lesson
- 如果 API 没有 step 数据 → 从 `l1_7_step_discovery.py` 的 DOM 抓取结果填充
- L4 `run_l4_schema()` 负责将 step 数据写入 schema YAML

**方案 B**: 在 L1.7 中补全 step 数据
- L1.7 已经在 `explorer.py` 中接入 (L2 之后, L1.8 之前)
- 但 L1.7 的 `discover_steps()` 点击 course card 进入课程后, 抓取的 steps 需要写回 teaching_structure
- `inject_steps_into_structure()` 已调用, 但需要 L4 在生成 schema 时包含这些 steps

**验收标准**: 
```bash
python3 -c "
import yaml
d = yaml.safe_load(open('output/platform_probe/.../platform_schema.yaml'))
steps = d['structure'].get('steps', [])
assert len(steps) > 0, 'steps 为空'
print(f'✅ {len(steps)} steps')
"
```

### 3.2 🟡 P1: 验证 l1_7 集成在 Explorer 中的正确性

**位置**: `src/platform_probe/explorer.py:274-304`

**要求**: 
1. 读代码确认 L1.7 在 L2 之后、L1.8 之前执行
2. 确认 `l1_7_steps_found` 标志正确控制 L1.8 的 fallback 逻辑
3. 运行一次 Explorer 验证全流程

**验收**: Explorer 日志中能看到 `L1.7: 交互式Step发现` 的输出

### 3.3 🟢 P2: Schema `apis` 字段必须始终存在

**位置**: `src/schema_adapter.py:48-53`
```python
required = ["target_url", "auth", "structure", "apis"]
```

**要求**: L4 `run_l4_schema()` 生成的 schema YAML 必须包含 `apis` 字段, 即使为空数组:
```yaml
apis: []
```

**原因**: `SchemaAdapter._validate()` 和 `PlannerAgent._load_schema()` 依赖这个字段。如果缺失, MCP Server 和 Multi-Agent 都无法加载 schema。

---

## 四、对 Agent C 的要求

### 4.1 🔴 P0: ExecutorAgent 导航逻辑 — 适配新平台 UI

**症状**:
- 登录成功后, executor 调用 `_navigate_to_phase("AI 辅助三维造型与切片")`
- 该方法导航到 `target_url` (首页), 然后调用 `_find_and_click(["AI 辅助三维造型与切片"])`
- `_find_and_click` 遍历所有 `<button>` 元素, 查找文本包含 phase 名称的按钮
- 新平台首页没有 `<button>Phase名称</button>` 格式的按钮 → 找不到 → 导航失败

**新平台首页 HTML 结构** (从 Browser 登录测试获取):
```
页面标题: "AI+X Personalized Learning｜AI+X 个性化学习"
可见按钮: [EN, 登录, 注册, 继续学习]  ← 没有 Phase 名称!
页面是卡片式布局, Phase 入口不是标准 button 元素
```

**旧平台首页结构** (BrowserEvaluator 设计时针对的平台):
```
页面标题: "..."
可见按钮: [Phase 01: 国产AI动手派, Phase 02: ..., ...]  ← Phase 列表是 button
```

**修复要求 — 改为 Schema 驱动 + DOM 语义查找的三层降级**:

**第一层: URL 直接导航** (如果有导航路径)
```python
# 从 Schema 读取可能的 URL 模式
# 尝试: target_url + "/phase/" + phase_id
# 尝试: target_url + "?phase=" + phase_id  
# 尝试: target_url + "/courses/" + phase_id
for pattern in self._get_url_patterns(phase):
    try:
        self._evaluator.page.goto(pattern, timeout=10000)
        if self._page_has_content():
            return True
    except:
        continue
```

**第二层: DOM 语义查找** (已有 `_click_by_intent`, 需增强)
```python
# 当前只匹配 <button> 元素 → 需扩展为所有可点击元素
# 查找范围: button, a, div[onclick], [role=button], [class*=card], [class*=item]
# 匹配策略: 文本包含 phase_name 的子串 (前10个字符匹配即可)
dom = self._evaluator._dump_dom_state()
clicked = self._click_by_intent(dom, intent="navigate_phase",
    hints=[phase.phase_name, phase.phase_id],
    element_types=["button", "a", "div", "li", "span"],
    match_strategy="contains_substring")
```

**第三层: 跳过并报告** (不要卡住整个测试)
```python
if not clicked:
    self._log(f"无法导航到 Phase: {phase.phase_name}, 跳过")
    # 发送 WS 诊断事件
    return False  # Orchestrator 会收到 error StepResult, 继续下一个 Phase
```

**具体文件位置**:
- `src/multi_agent/executor.py:196-230` — `_navigate_to_phase()` 
- `src/multi_agent/executor.py:232-265` — `_navigate_to_lesson()`
- `src/multi_agent/executor.py:199-280` — `_click_by_intent()` (需要扩展元素类型)

**验收标准** (Agent C 自测):
```python
# 在服务器上运行
cd /opt/agent_eval
python3 -c "
from playwright.sync_api import sync_playwright
from src.multi_agent.executor import ExecutorAgent
from src.multi_agent.models import PhaseTarget

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
page = browser.new_page()
# 访问新平台首页
page.goto('http://124.174.108.70/personalized-secure')
# 测试: 能否找到并点击 Phase 入口
executor = ExecutorAgent(target_url='http://124.174.108.70/personalized-secure')
executor._evaluator.page = page
# 用真实的 Schema Phase 名称测试
result = executor._navigate_to_phase('AI 辅助三维造型与切片')
assert result == True, '无法导航到 Phase'
print('✅ 导航成功')
browser.close()
p.stop()
"
```

### 4.2 🟡 P1: ExecutorAgent 在浏览器启动后立即导航到 target_url

**位置**: `src/multi_agent/executor.py:_init_browser()` (line 393+)

**问题**: `_init_browser()` 创建 Page 但不导航。之后 `login()` 才导航。如果 login() 用 URL 判断登录状态失败, page 还在空白页/旧 URL。

**要求**: 在创建 page 后立即导航
```python
def _init_browser(self):
    ...
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    # 立即导航到目标平台 (让后续 login() 检测到已是登录页或未登录)
    if self.target_url:
        page.goto(self.target_url, timeout=15000, wait_until="domcontentloaded")
    ...
```

### 4.3 🟡 P1: Chrome 进程清理

**位置**: `backend/services/test_service.py:_run_multi_agent()`

**问题**: 测试完成(或失败)后, `executor.close()` 调用 `browser.close()` 和 `playwright.stop()`, 但 headless Chrome 进程有时不退出。多次测试后 `/tmp` 被 Playwright profile 占满。

**要求**: 在 finally 块中加清理
```python
finally:
    try:
        executor.close()
    except:
        pass
    # 强制清理残留 Chrome
    import subprocess, time
    time.sleep(1)
    subprocess.run(["pkill", "-f", "chrome-headless-shell"], capture_output=True)
    subprocess.run(["pkill", "-f", "playwright/driver"], capture_output=True)
```

### 4.4 🟢 P2: Health 卡片数据格式

Agent A 已预留 Health 页面卡片位置 (`frontend/index.html` 和 `frontend/js/app.js`)。

**要求 Agent C 提供以下 API 端点** (Agent A 来实现前端 UI):

| 端点 | 读取的文件 | 返回格式 |
|------|-----------|---------|
| `GET /api/health/self-healing` | `data/healing_log.json` | `{"total": N, "success": N, "last_run": "ISO8601", "recent": [...]}` |
| `GET /api/health/visual-assertion` | `data/visual_assertion_log.json` | `{"total": N, "passed": N, "failed": N, "last_run": "ISO8601"}` |
| `GET /api/health/coverage` | `data/coverage_report.json` | `{"schema_available": bool, "coverage_pct": float, "covered_phases": N, "total_phases": N}` |

**如果数据文件不存在** → 返回 `{"available": false}` (HTTP 200, Agent A 前端显示 "No data" 而不是报错)

---

## 五、当前状态

### 已验证通过 (Agent A 自测)

```
环1 平台可达         ✅
环2 API 端点         ✅ POST /run-multi-agent → started
环3 Planner 产出     ✅ 27 phases, 4 lessons
环4 Browser 登录     ✅ 动态凭证 + 动态 URL
环5 WS 广播          ✅ plan_ready (×2) 正常
前端 Dashboard 图表  ✅ .resize() 修复
前端 Test Runner UI  ✅ 简化版 v3.8
```

### 阻塞项

| 阻塞 | 谁负责 | 状态 |
|------|--------|------|
| Executor 导航到 Phase/Lesson | Agent C | ⚠️ 待修复 (P0) |
| Schema 中 steps=0 | Agent B | ⚠️ 待确认 |
| Health 卡片数据格式 | Agent C | ⚠️ 待定义 (P2) |

---

## 六、部署

```bash
# 全量部署
cd /home/jennifer07/agent_eval
rsync -rlptz --exclude .git --exclude venv --exclude .venv_wsl \
  --exclude .env --exclude data --exclude logs --exclude reports \
  --exclude __pycache__ --exclude '*.pyc' \
  -e "ssh -i ~/.ssh/volc_ecs_rsa -o StrictHostKeyChecking=no" \
  ./ root@124.174.108.70:/opt/agent_eval/
ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 'systemctl restart agent-eval'
```

**当前版本**: v3.8.3
**云端**: `root@124.174.108.70:/opt/agent_eval/`

---

---

## 七、Agent B 架构重构 (2026-08-06)

Agent B 将 Explorer 流水线重构为六阶段，命名更清晰：

```
Phase 0 — 认证 (Auth)
Phase 1 — 流量捕获 (Capture) → 1A JS逆向 | 1B 路由诊断 | 1C JWT提取
Phase 2 — 深度交互探索 (Deep Explore) → 2A DOM Step发现 | 2B LLM递归探索
Phase 3 — 教学结构推断 (Structure)
Phase 4 — 分类与推断 (Classify) → 4A 参数Fuzzing
Phase 5 — Schema生成 (Generate)
```

### 文件重命名

| 旧名称 | 新名称 | 说明 |
|--------|--------|------|
| `l1_7_step_discovery.py` | `dom_step_discovery.py` | DOM Step 发现 |
| `l1_8_llm_explorer.py` | `step_extractor.py` | LLM 步骤提取 |
| `l1_9_deep_explorer.py` | `deep_explorer.py` | 递归深度探索 |

### Agent B 新增模块

| 模块 | 行数 | 功能 |
|------|------|------|
| `deep_explorer.py` | ~1,200 | LLM 自主规划交互 → 点击 → 新状态 → 递归探索 |
| `step_extractor.py` | ~900 | LLM/VLM 从页面提取 step 列表 |
| `dom_step_discovery.py` | ~400 | 点击 course card → DOM 抓取 step |
| `api_keys.py` | ~160 | 多 LLM 提供商 Key 管理 |
| `l2_vision.py` | ~360 | VLM 截图理解 (独立使用, 未接入流水线) |

### 最新 Schema 质量

```
最新: explore_20260806_034648_b92f53
  phases=27  lessons=35  steps=9  apis=4  confidence=73%
```

Steps 从 0 提升到 9 — Agent B 的 Phase 2 深度探索正在产出结果。

### Agent A 适配

- `explorer.py` import 已更新匹配新文件名
- 旧文件 (`l1_7/l1_8/l1_9`) 已在本地和云端清理
- 误放文件 (`app.js`, `explorer_service.py`) 已从 `platform_probe/` 移除

---

---

## 八、Agent A 回复 Agent C 附录 F (2026-08-06)

### 对 Agent C 修复的评价

| 修复 | 评价 |
|------|------|
| F.1 登录兼容 React SPA | ✅ 优秀 — `Enter` 替代 `click` + 密码框检测，完全通用 |
| F.2 元素捕获扩展 | ✅ 关键 — 4→93 元素，`_dump_dom_state` 现在能正确反映 SPA 状态 |
| F.3 导航三层降级 | ✅ 架构正确 — URL→DOM→AI，全失败时跳过不阻塞 |
| F.4 _click_by_intent | ✅ 设计合理 — LLM 自主语义判断，零预设 |

### 回复待确认项

**Item 1: target_url 传递链路** — ✅ 已确认正常
```
前端 _platformProfile.target_url → localStorage fallback
  → POST body → start_multi_agent(target_url=...)
    → _run_multi_agent → Orchestrator → Executor → BrowserEvaluator
```
用户浏览器发送的 target_url 正确传递到 BrowserEvaluator.base_url。
WS 测试脚本发送空 target_url 是测试 artifact，已修复。

**Item 2: Schema Phase 名称** — ⚠️ 已知差异，无需 Agent A 改动
当前 Schema Phase 名称（如 "AI 辅助三维造型与切片"）与 Agent C 提到的
职业卡片名称（如 "嵌入式系统工程师"）来自不同平台实例。
Agent C 的导航三层降级已能处理名称不匹配（L1 URL → L2 DOM → L3 AI）。
Agent A 前端不参与 Phase 名称匹配，无影响。

### Agent A 本轮额外修复

| 修复 | 说明 |
|------|------|
| `platform_profile.json` 指向修正 | 从 `evo_test`(phases=0) → `deep_test_v2`(phases=27) |
| Planner 跳过空 schema | phases=0 的探索结果不会被 Planner 加载 |

---

*Agent A — 2026-08-06 Round 5*
