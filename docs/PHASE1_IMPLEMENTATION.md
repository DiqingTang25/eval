# Phase 1 实现清单 — Platform Explorer (PX)

> **状态**: ✅ 核心框架已实现，以下为待完成项
> **接手AI**: 按此清单逐项完成，每完成一项打勾

---

## ✅ 已完成 (本次实现)

- [x] `src/platform_probe/` 目录结构
- [x] `models.py` — 全部 dataclass 数据模型 (L0~L4)
- [x] `confidence.py` — 6信号分类器 + Step类型分类器 + 置信度汇总
- [x] `l0_auth.py` — AuthDetector + AuthHandler + SessionManager
- [x] `l1_capture.py` — TrafficInterceptor + NavigationExplorer(BFS) + PageSnapshotter
- [x] `l2_structure.py` — Phase 1 简化版 (URL模式+标题推断)
- [x] `l3_classify.py` — APIClassifier (6信号) + StepTypeClassifier + LLMEnumerator(接口)
- [x] `l4_schema.py` — SchemaGenerator + Redactor + SchemaValidator
- [x] `explorer.py` — PlatformExplorer 主协调器 (5层流水线)
- [x] `__main__.py` — CLI 入口
- [x] `src/schema_adapter.py` — 薄适配层
- [x] `src/platform_client.py` — 新增 `from_schema()` 方法
- [x] `config/test_config.yaml` — 新增 `schema_driven` + `platform_schema_path`
- [x] `config/explorer_config.yaml` — 探索器独立配置
- [x] `docs/INTEGRATION_POINTS.md` — 对接点详细说明
- [x] `docs/PHASE1_IMPLEMENTATION.md` — 本文档

---

## 🔲 待完成 (优先级排序)

### P0 — 必须完成才能跑通

- [ ] **1. 安装 Playwright 浏览器**
  ```bash
  pip install playwright
  python -m playwright install chromium
  ```

- [ ] **2. 安装依赖**
  ```bash
  pip install pyyaml requests
  ```
  确认 `requirements.txt` 中已有 `playwright`, `pyyaml`, `requests`

- [ ] **3. 端到端测试 — 在已知平台上运行探索器**
  ```bash
  cd /opt/agent_eval
  python -m src.platform_probe --url http://124.174.108.70 \
      --username student001 --password 123456 \
      --output output/platform_probe
  ```
  **期望输出**: 
  - `output/platform_probe/platform_schema.yaml` 生成成功
  - API端点 > 5个
  - Step页面 > 10个

- [ ] **4. 验证 SchemaAdapter 可正确读取 schema**
  ```python
  from src.schema_adapter import SchemaAdapter
  a = SchemaAdapter("output/platform_probe/platform_schema.yaml")
  print(a.get_phases())       # 应该返回 Phase 字典
  print(a.get_endpoints_by_category("agent"))  # 应该至少有1个
  ```

- [ ] **5. 测试 PlatformClient.from_schema()**
  ```python
  from src.platform_client import PlatformClient
  client = PlatformClient.from_schema("output/platform_probe/platform_schema.yaml")
  client.login()
  result = client.chat(lesson_id=4, message="你好")
  print(result.answer[:200])  # 应该返回有效的 Agent 回答
  ```

### P1 — 完善探索器

- [ ] **6. BFS 导航改进** — 当前BFS只收集 `<a href>` 链接，需增强:
  - 点击侧边栏菜单项 (常见于 Ant Design `ant-menu-item`)
  - 点击 Tab 切换 (`.ant-tabs-tab`)
  - 点击下拉菜单 (`.ant-dropdown-trigger`)
  - 参考: `cli/explore_agent.py` 中的 selector 模式

- [ ] **7. L2 教学结构推断增强** — 当前只做 URL 模式+标题匹配:
  - 添加 DOM 层次分析: 检测侧边栏 `<ul><li>` 嵌套层次
  - 添加进度条检测: 找到 `.progress`, `.ant-progress` 对应到 Step
  - LLM 辅助: 将侧边栏 DOM 片段发给 LLM，要求输出 Phase→Lesson→Step 映射

