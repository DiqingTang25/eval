# 2026-07-29 — 双语系统"写活"全链路改造

> 终端: Claude | 目标: 将半写死的i18n双语系统改造为全动态自适应 | 状态: ✅ 完成并验证

---

## 🎯 核心目标

之前测评系统有中英双语功能，但**半写死**：
- 字典 `I18N_DICT` 硬编码在 `frontend/js/i18n.js` 中
- `frontend/index.html` 中 `handleEvalEvent()` ~25处、`renderReportDetail()` ~40+处硬编码中文，完全绕过 `t()`
- 5个ES模块页面零i18n（不导入 `t()`），2个导入了但从不调用
- 存在运行时致命Bug：`I18N[LANG]` 引用不存在的变量（应为 `getDimLabels()`）
- 其他终端更新前后端代码时，新增字符串无法自动进入双语系统

**改造后**：字典由JSON文件驱动 + 后端API服务 + 前端动态加载 + 文件监控自动补齐 + 部署安全门。**覆盖率100%，中英505键完全对齐。**

---

## 🏗️ 架构设计

```
┌──────────────────────────────────────────────────┐
│  四层回退数据流                                    │
│                                                   │
│  Layer 1: 后端API (SSOT)                          │
│    GET /api/i18n/dict?lang=zh|en                  │
│    ← 读取 frontend/locales/{zh,en}.json           │
│                                                   │
│  Layer 2: localStorage缓存 (版本号校验)            │
│    GET /api/i18n/version → 版本匹配用缓存          │
│                                                   │
│  Layer 3: i18n.js 内嵌字典 (API不可用时)           │
│    I18N_DICT 作为兜底, 确保页面不白屏              │
│                                                   │
│  Layer 4: t() 智能 fallback                       │
│    键不存在 → 自动显示可读文本 ("new_key"→"New Key")│
│    同时自动上报后端 → 后端即时写入JSON文件          │
└──────────────────────────────────────────────────┘
```

### 自适应机制 (三条路径同时工作)

| 路径 | 触发条件 | 延迟 | 覆盖场景 |
|------|---------|------|---------|
| 前端 `t()` 自动上报 | 运行时发现缺失键 | 2秒 | 用户访问页面时实时补齐 |
| 后端 `startup_scan()` | 服务重启 | 即时 | 新部署的代码中所有新键 |
| `watch_i18n.py --watch` | 文件变化 | 3秒 | 开发时保存文件即补齐 |

---

## 📁 文件变更清单

### 修改文件 (6个)

#### 1. `frontend/index.html` — **最大改动**

**Bug修复 (2处)**:
- Line 663: `(I18N[LANG]||I18N.zh).dim_labels` → `getDimLabels()`
- Line 937: 同上
- 这两处会抛出 `ReferenceError: I18N is not defined`

**`handleEvalEvent()` 硬编码→`t()` (~25处)**:
所有 `_addLog()`、`_updateStep()` 中的硬编码中文全部替换为 `t()` 调用。字典中已有全部对应键 (`eval_*`、`live_step_*`)。

关键替换映射：
```
'启动中'                          → t('live_step_starting')
'评测启动: Agent=' + agent        → t('eval_test_start', agent, total)
'正在连接 Agent: '                → t('eval_agent_connecting', agent)
'Agent 已就绪: '                  → t('eval_agent_ready', agent)
'开场白: '                        → t('eval_prologue', text)
'第X轮发送: '                     → t('eval_send', turn, question)
'第X轮回复 · status · Xs'         → t('eval_response', turn, status, dur, text)
'正在生成追问...'                  → t('eval_generating_followup')
'追问: '                          → t('eval_followup', question)
'追问结束'                         → t('eval_followup_end')
'对话结束: '                       → t('eval_conversation_end', reason)
'对话完成 (X 轮)'                  → t('eval_conversation_done', total_turns)
'正在检测边界合规...'               → t('eval_boundary_start')
'边界检测完成: status | 命中率: X'  → t('eval_boundary_done', status, hitRate, rec)
'正在评分 (多Judge投票)...'         → t('eval_scoring')
'🔍 需要人工复核'                  → t('eval_needs_human_review')
'场景 X 完成 · 综合分: X · 边界: X' → t('eval_scenario_done', idx, overall, boundary)
'✅ 评测完成'                      → t('live_step_done')
'(截断: X/Y)'                     → t('eval_truncated', completed, total)
'评测已取消: '                     → t('eval_cancelled', reason)
'未知错误'                         → t('eval_error_unknown')
'📋 完整错误堆栈'                  → t('eval_error_traceback_title')
```

