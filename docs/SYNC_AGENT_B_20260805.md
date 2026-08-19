# Agent B → Agent A 同步文档

> **写给 Agent A 的同步文档**  
> **日期**: 2026-08-05  
> **版本**: Agent B Session 2 (下午)  
> **原则**: 本文档只记录 Agent B 本轮改动 + Agent A 需要知道的接口变化 + 阻塞点

---

## 0. 本轮改动概览（Agent B 视角）

**改动了 6 个文件，全部语法检查通过。**

| 文件 | 改动性质 | 影响 |
|------|----------|------|
| `models.py` | +2 字段 | `ExplorationReport.fuzz_findings`, `PlatformSchema.fuzz_findings` |
| `l2_structure.py` | 增强 | 自适应解包 + 递归搜索 fallback + 调试日志 |
| `l3_classify.py` | 1 行改动 | `classify_pages()` 传 `page.url` 给分类器 |
| `l4_schema.py` | 增强 | `run_l4_schema()` 接受 `fuzz_findings`；报告/YAML 展示 |
| `confidence.py` | 重写 | `classify_step_type()` 3 信号融合 (DOM+文本+URL) |
| `explorer.py` | 1 行改动 | L4 调用传 `fuzz_findings=fuzz_findings` |

---

## 1. 🔴 修复: fuzz_findings → 报告（之前完全丢失）

### 问题
`explorer.py:262` L3.5 Fuzzer 跑完了，结果存在 `fuzz_findings`，但从未传给 L4。
报告和 YAML 里完全看不到任何 fuzz 发现。

### 具体改动

**models.py — 新增字段**
```python
# ExplorationReport (line 299)
fuzz_findings: list[dict] = field(default_factory=list)

# PlatformSchema (line 318)
fuzz_findings: list[dict] = field(default_factory=list)
```

**explorer.py — 传递 fuzz_findings**
```python
# Line 302: 在 run_l4_schema() 调用中加了:
fuzz_findings=fuzz_findings,
```

**l4_schema.py — 3 处联动**
```python
# 1. run_l4_schema() 签名新增 fuzz_findings 参数 (line 453)
def run_l4_schema(..., fuzz_findings: list[dict] = None):

# 2. 附加到 schema 对象 (line 489)
if fuzz_findings:
    schema.fuzz_findings = fuzz_findings

# 3. ExplorationReport 创建时传入 (line 524)
fuzz_findings=fuzz_findings or [],
```

**报告输出新增章节**（`_format_report_md`）
```markdown
## 安全Fuzz发现
| 风险 | 数量 |
|------|------|
| 🔴 高风险 (IDOR/绕过) | 2 |
| 🟡 中风险 (响应差异) | 5 |

### 🔴 高风险发现
- **/api/v1/user/1** — IDOR风险: adjacent_id=2 返回了不同数据
  - Fuzz: adjacent_id=2 → 状态码 200 (原始: 200)
```

**YAML 新增 security 节点**（`_schema_to_dict`）
```yaml
security:
  fuzz_findings:
    - endpoint: /api/v1/user/1
      risk: high
      detail: "IDOR风险: ..."
  high_risk_count: 2
  medium_risk_count: 5
```

### ⚠️ 对你（Agent A）的影响
**无需任何改动。** L3.5 Fuzzer 是你那边的 `l3_fuzzer.py`，我只改了它的消费端（L4）。你的 fuzzer 输出格式不变。

---

## 2. 🟡 增强: L2 parser 自适应

### 问题
当前 parser 的 `API_STRUCTURE_PATTERNS` 期望固定 JSON 结构：
```json
{"courses": [{"modules": [{"steps": [...]}]}]}
```
但真实 API 经常用包装器：
```json
{"data": {"courses": [...]}}
{"result": {"payload": {"courses": [...]}}}
```

### 具体改动 (l2_structure.py)

**新增 `_unwrap_response()` — 自动解包**
```python
@staticmethod
def _unwrap_response(data: dict) -> dict:
    """自动解包常见API响应包装器"""
    wrappers = ["data", "result", "payload", "content", "response", "body"]
    for wrapper in wrappers:
        if wrapper in data and isinstance(data[wrapper], dict):
            inner = data[wrapper]
            if len(inner) > len(data) * 0.5:
                return inner  # 递归解包
    return data
```

**新增 `_find_list_recursive()` — 递归搜索 fallback**
```python
@staticmethod
def _find_list_recursive(obj: dict, max_depth: int = 4) -> list:
    """递归搜索嵌套字典中第一个有意义的 list（跳过 error/meta 等）"""
    skip_keys = {"error", "errors", "message", "status", "code",
                "meta", "pagination", "page", "timestamp"}
    for key, val in obj.items():
        if key.lower() in skip_keys: continue
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
        elif isinstance(val, dict):
            result = _find_list_recursive(val, max_depth - 1)
            if result: return result
    return []
```

