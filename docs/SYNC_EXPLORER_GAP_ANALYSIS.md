# 🔍 Platform Explorer 差距分析 & 同步文档

> **生成时间**: 2026-08-05  
> **目的**: 供其他终端AI接手时快速了解当前探索器状态、与目标愿景的差距、以及所有待做工作  
> **目标愿景**: 黑盒版侦察器架构 2.0 — 面向通用网站（百度百科等）的全自动逆向工程与测绘系统  
> **参考**: 用户提供的6大SOTA方案深度分析文档

---

## 一、项目总览

### 目录结构
```
agent_eval/
├── src/platform_probe/          # 🔥 核心侦察器
│   ├── models.py                # 全部数据模型 (L0~L4 dataclass)
│   ├── confidence.py            # 置信度计算 (6信号API分类 + Step分类)
│   ├── l0_auth.py               # L0: 认证与会话
│   ├── l1_capture.py            # L1: 流量捕获 + 页面遍历
│   ├── l2_structure.py          # L2: 教学结构推断
│   ├── l3_classify.py           # L3: API分类 + Step分类 + LLM枚举(占位)
│   ├── l4_schema.py             # L4: Schema生成 + 脱敏 + 验证
│   ├── explorer.py              # 五层流水线主协调器
│   ├── __main__.py              # CLI入口
│   └── __init__.py
├── backend/
│   ├── api/explorer.py          # REST API (run/status/cancel/sessions/schema)
│   ├── api/__init__.py          # 路由注册
│   ├── models/exploration_session.py  # ORM模型
│   └── services/explorer_service.py   # 后台线程 + DB持久化
├── frontend/
│   ├── index.html               # Explorer页面 + 侧边栏
│   ├── js/app.js                # 完整JS (~4000行, 零ES模块, 内置i18n)
│   └── locales/{zh,en}.json     # 双语翻译
├── docs/
│   ├── PHASE1_IMPLEMENTATION.md  # Phase 1实现清单
│   └── SYNC_FRONTEND_DESIGN_REVIEW.md
└── tests/
    ├── test_capture_jwt.py
    ├── test_fetch_eval.py
    ├── test_jwt_extract.py
    └── test_route_fetch.py
```