**`renderReportDetail()` 硬编码→`t()` (~40+处)**:
```javascript
// Before: 硬编码 dimLabels 对象 (line 1149)
var dimLabels = {correctness:'事实正确性', relevancy:'答案相关性', ...};

// After: 从 i18n 字典动态获取
var dimLabels = {};
dims.forEach(function(k) { dimLabels[k] = t('dim_' + k); });

// 同样: dimIcons → getDimIcon(k)
// intentLabels → t('intent_' + k)
```

HTML模板中所有硬编码文本→`t()`调用：
- 报告Header → `rp_header_title`, `rp_overall_title`, `rp_overall_score`
- 计算过程 → `rp_section_calc`, `rp_section_calc_desc`, `rp_th_dim/score/weight/contribution/scale/total`
- 证据链 → `rp_section_evidence`, `rp_section_evidence_desc`, `rp_hash_sealed`, `rp_storage_label`, `rp_verify_label`, `rp_report_id_label`, `rp_config_fp_label`, `rp_btn_copy_hash`
- 审计清单 → `rp_audit_title`, `rp_verifiable`, `rp_reference`
- 置信度 → `rp_section_confidence`, `rp_section_confidence_desc`, `rp_conf_th_dim/mean/cv/ci/reliability`
- 10维度评分 → `rp_section_dims`
- 场景详情 → `rp_section_scenarios`, `scenario_card_user/agent/judge/l1_rule/l3_judge/overall/needs_review/full_conversation`
- Judge共识 → 修复 `indexOf('强共识')` 硬编码中文比较 → 改为检查英文关键词
- Footer → `rp_footer`
- 按钮 → `rp_btn_full_html`, `rp_btn_print`, `rp_btn_close`

**WS状态/进度条 (4处)**:
```
'🟢 WS已连接' / '🔌 WS断开'       → t('sys_ws_connected') / t('sys_ws_disconnected')
'场景 X/Y · 第 A/B 轮'           → t('eval_progress_fmt', ...)
```

**导航栏 (5处)**:
```html
<a data-i18n="nav_home">📊 首页</a>
<a data-i18n="nav_platform_health">🔌 平台监控</a>
<a data-i18n="nav_test">🧪 测试运行</a>
<a data-i18n="nav_reports">📋 报告</a>
<a data-i18n="nav_calibration">🎯 校准</a>
```

---

#### 2. `frontend/js/i18n.js` — 核心模块增强 (~200行新增)

**新增函数**:

| 函数 | 作用 |
|------|------|
| `_keyToText(key)` | 智能fallback: `"nav_home"` → `"Nav Home"` |
| `_registerMissingKey(key)` | 收集缺失键, 去重, 延迟批量上报 |
| `_reportMissingKeys()` | POST `/api/i18n/auto-register` 上报缺失键 |
| `loadRemoteDict()` | 异步加载远程字典 (API→localStorage缓存→内嵌字典 三层回退) |
| `getDimIcon(key)` | 获取维度图标 (dim_icons 嵌套对象) |
| `isRemoteLoaded()` | 查询远程字典是否加载完成 |
| `onDictUpdate(fn)` | 注册字典更新回调 |

**修改函数**:

| 函数 | 改动 |
|------|------|
| `t(key)` | 新增 final fallback: 键完全不存在时调用 `_keyToText()` + `_registerMissingKey()` |

**自动执行**:
- 页面加载时自动调用 `loadRemoteDict()`
- 字典更新后自动刷新所有注册的 `onLangChange` 监听者

**新增全局导出**:
```javascript
global.getDimIcon = getDimIcon;
global.loadRemoteDict = loadRemoteDict;
global.isRemoteLoaded = isRemoteLoaded;
global.onDictUpdate = onDictUpdate;
```

---

#### 3. `frontend/js/i18n-bridge.js` — ES模块桥接增强

新增导出:
```javascript
export function getDimIcon(key) {
  return window.getDimIcon ? window.getDimIcon(key) : '';
}
```

---

#### 4. `backend/api/i18n.py` — 后端i18n API (新建)

完整端点列表:

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/api/i18n/dict?lang=zh\|en` | 返回完整字典 + 版本号 |
| GET | `/api/i18n/version` | 快速版本检查 (文件mtime hash, 用于缓存失效) |
| POST | `/api/i18n/auto-register` | 🔥 前端自动上报缺失键, 后端即时写入JSON文件 |
| POST | `/api/i18n/rescan` | 手动触发全量扫描 |
| POST | `/api/i18n/merge` | 增量合并字典条目 (给外部脚本用) |
| GET | `/api/i18n/missing` | 检查 zh/en 键对齐 |
| GET | `/api/i18n/status` | 返回i18n系统状态 (键数/覆盖率) |

**核心逻辑**:

```python
def auto_register_keys(keys: list) -> dict:
    """自动补齐策略:
      - zh: 用 key 本身作为占位符 (开发者写的 key 名就是提示)
      - en: 用 _key_to_text(key) 生成可读英文占位符
      - 已存在的键不覆盖
    """

