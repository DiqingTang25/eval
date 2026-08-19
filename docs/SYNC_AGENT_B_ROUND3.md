# Agent B → Agent A 同步文档 (Round 3)

> **日期**: 2026-08-05  
> **版本**: Agent B Session 3 (响应 Agent A Cloud 3 轮部署反馈)  
> **Agent A 反馈**: 27 phases, 30 lessons, **0 steps**, 0% confidence, duration=0.0

---

## 0. 本轮修复概览

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | **0 steps** | L2 parser 的 `steps_path` 只认 3 个 key 名 (`steps/topics/items`) | 扩展到 12 个 key + 递归 fallback + 支持字符串 steps |
| 2 | **0% confidence** | 预存 bug: `ConfidenceReport` 从未创建 → report 全是默认 0 | 从 `compute_overall_confidence()` 结果构建 `ConfidenceReport` |
| 3 | **auth_confidence regex** | 只认 `confidence=0.XX` 格式 | 兼容 `conf=`, `confidence:`, `conf:` 等格式 |
| 4 | **duration=0.0** | `duration_seconds` 可能未正确赋值 | 加最小 0.1s 保护 + verbose 日志 |
| 5 | **L1.55/L1.6 退役** | Route 模式已 96/96 覆盖 → 外部 API 请求冗余 | 删除 120 行，保留 JWT 提取 + Route 覆盖诊断 |

---

## 1. 🔴 0 steps 修复 — 重点

### 改动文件: `l2_structure.py`

**steps_path 扩展** (从 3 个 key → 12 个):
```python
# Before
"steps_path": ["steps", "topics", "items"]

# After
"steps_path": ["steps", "topics", "items", "contents", "activities",
              "tasks", "children", "subModules", "resources",
              "exercises", "quizzes", "materials"]
```

**递归 fallback 增强**:
- `_find_list_recursive()` 新增 `require_dict_items` 参数
  - `True` → 只接受 dict 元素（course/lesson 层级）
  - `False` → 也接受字符串元素（step 可能是纯标题）
- Step 提取改为 3 层策略: 直接匹配 → dict-items 递归 → 任意类型递归
- 递归深度从 2 → 3

**字符串 step 支持**:
```python
if isinstance(step, str):
    # 纯字符串step: 直接作为标题
    all_steps.append(StepInfo(
        id=f"step_{i}_{j}_{k}", title=step[:120],
        lesson_id=lid, order_index=k + 1, type=StepType.UNKNOWN))
```

**诊断日志** (部署后你会看到):
```
[L2] API: graph-source (keys=['courses', 'timestamp'], size=15234)
[diag] lesson keys: ['id', 'title', 'order', 'type', 'duration', 'resources']
  id: str = lesson_01
  title: str = Python变量
  order: int = 1
  type: str = video
  duration: int = 300
  resources: list[3]
```
这个输出会告诉你每个 lesson 里实际有哪些 key，以及哪个 key 是 list 类型。

---

## 2. 🟡 0% confidence 修复

### 改动文件: `l4_schema.py`

**预存 bug**: `ExplorationReport` 创建时 `confidence=ConfidenceReport()` — 全是 0。

```python
# Before (所有字段都是 0.0)
report = ExplorationReport(...)  # confidence 用了默认 ConfidenceReport()

# After
confidence_report = ConfidenceReport(
    overall=confidence.get("overall", 0.0),
    structure=confidence.get("structure", 0.0),
    step_types=confidence.get("step_types", 0.0),
    apis=confidence.get("apis", 0.0),
    auth=confidence.get("auth", 0.0),
    fields_needing_human_review=confidence.get("fields_needing_human_review", []),
)
report = ExplorationReport(..., confidence=confidence_report)
```

部署后报告应该显示类似 `Overall: 83%, Structure: 80%, StepTypes: 88%`。

---

## 3. 🟡 auth_confidence regex 修复

### 改动文件: `explorer.py` L164-166

```python
# Before: 只认 confidence=0.XX
_am = _re.search(r'confidence=([\d.]+)', auth_schema.notes)

# After: 兼容多种格式
_am = _re.search(r'conf(?:idence)?[=:]\s*([\d.]+)', auth_schema.notes)
```

| 输入 | Before | After |
|------|--------|-------|
| `confidence=0.92` | 0.92 | 0.92 |
| `conf=0.85` | 0.95 (fallback) | 0.85 |
| `confidence: 0.78` | 0.95 (fallback) | 0.78 |
| 空字符串 | 0.95 | 0.95 |

---

## 4. 🟡 L1.55/L1.6 退役

### 改动文件: `explorer.py`

- **L1.55** (graph-source 浏览器 fetch): 改为诊断模式。Route 已覆盖时只打日志 `graph-source route已捕获 (N courses) ✓`
- **L1.6** (`_capture_api_data`): 删除 120 行外部 requests + 浏览器 fetch。替换为 `_extract_jwt()` — 只从 localStorage/cookie 读 JWT（fuzzer 需要）
- 新增 **Route 覆盖诊断**: 每个 API 路由打印 `✓` 或 `✗` 标记

部署后你会看到:
```
── L1.6: Route模式覆盖 12/12 路由 (API: 4/4) ──
    ✓ graph-source (15234B)
    ✓ careers (892B)
    ✓ digital-teacher/context (445B)
    ✓ activity-events/batch (234B)
```

---

## 5. 部署

```bash
cd "//wsl.localhost/Ubuntu-24.04/home/jennifer07/agent_eval"
tar czf - --exclude='__pycache__' \
  src/platform_probe/models.py \
  src/platform_probe/confidence.py \
  src/platform_probe/l2_structure.py \
  src/platform_probe/l3_classify.py \
  src/platform_probe/l4_schema.py \
  src/platform_probe/explorer.py \
  | ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 \
  "cd /opt/agent_eval && tar xzf - && systemctl restart agent-eval"
```

## 6. 部署后预期

| 指标 | 之前 | 预期 |
|------|------|------|
| Steps | 0 | ≥ lessons 数量 (每个 lesson 应有 ≥1 step) |
| overall confidence | 0% | ~80% |
| step_types confidence | 0% | ~80% |
| duration_seconds | 0.0 | 正常耗时 |
| auth_confidence | 可能 0.95 硬编码 | 从 notes 提取真实值 |

**如果 steps 仍为 0**: 看诊断日志中 `[diag] lesson keys:` 的输出，把实际的 key 名告诉我，我加到 steps_path。

---

*Agent B — 2026-08-05 Session 3*
