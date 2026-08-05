# 对接点详细说明 — Platform Explorer ↔ 现有测评系统

> **目标读者**: 接手此项目的 AI / 开发者
> **前提**: 已阅读 `docs/whitepaper_v3.6.md` (测评白皮书) 和 `ARCHITECTURE_PX.md` (架构设计)

---

## 一、文件地图

```
探索器 (新增, 独立)              现有测评 (保留, 小改)
─────────────────────           ─────────────────────
src/platform_probe/             src/
├── __init__.py                   ├── evaluator.py        ← 不动
├── __main__.py  (CLI入口)        ├── test_runner.py      ← 小改: 读 schema_driven 字段
├── explorer.py  (主协调器)        ├── platform_client.py  ← 新增: from_schema()
├── models.py    (数据模型)        ├── browser_evaluator.py← 可改: 从 schema 读 PHASES
├── confidence.py                 ├── persona_tester.py   ← 可改: 从 schema 读课时
├── l0_auth.py                    ├── schema_adapter.py   ← 新增: 薄适配层
├── l1_capture.py                 ├── rules/              ← 不动
├── l2_structure.py               └── agents/             ← 不动
├── l3_classify.py
├── l4_schema.py                 config/
└── prompts/ (空, Phase 2用)       ├── test_config.yaml   ← 新增2个字段
                                   ├── explorer_config.yaml← 新增
                                   └── dimension_weights.yaml← 不动

output/platform_probe/           backend/ + frontend/     ← 不动
├── platform_schema.yaml  ←── 桥梁文件
├── exploration_report.md
├── capture.json
└── screenshots/
```

---

## 二、数据流

```
                         ① 探索阶段 (独立运行)
                         ─────────────────
  目标平台 URL ──→ PlatformExplorer.explore()
                         │
                         ├── L0: 认证检测 → auth_state.json
                         ├── L1: 流量捕获 → capture.json
                         ├── L2: 结构推断 → (暂跳过)
                         ├── L3: API分类  → api_catalog
                         └── L4: Schema   → platform_schema.yaml ★
                                              exploration_report.md


                         ② 测评阶段 (读取schema)
                         ─────────────────
  platform_schema.yaml ──→ SchemaAdapter
                              │
                              ├── adapter.base_url → PlatformClient
                              ├── adapter.get_auth() → PlatformClient login
                              ├── adapter.get_phases() → BrowserEvaluator
                              ├── adapter.get_agent_chat_endpoint() → TestRunner
                              └── adapter.get_steps() → PersonaTester
```

---

## 三、各模块对接详情

### 3.1 PlatformClient (已实现 ✅)

**新增方法**: `PlatformClient.from_schema(schema_path)`
**位置**: `src/platform_client.py:112-152`

```python
# 旧方式 (仍然可用)
client = PlatformClient(base_url="http://124.174.108.70", ...)

# 新方式 (schema驱动)
client = PlatformClient.from_schema("output/platform_probe/platform_schema.yaml")
client.login()  # 自动从 schema 读取认证方式
client.chat(lesson_id=4, message="你好")  # 自动从 schema 读取 chat 端点
```

**关键**: 旧方式的所有参数仍然有效，`from_schema()` 只是替代手动传参。如果 schema 不存在，回退到旧的硬编码模式。

### 3.2 TestRunner (需要小改)

**位置**: `src/test_runner.py`
**改动**: 读取 `test_config.yaml` 中的 `schema_driven` 和 `platform_schema_path` 字段

```python
# 在 TestRunner.__init__() 中添加 (伪代码, ~10行)
schema_path = config.get("platform_schema_path", "")
if config.get("schema_driven") and schema_path:
    self.client = PlatformClient.from_schema(schema_path)
else:
    self.client = PlatformClient()  # 旧的硬编码模式
```

### 3.3 BrowserEvaluator (需要小改)

**位置**: `src/browser_evaluator.py`
**改动**: `PHASES` 字典可从 schema 动态读取

```python
# 在 BrowserEvaluator.__init__() 中添加 (伪代码, ~15行)
if schema_path:
    from src.schema_adapter import SchemaAdapter
    adapter = SchemaAdapter(schema_path)
    self.phases = adapter.get_phases()
else:
    self.phases = PHASES  # 旧硬编码, 保留
```

### 3.4 PersonaTester (需要小改)

**位置**: `src/persona_tester.py`
**改动**: 课时列表和 Agent 端点从 schema 读取

---

## 四、测试验证步骤

### Step 1: 在已知平台上生成 schema
```bash
cd /opt/agent_eval
python -m src.platform_probe --url http://124.174.108.70 \
    --username student001 --password 123456 \
    --output output/platform_probe
```

### Step 2: 验证 schema 正确性
```bash
# 检查生成的 schema 结构
cat output/platform_probe/platform_schema.yaml | head -100

# 用 Python 验证
python -c "
from src.schema_adapter import SchemaAdapter
a = SchemaAdapter('output/platform_probe/platform_schema.yaml')
print(f'URL: {a.base_url}')
print(f'Phases: {a.get_phases()}')
print(f'Agent endpoint: {a.get_agent_chat_endpoint()}')
print(f'Ready: {a.is_ready()}')
"
```

### Step 3: 用 schema 驱动现有测评
```bash
# 修改 config/test_config.yaml:
#   schema_driven: true
#   platform_schema_path: "output/platform_probe/platform_schema.yaml"

python -m src.persona_tester --mode smoke
```

### Step 4: 对比结果
- 硬编码模式的评分 vs schema驱动模式的评分
- 偏差应在 ±0.1 以内 (允许 schema 精度差异)

---

## 五、向后兼容保证

| 场景 | 行为 |
|------|------|
| `schema_driven: false` (默认) | 完全使用硬编码, 与 v3.6 完全一致 |
| `schema_driven: true` 但 schema 不存在 | 打印警告, 回退到硬编码 |
| `schema_driven: true` 且 schema 存在 | 使用 schema 驱动, 但 API 调用逻辑不变 |
| 探索器未运行 | 不影响任何现有功能 |

---

## 六、常见问题

**Q: 如果探索器发现的端点与硬编码不一致怎么办？**
A: Schema 中的端点优先。如果调用失败，PlatformClient 的退避重试机制仍然生效。

**Q: Schema 中的认证信息错误怎么办？**
A: `from_schema()` 支持 overrides 参数，可手动覆盖：`PlatformClient.from_schema(path, username="correct_user")`

**Q: 如何在 CI 中使用？**
A: 
```bash
# CI 流水线新增步骤:
python -m src.platform_probe --url $TARGET_URL -u $TEST_USER -p $TEST_PASS -q
python -m src.persona_tester --mode smoke --schema output/platform_probe/platform_schema.yaml
```