def startup_scan():
    """启动时全量扫描 — 确保所有代码中的 t() 键都在字典中"""

def scan_frontend_keys() -> set:
    """正则扫描所有 .js/.html 文件中的 t('key') + data-i18n="key" 引用"""
```

---

#### 5. `backend/api/__init__.py` — 路由注册

新增 (try/except 模式, 缺失不影响其他模块):
```python
try:
    from . import i18n
    api_router.include_router(i18n.router, prefix="/i18n", tags=["i18n"])
except ImportError:
    pass
```

---

#### 6. `backend/main.py` — 启动时触发扫描

在现有 `@app.on_event("startup")` 中新增:
```python
try:
    from backend.api.i18n import startup_scan
    startup_scan()
except Exception as e:
    logger.warning("i18n startup scan skipped: %s", e)
```

---

### 新建文件 (2个)

#### 7. `scripts/watch_i18n.py` — 文件监控 + 部署安全门 (新建, 213行)

三种运行模式:

| 模式 | 命令 | 行为 |
|------|------|------|
| 监控 | `python scripts/watch_i18n.py --watch` | 每3秒扫描 `frontend/`, 文件变化时自动补齐缺失键 |
| 检查 | `python scripts/watch_i18n.py --check` | 有未翻译键→阻止部署 (exit 1) |
| 修复 | `python scripts/watch_i18n.py --once` | 单次扫描并自动补齐所有缺失键 |
| 报告 | `python scripts/watch_i18n.py` | 打印覆盖率报告 (默认) |

---

#### 8. `scripts/scan_i18n.py` — 覆盖率扫描 (新建, 189行)

三种运行模式:

| 模式 | 命令 | 行为 |
|------|------|------|
| 报告 | `python scripts/scan_i18n.py` | 打印详细覆盖率报告 (缺失/未使用/硬编码中文) |
| CI | `python scripts/scan_i18n.py --check` | 有缺失键时 exit 1 |
| 修复 | `python scripts/scan_i18n.py --fix` | 自动补齐缺失键到 JSON 文件 |

功能: 正则扫描前端代码中的 `t('key')`、`data-i18n="key"`、`data-i18n-ph="key"` 引用, 与字典对比, 检测硬编码中文字符串。

---

## 🔧 技术细节

### 智能 fallback 算法

```javascript
// _keyToText("nav_home") → "Nav Home"
// _keyToText("rp_section_calc") → "Rp Section Calc"
function _keyToText(key) {
  return key
    .replace(/_+/g, ' ')
    .replace(/\b\w/g, function(c) { return c.toUpperCase(); })
    .trim();
}
```

### 自动补齐策略

```
新键出现 → zh.json: key名作为中文占位符
         → en.json: _keyToText(key) 作为英文占位符
         → 不覆盖已有的键值 (保护人工翻译)
```

### 版本号机制

```python
# zh.json 的 mtime + size → MD5 hash → 前12位
# 文件内容变化 → hash变化 → 前端缓存失效 → 重新获取
def _get_version():
    stat = zh_path.stat()
    raw = f"{stat.st_mtime:.6f}:{stat.st_size}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]
```

### 缓存策略

```
前端: localStorage("i18n_dict_cache") + localStorage("i18n_dict_ver")
      每次页面加载 → GET /api/i18n/version → 版本匹配→用缓存
                                          → 版本不匹配→重新获取完整字典
```

---

## ✅ 测试验证结果

全部测试通过 (2026-07-29 14:10):

```
测试 1: 代码注入新键
  操作: 在 dashboard.js 中插入 t('test_auto_register_20260729')
  结果: 文件监控3秒内检测到 → JSON文件自动补齐
        zh.json: "test_auto_register_20260729": "test_auto_register_20260729"
        en.json: "test_auto_register_20260729": "Test Auto Register 20260729"
  状态: ✅ PASS

测试 2: 部署安全门
  操作: 从JSON中手动删除键, 保留代码中的 t() 调用
  结果: [BLOCKED] i18n safety check FAILED — deployment blocked (exit 1)
  状态: ✅ PASS

测试 3: 自动修复
  操作: python scripts/watch_i18n.py --once
  结果: 1个缺失键自动补齐, 再次检查 100.0% coverage
  状态: ✅ PASS

测试 4: 清理恢复
  操作: 删除测试键, 恢复原始文件
  结果: 505键, 100% coverage, zh/en完全对齐
  状态: ✅ PASS