- [ ] **8. 处理 SPA 路由** — 当前BFS假设页面跳转是完整URL变化:
  - 检测 `history.pushState` / `hashchange`
  - 对于 React Router / Vue Router, 尝试点击导航项后等待 DOM 变化而非 URL 变化

### P2 — 集成到现有测评

- [ ] **9. TestRunner 适配** — 修改 `src/test_runner.py` (~10行):
  ```python
  # 在 _init_client() 方法中添加:
  if self.config.get("schema_driven"):
      schema_path = self.config.get("platform_schema_path", "")
      if not schema_path:
          schema_path = "output/platform_probe/platform_schema.yaml"
      if Path(schema_path).exists():
          return PlatformClient.from_schema(schema_path)
  return PlatformClient()  # fallback
  ```

- [ ] **10. BrowserEvaluator 适配** — 修改 `src/browser_evaluator.py` (~15行):
  ```python
  # 在 __init__() 中添加:
  if schema_path and Path(schema_path).exists():
      from src.schema_adapter import SchemaAdapter
      adapter = SchemaAdapter(schema_path)
      self.phases = adapter.get_phases()
  else:
      self.phases = PHASES  # 保留硬编码
  ```

- [ ] **11. PersonaTester 适配** — 修改 `src/persona_tester.py`:
  - 从 schema 读取课时列表 (替代硬编码的 lesson topics)
  - 从 schema 读取 Agent 端点 (替代硬编码的 `/phase3-api/agent/chat`)

- [ ] **12. schema 驱动测评端到端测试**:
  ```bash
  # 1. 先探索
  python -m src.platform_probe --url http://124.174.108.70 -u student001 -p 123456
  
  # 2. 修改 test_config.yaml: schema_driven: true
  
  # 3. 跑冒烟测评
  python -m src.persona_tester --mode smoke
  
  # 4. 对比: schema模式分数 vs 硬编码模式分数, 偏差应<0.1
  ```

### P3 — LLM Prompt 模板 (Phase 2 准备)

- [ ] **13. 编写 Prompt 模板文件**:
  - `src/platform_probe/prompts/structure_inference.txt` — 教学层次推断
  - `src/platform_probe/prompts/step_classification.txt` — Step类型分类
  - `src/platform_probe/prompts/api_enumeration.txt` — A2A风格LLM端点枚举

- [ ] **14. 实现 LLMEnumerator.enumerate()** (当前是空接口):
  - 筛选 gray zone 端点 (conf 0.50-0.70)
  - 调用 LLM (DeepSeek/OpenAI API)
  - 对推断端点发起 OPTIONS/GET 试探
  - 返回验证通过的隐藏端点

---

## 🔧 调试技巧

```bash
# 显示浏览器窗口 (调试用)
python -m src.platform_probe --url http://124.174.108.70 --headed

# 限制探索范围 (快速测试)
python -m src.platform_probe --url http://124.174.108.70 --max-depth 1 --max-pages 5

# 静默模式 (CI使用)
python -m src.platform_probe --url http://124.174.108.70 -q

# 查看中间产物
cat output/platform_probe/capture.json | python -m json.tool | head -50
cat output/platform_probe/platform_schema.yaml | head -80
```

---

## 📊 验证标准

| 检查项 | 通过标准 |
|--------|---------|
| Schema 生成 | `platform_schema.yaml` 文件存在且格式正确 |
| API 发现 | 在已知平台上发现 ≥8 个 API 端点 |
| Step 发现 | 在已知平台上发现 ≥20 个 Step 页面 |
| 认证检测 | `auth.type` 正确识别 (已知平台为 "form") |
| SchemaAdapter | `get_phases()` 返回非空字典 |
| PlatformClient.from_schema() | `login()` + `chat()` 成功返回有效回答 |
| 向后兼容 | `schema_driven: false` 时行为与 v3.6 完全一致 |
| 评分一致性 | schema模式 vs 硬编码模式, 评分偏差 <0.1 |