### 已验证成功的功能
- ✅ React Fiber认证突破 (Next.js自定义认证)
- ✅ 5个API端点发现 (graph-source, careers, digital-teacher, auth/me, events)
- ✅ 22个Phase发现 (来自careers API的competency数据)
- ✅ 端到端流程 (前端UI → 后端API → 探索器 → Schema生成 → 结果展示)
- ✅ 云端部署运行 (http://124.174.108.70/test/)

---

## 二、当前五层架构 vs 目标黑盒架构 — 逐层对比

### L0: 认证与会话

| 能力 | 当前状态 | 目标状态 | 差距 |
|------|---------|---------|------|
| 表单自动检测 | ✅ 启发式DOM检测 | 🤖 balage-core ML分类(F1=0.93) | 🔴 未集成balage-core |
| 登录策略 | ✅ 4路径: Fiber注入→表单提交→按钮点击→预认证 | ✅ 已有 | ✅ 满足 |
| OAuth/SSO检测 | ⚠️ 仅检测HTML关键词 | 🤖 完整OAuth流程识别 | 🟡 基础可用 |
| 验证码处理 | ❌ 未实现 | 🤖 视觉识别+人工fallback | 🔴 未实现 |
| MFA处理 | ❌ 未实现 | 🤖 Periscope MCP工具链 | 🔴 未实现 |
| WAF/反爬对抗 | ❌ 完全未实现 | 🔴 TLS指纹伪装+Canvas指纹 | 🔴 核心缺口 |
| Session持久化 | ✅ Playwright storage_state | ✅ 已有 | ✅ 满足 |
| 预认证模式 | ✅ 加载已保存session | ✅ 已有 | ✅ 满足 |

### L1: 流量捕获与JS逆向 (🌟 这是整个系统最核心的层)

| 能力 | 当前状态 | 目标状态 | 差距 |
|------|---------|---------|------|
| HTTP流量拦截 | ✅ `page.on("response")` | ✅ 已有 | ✅ 满足 |
| 响应体捕获 | ❌ **已知BUG** — JWT在React内存, 外部requests无法访问 | 🔴 `page.route()` + `route.fetch()` | 🔴 P0待修 |
| HAR导出 | ⚠️ 简化版JSON (非标准HAR) | ✅ 标准HAR格式 | 🟡 格式升级 |
| BFS页面遍历 | ✅ 传统链接 + 卡片点击 | ✅ 已有 | ✅ 满足 |
| SPA交互探索 | ⚠️ 仅点击career cards | 🔴 完整SPA交互 (所有导航元素) | 🟡 可扩展 |
| WebSocket拦截 | ❌ 未实现 | 🔴 WebSocket消息捕获 | 🔴 核心缺口 |
| **JS AST静态分析** | ❌ **完全未实现** | 🔴 **Babel/TypeScript解析app.js** | 🔴 **最大缺口** |
| **SourceMap还原** | ❌ 完全未实现 | 🔴 自动下载.map还原源码 | 🔴 核心缺口 |
| **JS字符串提取** | ❌ 完全未实现 | 🔴 扫描所有字符串字面量找API路径 | 🔴 核心缺口 |
| 页面快照 | ✅ 截图+DOM摘要+框架检测 | ✅ 已有 | ✅ 满足 |
| 交互元素提取 | ✅ 按钮/链接/输入框清单 | ⚠️ 需KaBOOM语义增强 | 🟡 可改进 |

### L2: 结构与语义分析

| 能力 | 当前状态 | 目标状态 | 差距 |
|------|---------|---------|------|
| API驱动结构解析 | ✅ 从graph-source/careers等API提取 | ✅ 已有 | ✅ 满足 |
| DOM结构推断 | ✅ 标题启发式 (Phase 1, Lesson 2...) | ⚠️ 仅fallback | 🟡 基础可用 |
| 框架检测 | ✅ React/Vue/Angular/Next/Antd | ✅ 已有 | ✅ 满足 |
| **KaBOOM语义选择器** | ❌ 完全未实现 | 🔴 语义定位"提交按钮"/"模态框" | 🔴 需要引入 |
| **Shadow DOM穿透** | ❌ 完全未实现 | 🔴 Web Components边界穿透 | 🔴 需要引入 |
| **VLM截图理解** | ❌ 完全未实现 | 🔴 多模态大模型页面分块 | 🔴 核心缺口 |
| **交互热力图** | ❌ 完全未实现 | 🔴 JS注入高亮可点击元素 | 🔴 需要实现 |
| **Explorbot Research** | ⚠️ 仅元素列表 | 🔴 UI分块+元素索引+状态记忆 | 🔴 差距大 |

### L3: API分类与推断

| 能力 | 当前状态 | 目标状态 | 差距 |
|------|---------|---------|------|
| 6信号API分类 | ✅ Vespasian风格 (content_type+path+method+response+static+teaching) | ✅ 已有 | ✅ 满足 |
| API细粒度分类 | ✅ 8类 (content/agent/quiz/progress/auth/profile/search/event) | ✅ 已有 | ✅ 满足 |
| Step类型分类 | ✅ 6类 (video/coding/quiz/chat/upload/reading) | ✅ 已有 | ✅ 满足 |
| 参数推断 | ✅ URL参数化+Query+Body schema | ✅ 已有 | ✅ 满足 |
| 响应Schema推断 | ✅ JSON→JSON Schema | ✅ 已有 | ✅ 满足 |
| **LLM端点枚举** | ❌ **仅有占位类, 返回空列表** | 🔴 A2A论文方法: JS分析→LLM脑补→GET/OPTIONS验证 | 🔴 **核心缺口** |
| **灰色地带处理** | ❌ is_gray_zone()函数存在但未调用LLM | 🔴 conf 0.50-0.70 → LLM辅助 | 🔴 逻辑断链 |
| **JS Bundle分析** | ❌ 完全未实现 | 🔴 下载+解析JS→提取路由→LLM枚举 | 🔴 核心缺口 |
| **参数Fuzzing** | ❌ 完全未实现 | 🔴 篡改参数→重放→检测越权 | 🔴 未开始 |
| GraphQL发现 | ❌ 未实现 | 🟡 GraphQL introspection | 🟡 可选 |

### L4: Schema生成与验证

| 能力 | 当前状态 | 目标状态 | 差距 |
|------|---------|---------|------|
| Schema生成 | ✅ platform_schema.yaml (YAML) | ✅ 已有 | ✅ 满足 |
| 凭证脱敏 | ✅ Redactor (递归+正则) | ✅ 已有 | ✅ 满足 |
| Schema验证 | ⚠️ 仅基础字段检查 | 🔴 API重放验证+漂移检测 | 🟡 需增强 |
| 探索报告 | ✅ Markdown报告 | ✅ 已有 | ✅ 满足 |
| **OpenAPI 3.0生成** | ❌ 未实现 | 🟡 Vespasian风格OpenAPI生成 | 🟡 可选 |
| **MCP Server生成** | ❌ 完全未实现 | 🔴 Schema→MCP Tools自动生成 | 🔴 架构缺口 |
| **知识图谱** | ❌ 完全未实现 | 🔴 实体关系+业务地图 | 🔴 未开始 |

---

## 三、6大SOTA方案对标 — 逐项分析

### 1. Vespasian (L1捕获 + L3规范生成)
**对标度: 35%**

| Vespasian功能 | 当前状态 |
|--------------|---------|
| Headless Browser拦截XHR/Fetch | ✅ 已实现 |
| HAR流量日志 | ⚠️ 简化版JSON, 非标准HAR |
| OpenAPI 3.0生成 | ❌ 未实现 (只生成platform_schema.yaml) |
| GraphQL SDL生成 | ❌ 未实现 |
| WSDL生成 | ❌ 未实现 |
| AST+正则Classifier | ❌ 未实现 (用的是纯规则, 无AST解析) |
| 两阶段分离架构 | ⚠️ 有Capture→Generate概念, 但响应体捕获broken |

### 2. Explorbot (L2结构分析 + 探索交互)
**对标度: 15%**

| Explorbot功能 | 当前状态 |
|--------------|---------|
| Research (UI切块+索引元素) | ⚠️ 仅有元素列表, 无分块 |
| Plan (基于理解起草场景) | ❌ 未实现 |
| Execute | ❌ 未实现 |
| Verify | ❌ 未实现 |
| Keep (记住页面状态) | ❌ 未实现 |
| 五步工作流 | ❌ 完全未实现 |

### 3. balage-core (L0认证与表单检测)
**对标度: 10%**

| balage-core功能 | 当前状态 |
|----------------|---------|
| ML表单识别 (F1=0.93) | ❌ 用的是启发式规则, 无ML |
| 登录表单vs搜索框vs结账 | ❌ 未区分 |
| OAuth重定向页识别 | ⚠️ 基础HTML关键词匹配 |
| Raw HTML解析 | ❌ 未集成 |
| URL分析 | ❌ 未集成 |

### 4. KaBOOM! (L2深度DOM与Shadow DOM)
**对标度: 0%**

| KaBOOM!功能 | 当前状态 |
|------------|---------|
| 语义选择器 | ❌ 完全未实现 |
| Shadow DOM穿透 | ❌ 完全未实现 |
| 视觉+语义定位 | ❌ 完全未实现 |
| Web Components支持 | ❌ 完全未实现 |

### 5. A2A隐藏API识别论文 (L3语义推断)
**对标度: 5%**

| A2A论文方法 | 当前状态 |
|------------|---------|
| LLM分析JS源码变量名/路由 | ❌ 未实现 |
| 端点"脑补" (/users→/admins) | ❌ 未实现 |
| A2A协议能力发现 | ❌ 未实现 |
| GET/OPTIONS验证 | ❌ 未实现 |
| 91.9%发现率方法 | ❌ 仅占位类 |
| 灰色地带LLM fallback | ❌ 函数存在但未接LLM |

### 6. Periscope MCP (L0/L1复杂认证与浏览器武装)
**对标度: 5%**

| Periscope MCP功能 | 当前状态 |
|------------------|---------|
| 60+ Playwright高级工具 | ❌ 未集成 |
| 2FA绕过 | ❌ 未实现 |
| SSO登录流 | ❌ 未实现 |
| 验证码识别等待 | ❌ 未实现 |
| Session状态持久化 | ✅ storage_state已实现 |
| MCP协议 | ❌ 未实现 |

---

## 四、关键架构决策回顾 (来自用户文档)

### 决策1: L3的LLM辅助推断
**用户结论**: 必须用，但做成本控制+安全门
**当前状态**: 
- `LLMEnumerator` 类存在但返回空列表
- `is_gray_zone()` 函数已实现 (conf 0.50-0.70判定)
- `llm_fallback` 开关未实现
- 廉价模型调用未实现 (计划用DeepSeek/Haiku)
**需要实现**:
```python
# 在 l3_classify.py LLMEnumerator.enumerate() 中:
# 1. 筛选 gray_zone 端点
# 2. 构建Prompt (已知端点 + JS路由片段)
# 3. 调用LLM推断隐藏端点
# 4. GET/OPTIONS试探验证
# 5. 返回验证通过的隐藏端点
```

### 决策2: platform_schema.yaml进Git
**用户结论**: 结构进Git，凭证不进
**当前状态**: ✅ Redactor已实现 (递归脱敏 + YAML正则脱敏)
**未完成**: 运行时从.env.local注入凭证的功能 (脱敏是单向的)

### 决策3: 垂直切片策略
**用户结论**: L0→L1→L3先打通 (MVP), 再横向扩展L2和L4
**当前状态**: 
- ✅ L0→L1→L3→L4 已打通 (MVP完成)
- ✅ L2已加入但效果有限 (仅Phase级别)
- 🔄 下一步应该是深化L1+L3, 而非扩展L2+L4

---

## 五、优先级路线图

### 🔴 P0 — 阻塞性 (必须先修)

1. **响应体捕获修复** (`l1_capture.py`)
   - 从 `page.on("response")` 迁移到 `page.route()` + `route.fetch()`
   - 当前JWT存储在React内存中，外部requests无法访问
   - 影响: L2结构解析、L3 API分类、L4 Schema生成的准确性

2. **JS Bundle下载与解析** (新模块, 例如 `l1_js_analyzer.py`)
   - 下载所有 `<script src="...">` 中的JS文件
   - 尝试下载 `.map` 文件进行SourceMap还原
   - 使用正则+AST提取所有字符串字面量中的URL路径
   - 这是A2A论文方法的前提条件

### 🟡 P1 — 核心能力 (MVP深化)

3. **LLM端点枚举实现** (`l3_classify.py LLMEnumerator`)
   - 接入DeepSeek/Haiku API
   - 实现: 灰色地带筛选 → Prompt构建 → LLM调用 → 验证
   - Prompt策略参考A2A论文

4. **L1 WebSocket拦截** (`l1_capture.py`)
   - 监听WS连接和消息
   - 很多AI对话接口走WS而非HTTP

5. **参数Fuzzing基础版** (新模块 `l3_fuzzer.py`)
   - URL参数篡改 (id=123→124)
   - 重放并比较响应
   - 检测潜在IDOR

### 🟢 P2 — 扩展能力

6. **balage-core集成** (`l0_auth.py`)
   - 替换启发式表单检测为ML分类
   - 区分: 登录表单 / 搜索框 / 结账流程 / 注册表单

7. **VLM截图理解** (新模块 `l2_vision.py`)
   - 页面区块截图 → GPT-4o/Qwen-VL识别
   - "这是百科摘要区" / "这是侧边栏目录" / "这是广告"

8. **KaBOOM语义选择器** (`l2_structure.py` 或新模块)
   - Shadow DOM穿透
   - 语义定位 ("提交按钮" 而非 `#div-123 > button`)

9. **OpenAPI 3.0生成** (`l4_schema.py`)
   - 在现有platform_schema.yaml基础上
   - 额外生成标准OpenAPI 3.0格式

### 🔵 P3 — 愿景功能

10. **MCP Server自动生成** (新模块)
    - 读取platform_schema.yaml
    - 自动生成MCP Tools (如search_wiki, get_edit_history)
    - 让Explorbot/Multi-Agent可以接入

11. **WAF/反爬对抗** (`l0_auth.py`)
    - TLS指纹伪装 (Playwright launch options)
    - Canvas指纹处理
    - User-Agent轮换
    - IP代理支持

12. **Periscope MCP集成**
    - 复杂认证场景 (SSO+MFA)
    - 60+ Playwright高级工具

13. **知识图谱构建** (`l4_schema.py` 扩展)
    - 实体关系提取
    - 业务流转路径
    - 竞品变更监控

---

## 六、代码架构评估

### 优点
- **清晰的五层分离**: L0~L4职责分明，每层独立模块
- **借鉴SOTA设计**: 数据模型、信号系统、流水线协调都有明确的理论来源
- **置信度系统完善**: 从单信号到整体汇总，支持不确定性传播
- **凭证安全**: Redactor双重脱敏 (递归dict + YAML正则)
- **自适应认证**: 4路径fallback (Fiber→表单→按钮→预认证)
- **前后端完整**: REST API + 后台线程 + DB持久化 + 前端UI

### 待改进
- **响应体捕获broken**: 这是整个流水线的数据源，当前不可靠
- **JS逆向完全缺失**: 这是黑盒侦察最核心的能力，当前为0
- **LLM集成仅为占位**: LLMEnumerator存在但不工作
- **L2结构解析太弱**: 只能到Phase级别，Lesson/Step靠DOM猜
- **缺少VLM视觉理解**: 纯文本方式无法处理现代SPA
- **缺少反爬对抗**: 目标网站可能有WAF

### 架构建议
```
当前:  L0 → L1 → L1.5 → L2 → L3 → L4
目标:  L0 → L1(HTTP+WS+JS AST+SourceMap) → L1.5 → L2(API+DOM+VLM) → L3(规则+LLM+Fuzz) → L4(Schema+MCP+KG)
```

---

## 七、🐛 已知Bug清单 (深度审查发现)

### 探索器相关

| # | 文件:行号 | 严重度 | 描述 |
|---|----------|--------|------|
| 1 | `models.py:88-89` | 🟡低 | **重复 `@dataclass` 装饰器** — `SessionState` 类上有两行连续的 `@dataclass`，编辑遗留，运行时不报错但应清理 |
| 2 | `l1_capture.py:375-451` | 🟡低 | **死代码** — `_explore_spa_fast()` 方法在 `return discovered` (行374) 之后有一段完全不可达的实现，其中引用了未定义的 `max_pages` 变量。如果移除 `return` 会直接 NameError |
| 3 | `l1_capture.py:578-581` | 🟠中 | **用户配置被静默截断** — `run_l1_capture()` 强制 `max_depth=min(max_depth, 2)`, `max_pages=min(max_pages, 10)`，CLI/API传入的3/50从未生效。这是SPA慢的临时方案，但没有任何warning告知用户 |
| 4 | `l4_schema.py:453` | 🟠中 | **硬编码 auth_conf=0.95** — L0真实认证置信度被丢弃，整体评分永远包含一个虚假的0.95 |

### 前后端契约不匹配 (校准系统)

| # | 位置 | 描述 |
|---|------|------|
| 5 | `app.js calSubmit` ↔ `calibration.py /score` | 前端发送 `{qa_id, scores}` 但后端期望 `{qa_id, human_scores: DimensionScore, human_overall, notes}` → 校准打分提交会 **400报错** |
| 6 | `app.js calLoad` ↔ `calibration.py /items` | 前端传 `limit=20&unscored_only=true`，但后端 **忽略这两个参数**，返回全部items |
| 7 | `app.js calStats` ↔ `calibration.py /results` | 前端读取 `cohens_kappa`/`spearman_rho`/`per_dimension[].bias`，但后端返回的结构完全不同的嵌套格式 → 统计面板永远显示 0.000 |
| 8 | `app.js calGenBtn` ↔ `calibration.py /generate` | 前端POST `{count:20}`，后端期望 `{size, type}` → count被忽略，永远生成50条 |

### 其他

| # | 位置 | 描述 |
|---|------|------|
| 9 | `backend/api/tests.py:150,165` | **可变默认参数** — `trigger_test(body: TestRunRequest = TestRunRequest())` 和 `trigger_browser_eval` 使用可变默认值，同一实例跨请求共享 |
| 10 | `frontend/js/pages/*.js` | **孤儿文件** — 10个页面JS文件存在但 `index.html` 从未加载它们，所有逻辑在 `app.js` 单文件中 |
| 11 | `frontend/js/i18n.js` + `app.js` | **两套i18n系统并存** — `i18n.js` (1467行, 591-key) 和 `app.js` 内置 `_dict` (~120-key)，通过 `setLang()` 合并逻辑协调，有已知冲突历史 |
| 12 | `backend/api/settings.py` | **安全**: `GET /platform-defaults` 未认证返回 admin/admin123 和平台密码; `PUT /llm-keys` 未认证写入 `.env` |
| 13 | `src/platform_probe/prompts/` | **空目录** — `l3_classify.py` 文档引用的 `prompts/api_enumeration.txt` 从未创建 |

---

## 八、文件修改热力图

| 文件 | 需要改动程度 | 说明 |
|------|------------|------|
| `l1_capture.py` | 🔥🔥🔥🔥🔥 | P0响应体修复 + WS拦截 + JS下载 |
| `l3_classify.py` | 🔥🔥🔥🔥🔥 | LLM枚举实现 + Fuzzing |
| `l0_auth.py` | 🔥🔥🔥 | balage-core集成 + WAF对抗 |
| `l2_structure.py` | 🔥🔥🔥 | KaBOOM + VLM + 深层结构 |
| `l4_schema.py` | 🔥🔥 | OpenAPI生成 + MCP生成 |
| `models.py` | 🔥🔥 | 新增WS/JS/Fuzz相关dataclass |
| `explorer.py` | 🔥🔥 | 流水线加入新步骤 |
| `confidence.py` | 🔥 | LLM推断置信度标记 |
| **新文件** | — | `l1_js_analyzer.py`, `l3_fuzzer.py`, `l2_vision.py` |

---

## 八、快速上手命令

```bash
# 云端SSH
ssh root@124.174.108.70
cd /opt/agent_eval

# 直接运行探索器
./venv/bin/python3 -c "
from src.platform_probe.explorer import PlatformExplorer
from pathlib import Path
e = PlatformExplorer(headless=True, output_dir=Path('/tmp/test'), verbose=True)
e.explore('http://124.174.108.70/personalized-secure', '111', '123456')
"

# 查看最新探索结果
curl -s http://localhost:8000/api/explorer/sessions?page_size=1 | python3 -m json.tool

# 查看生成的schema
cat /opt/agent_eval/output/platform_probe/explore_*/platform_schema.yaml | head -50

# 重启服务
systemctl restart agent-eval

# 健康检查
curl http://localhost:8000/api/explorer/health

# 本地开发 — CLI模式
cd /home/jennifer07/agent_eval
python -m src.platform_probe --url https://some-platform.com --username test --password test
```

---

## 九、给接手AI的上下文

1. **用户不是传统QA**: 面对的是通用网站 (百度百科等)，无法接触后端数据库，是纯黑盒外部测试者
2. **目标不是保证代码不出错**: 而是挖掘业务逻辑漏洞、监控竞品变更、发现边缘体验问题
3. **当前MVP已跑通**: L0→L1→L3→L4 端到端可用，能生成platform_schema.yaml
4. **最大瓶颈在L1**: 响应体捕获broken + JS逆向完全缺失 = 数据源不可靠
5. **第二大瓶颈在L3**: LLM枚举未实现 = 隐藏API发现率为0
6. **L2/L4是锦上添花**: 先把L1+L3做扎实，再扩展其他层
7. **前端是零ES模块架构**: 所有JS在app.js单文件中，内置i18n字典，无npm/webpack
8. **后端是FastAPI+MySQL**: 探索器在后台线程运行，结果持久化到DB
9. **云端地址**: http://124.174.108.70/test/ (nginx代理到FastAPI)