**主流程改进**（`extract_structure`）
- 每个 Route 处理前先 unwrap
- 常规 `_extract_list()` 失败 → fallback `_find_list_recursive()`
- Lesson/Step 子结构也使用相同 fallback
- verbose 模式打印 API key 和结构大小（方便调试）

### ⚠️ 对你（Agent A）的影响
**无需任何改动。** L2 parser 是你的边界，但我增强它只是为了让它能从你已经捕获的 graph-source 数据中提取 Lesson/Step。你的任务是确保 graph-source 的 `response_sample` 不为 None。

---

## 3. 🟡 增强: Step 类型分类多信号

### 问题
`classify_step_type()` 只看 DOM 元素 + 文本关键词，完全不用 URL 模式。
一个 URL 是 `/quiz/1` 的页面如果 DOM 里没有 radio button，就被分到 `reading`。

### 具体改动 (confidence.py + l3_classify.py)

**新增 URL 模式映射**
```python
URL_PATTERN_INDICATORS = {
    "video":  {"patterns": ["/video", "/watch", "/player", "/lecture"], "weight": 0.85},
    "coding": {"patterns": ["/code", "/ide", "/editor", "/practice", "/lab"], "weight": 0.85},
    "quiz":   {"patterns": ["/quiz", "/exam", "/test", "/question", "/answer"], "weight": 0.85},
    "chat":   {"patterns": ["/chat", "/agent", "/assistant", "/tutor", "/coach"], "weight": 0.85},
    "upload": {"patterns": ["/upload", "/submit", "/assignment", "/homework"], "weight": 0.80},
    "reading":{"patterns": ["/lesson", "/course", "/module", "/content", "/phase", "/step"], "weight": 0.75},
}
```

**3 信号融合权重**
```
DOM 元素命中: 50% + 关键词: 25% + URL 模式: 25%
URL 模式命中: 40% + 关键词: 30% + 保底: 10%
仅关键词:    30% + 保底: 10%
```

**多信号共识提升**
```python
if signals_hit >= 3:  best_score *= 1.15   # 3信号全中 +15%
elif signals_hit >= 2: best_score *= 1.08   # 2信号 +8%
```

**l3_classify.py 联动**
```python
# 原来
step_type, confidence = classify_step_type(
    dom_elements, text_content, page_title)
# 现在
step_type, confidence = classify_step_type(
    dom_elements, text_content, page_title, page_url=page.url)
```

### ⚠️ 对你（Agent A）的影响
**无需任何改动。** 只要 `PageSnapshot.url` 字段有值即可（你的 L1 已经在填这个字段）。

---

## 4. 阻塞点 — 需要 Agent A 先完成

| 阻塞项 | 当前状态 | 为什么阻塞 Agent B |
|--------|----------|-------------------|
| **graph-source 响应体捕获** | L1.55/L1.6 已修复，待部署验证 | L2 parser 需要 `response_sample` 不为 None 才能提取 Lesson/Step |
| **BFS 深度恢复 3层/50页** | 当前硬限制 2层/10页 | 页面不够 → Step 分类样本不够 |
| **交互探索 (点击卡片)** | 未实现 | 课程内容页未访问 → Step 全都是首页截图的，类型分类无意义 |
| **auth 类型检测 (表单优先)** | 待修复 | 认证失败 → 可能看不到需要登录的课程内容 |

---

## 5. 部署

Agent B 文件部署（不需要同步 .env/data/reports）：

```bash
cd "//wsl.localhost/Ubuntu-24.04/home/jennifer07/agent_eval"
tar czf - --exclude='__pycache__' \
  src/platform_probe/models.py \
  src/platform_probe/l2_structure.py \
  src/platform_probe/l3_classify.py \
  src/platform_probe/l4_schema.py \
  src/platform_probe/confidence.py \
  src/platform_probe/explorer.py \
  | ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 \
  "cd /opt/agent_eval && tar xzf - && systemctl restart agent-eval"
```

验证：
```bash
ssh root@124.174.108.70 "systemctl is-active agent-eval"
curl http://124.174.108.70:8000/api/dashboard/summary
```

---

## 6. 验证清单（部署后）

| # | 验证项 | 期望结果 |
|---|--------|----------|
| 1 | 探索器运行不 crash | L2 打印 `🔍 分析API: graph-source (keys=[...], size=...)` |
| 2 | graph-source 有数据时 | L2 打印 `✅ API驱动: N phases, M lessons` |
| 3 | fuzz 有发现时 | 报告包含「安全Fuzz发现」章节 |
| 4 | Step 类型置信度 | 不再全是 0.4，URL 匹配的应该在 0.5-0.7 范围 |
| 5 | 前端校准/设置/测试 | 功能正常（本轮未改动这些） |

---

*Agent B — 2026-08-05 Session 2*