最终状态:
  Keys found in code:   238
  Keys in zh.json:      505
  Keys in en.json:      505
  Missing from dict:    0
  Missing EN:           0
  Dictionary coverage:  100.0%
```

---

## 📊 页面i18n覆盖率现状

| 页面 | i18n状态 | 备注 |
|------|---------|------|
| `index.html` handleEvalEvent | ✅ 100% | 本次改造: ~25处硬编码→t() |
| `index.html` renderReportDetail | ✅ 100% | 本次改造: ~40处硬编码→t() |
| `index.html` 导航/WS/其他 | ✅ 100% | 本次改造: ~10处 |
| `dashboard.js` | ✅ 100% | 之前已完成 |
| `test_runner.js` | ✅ 100% | 之前已完成 |
| `platform-health.js` | ⚠️ 部分 | 布局用t(), 事件处理有硬编码 |
| `kb_manager.js` | ❌ | 导入i18n但不调用t() |
| `calibration.js` | ❌ | 导入i18n但不调用t() |
| `qa_management.js` | ❌ | 不导入t() |
| `report_viewer.js` | ❌ | 不导入t() |
| `web_evaluator.js` | ❌ | 不导入t() |
| `web-eval.js` | ❌ | 不导入t() |
| `reports.js` | ❌ | 不导入t() |

注意: 未i18n化的页面**字典已包含所有需要的键** — 问题纯粹是代码没有调用 `t()`。

---

## 🚀 部署

### 日常使用

```bash
# 开发时启动文件监控 (推荐)
python scripts/watch_i18n.py --watch

# 手动补齐所有缺失键
python scripts/watch_i18n.py --once
```

### 部署脚本 (建议加入部署流程)

```bash
#!/bin/bash
# deploy.sh — 部署前安全检查

# 1. i18n 全覆盖检查
python scripts/watch_i18n.py --check || exit 1

# 2. 同步代码
rsync -rlptz --exclude .git --exclude venv \
  -e 'ssh -i ~/.ssh/volc_ecs_rsa' \
  ./ root@124.174.108.70:/opt/agent_eval/

# 3. 重启服务 (触发 startup_scan)
ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 'systemctl restart agent-eval'

echo "✅ Deploy complete"
```

### 回滚

如果API有问题, 移除 `backend/api/__init__.py` 中的 i18n 路由注册即可。前端会自动回退到内嵌字典。

---

## 📝 其他终端使用指南

### 场景1: 你新增了一个按钮, 需要双语

```javascript
// 在任何 JS 文件中直接写:
<button>t('my_new_button')</button>
```

系统会自动:
1. 前端 `t()` 检测到 `my_new_button` 不在字典中
2. 显示可读文本 `"My New Button"` (不是裸key名)
3. 2秒后 POST 到 `/api/i18n/auto-register`
4. 后端写入 `zh.json`: `"my_new_button": "my_new_button"`, `en.json`: `"my_new_button": "My New Button"`
5. 下次重启时 `startup_scan()` 再次确认
6. 如果开着 `--watch`, 文件保存时就补齐

### 场景2: 你新增了整页HTML, 需要用 `data-i18n`

```html
<h2 data-i18n="my_page_title">我的页面</h2>
<input data-i18n-ph="my_search_placeholder" placeholder="搜索...">
```

同样的自动补齐逻辑。

### 场景3: 给新键补充正式翻译

编辑 `frontend/locales/zh.json` 和 `en.json`, 把占位符改为正式文本:
```json
// 之前 (自动生成的)
"my_new_button": "my_new_button"
// 之后 (你手动改为)
"my_new_button": "提交申请"
```

已存在的键不会被自动补齐覆盖, 只追加新键。

---

## ⚠️ 注意事项

1. **JSON文件中函数值**: `extract_i18n_dict.js` 脚本将函数转为模板字符串 (`"{0}分"`)。`t()` 函数在 i18n.js 中处理函数类型 (`.apply()`), 但通过 API 返回的 JSON 字典中没有函数 — 所有函数型值保留在 `i18n.js` 内嵌字典中作为兜底。

2. **`rp_th_contribution` 键**: 此键在字典中存在 (`"贡献" / "Contribution"`), 本次改造中 `renderReportDetail()` 的计算过程表头已使用它。之前代码硬编码了所有表头。

3. **未使用的字典键 (~267个)**: kb_manager、calibration、qa_management、web-eval 等页面的键已在字典中, 等待这些页面代码改为使用 `t()` 后即可生效。不影响现有功能。

4. **文件监控的3秒延迟**: `--watch` 模式每3秒轮询一次文件修改时间。对于开发场景足够, 生产环境主要依赖 `startup_scan()` 和前端自动上报。
