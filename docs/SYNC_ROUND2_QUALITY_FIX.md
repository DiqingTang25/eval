# 🔧 Round 2 — 探索质量修复方案

> **生成时间**: 2026-08-05 07:30 UTC  
> **背景**: 探索器已能跑通 (22 Phases/4 APIs/67s)，但质量不达标 — 0 Lessons/0 Steps/API不全/分类错误  
> **目标**: 通用教学平台的完整Schema — Phase→Lesson→Step全层次 + 完整API清单 + Agent端点识别  
> **原则**: 先方案后执行，两个AI并行，互不冲突

---

## 一、当前Schema问题诊断 (6个问题)

### 问题1: 0 Lessons / 0 Steps

**现象**: 22个Phase全部lesson_count=0，lessons/steps数组为空

**根因**: `l2_structure.py` 的 `StructureAPIParser` 只从 `careers` API 提取了 Phase (competency) 数据。真正的课程层次数据在 `graph-source` API 中，但该API的 `response_sample` 未捕获。

**API响应格式分析**:
```
careers API → {categories: [...], competencies: [...]}     → Phase级 (✅已提取)
graph-source API → {courses: [{modules: [{steps: [...]}]}]} → Lesson/Step级 (❌未捕获)
```

**修复**: 
- A侧: 确保 `_capture_api_data` 捕获 graph-source 的完整响应体
- B侧: `StructureAPIParser` 需要合并 careers(Phase名) + graph-source(Lesson/Step层次)

---

### 问题2: 仅4个API端点

**现象**: 只发现 graph-source, activity-events, digital-teacher/context, careers

**缺失**: 
- `auth/login`, `auth/me` — 认证API
- `digital-teacher/chat` — AI对话核心API  
- Phase/Lesson/Step 级别的CRUD API
- WebSocket端点

**根因**:
1. BFS深度被限制为2层/10页 — 很多页面未探索
2. `TrafficInterceptor` 过滤掉了 `resource_type=document` 和 `script` 的请求
3. 没有在页面交互中触发更多API (点击卡片、进入课程)

**修复**:
- A侧: BFS深度恢复为3层/50页（移除限制）
- A侧: 在BFS后增加交互探索（点击phase卡片→等待API请求）
- B侧: 从 graph-source 响应体中提取更多端点URL

---

### 问题3: api_prefixes 为空

**现象**: `api_prefixes: []`

**根因**: `l3_classify.py` 前缀提取逻辑假设API前缀在URL前2-3段。对于 `/personalized-secure-api/v1/...`，由于 `personalized-secure-api` 包含数字，被跳过。

**修复**: B侧 — 改进前缀提取正则，支持 `/*-api/v1/` 格式

---

### 问题4: SPA检测为false

**现象**: `spa: false` (实际是Next.js SPA)

**根因**: `_detect_spa()` 检查页面URL是否以 `.html/.htm/.php` 结尾。Next.js页面URL没有扩展名，但BFS访问的页面数太少，统计偏差。

**修复**: B侧 — 加入框架hint辅助判断（Next.js/React → 一定是SPA）

---

### 问题5: Auth类型误判为oauth

**现象**: `auth.type: oauth`，实际是标准表单登录

**根因**: `l0_auth.py AuthDetector.detect()` 扫描页面HTML中是否包含 "oauth" 等关键词。平台页面可能包含SSO相关文本。

**修复**: A侧 — 表单检测优先级应高于OAuth关键词匹配。当同时检测到表单字段和OAuth关键词时，以表单为准。

---

### 问题6: Agent端点未识别

**现象**: `agent.chat_endpoint: ''`, `agent.triggers: []`

**根因**:
1. `digital-teacher/context` 未匹配agent分类关键词（缺少 `/chat`, `/agent` 等）
2. `digital-teacher/chat` (真正的对话API) 未被捕获
3. Agent交互元素（"帮帮我"按钮）未被触发，对话API未暴露

**修复**:
- B侧: 添加 "digital-teacher" 到agent分类模式
- A侧: L1增加对"帮帮我"按钮的点击交互
- B侧: `_infer_agent_interaction` 需要更智能的端点匹配

---

## 二、分工方案

### AI Agent A — 数据采集层 (4个任务)

| # | 优先级 | 文件 | 任务 | 问题 |
|---|--------|------|------|------|
| A1 | 🔴 | `l1_capture.py` | 恢复BFS深度(3层/50页) + 增加交互探索 | #2 |
| A2 | 🔴 | `l1_capture.py` + `explorer.py` | 确保graph-source响应体被完整捕获 | #1 |
| A3 | 🟡 | `l0_auth.py` | 修复auth类型检测优先级(表单>OAuth) | #5 |
| A4 | 🟡 | `l1_capture.py` | 在BFS后点击phase卡片→触发更多API | #2 |

### AI Agent B (我) — 智能分析层 (6个任务)

| # | 优先级 | 文件 | 任务 | 问题 |
|---|--------|------|------|------|
| B1 | 🔴 | `l2_structure.py` | 合并careers+graph-source数据 → 提取Lesson/Step | #1 |
| B2 | 🔴 | `l3_classify.py` | 添加"digital-teacher"到agent分类 | #6 |
| B3 | 🔴 | `l3_classify.py` | 修复api_prefix提取 | #3 |
| B4 | 🟡 | `l4_schema.py` | 修复SPA检测(利用framework hint) | #4 |
| B5 | 🟡 | `l4_schema.py` | 改进agent交互推断(从digital-teacher API推断) | #6 |
| B6 | 🟢 | `explorer.py` | 改进L0 auth_confidence传递 | #5 |

---

## 三、互不冲突保证

```
Agent A 改:                          Agent B 改:
├── l0_auth.py (A3)                  ├── l2_structure.py (B1)
├── l1_capture.py (A1, A2, A4)       ├── l3_classify.py (B2, B3)
├── explorer.py (A2 — 仅capture部分)  ├── l4_schema.py (B4, B5)
└── models.py (如需要)               └── explorer.py (B6 — 仅L4调用部分)
```

**共享文件约定**:
- `explorer.py`: A改 `_capture_api_data` (L1.6段), B改 `run_l4_schema` 调用 (L4段) — 不同行，不冲突
- `models.py`: 如需新增字段，A先改，B后读

---

## 四、验收标准

探索 `http://124.174.108.70/personalized-secure` 后，schema应满足：

```
✅ Phases: ≥20 (当前已是22)
✅ Lessons: ≥50 (当前0 — 需≥50)
✅ Steps: ≥100 (当前0 — 需≥100)  
✅ APIs: ≥8 (当前4 — 需含auth/login, digital-teacher/chat等)
✅ Agent端点: 至少1个 (chat_endpoint非空)
✅ Auth类型: form (不是oauth)
✅ SPA: true (Next.js)
✅ api_prefixes: ["/personalized-secure-api/v1"]
✅ 整体置信度: ≥0.75
```
