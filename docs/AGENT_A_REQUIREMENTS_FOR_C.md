# Agent A → Agent C 接口要求

> **Agent C 即将实施 Multi-Agent 架构。本文档定义 Agent A 需要 Agent C 遵守的接口契约。**

---

## 1. Agent A 域红线 (不可触碰)

| 文件/目录 | 原因 |
|-----------|------|
| `frontend/index.html` | Agent A 的 SPA shell |
| `frontend/js/app.js` | Agent A 的全部前端逻辑 |
| `frontend/locales/{en,zh}.json` | Agent A 的双语词典 |
| `src/platform_probe/l1_capture.py` | Agent A 的数据采集核心 |
| `backend/api/dashboard.py` | Agent A 的 Dashboard/Health API |
| `backend/services/dashboard_service.py` | Agent A 的 Health 探活 |

**Agent C 只读这些文件，不修改。如需新增前端 UI，告知 Agent A 来实现。**

---

## 2. 接口契约 (Agent C 必须遵守)

### 2.1 WebSocket 事件格式

所有 `multi_agent:*` 事件必须遵循以下格式：

```json
{
  "type": "multi_agent:plan_ready",
  "data": {
    "phases": [{"id": "...", "name": "...", "lesson_count": 3}],
    "strategy": "full",
    "estimated_minutes": 18
  }
}
```

**要求**:
- `type` 字段必须以 `multi_agent:` 为前缀
- `data` 必须是 dict，不能是 list 或 string
- 字段名使用 `snake_case`（与现有 WebSocket 事件一致）

### 2.2 API 端点

```
POST /api/tests/run-multi-agent
```

**Request**:
```json
{
  "strategy": "full",
  "phases": ["phase_1", "phase_2"],
  "target_url": "http://..."
}
```

**Response**:
```json
{
  "status": "started",
  "session_id": "multi_agent_20260805_...",
  "strategy": "full",
  "estimated_minutes": 18
}
```

### 2.3 报告 JSON 格式

新增 `diagnosis` 字段，格式如下：

```json
{
  "summary": {...},
  "dimensions": {...},
  "diagnosis": {
    "pass_rate": 0.85,
    "critical_failures": 2,
    "findings": [
      {
        "step": "Phase 2 Day 3 Step 2",
        "verdict": "fail",
        "text_score": 4.2,
        "visual_pass": false,
        "api_pass": true,
        "reason": "前端渲染问题 — API正常但页面空白"
      }
    ]
  }
}
```

**要求**:
- `diagnosis` 为可选字段 — 现有评测不返回此字段时，前端不应崩溃
- `findings[].step` 使用 Schema 中的 Phase/Lesson 名称，不硬编码

### 2.4 文件路径

| 数据 | 路径 | Agent C 可写 |
|------|------|-------------|
| Healing 日志 | `data/healing_log.json` | ✅ 写 |
| 视觉断言日志 | `data/visual_assertion_log.json` | ✅ 写 |
| 覆盖率报告 | `data/coverage_report.json` | ✅ 写 |
| Multi-Agent 报告 | `eval_output/multi_agent/` | ✅ 写 |
| 前端文件 | `frontend/` | ❌ 不可写 |

---

## 3. Agent A 提供给 Agent C 的接口

| 接口 | 用途 | 状态 |
|------|------|------|
| `GET /api/explorer/profile/latest` | 读 Schema (Phase/Lesson/API) | ✅ 生产 |
| `GET /api/explorer/schema` | 读 platform_schema.yaml | ✅ 生产 |
| `WebSocket /ws` | 实时事件推送 (现有 `eval:*` 事件) | ✅ 生产 |
| `GET /api/mcp/tools` | MCP 工具列表 | ✅ 已部署 |
| `POST /api/mcp/call` | MCP 工具调用 | ✅ 已部署 |
| `BrowserEvaluator` | 浏览器自动化 | ✅ 稳定 |
| `PlatformClient` | 平台 API 客户端 | ✅ 稳定 |
| `src/schema_adapter.py` | Schema → 统一数据结构 | ✅ 可用 |

---

## 4. Agent A 对 Agent C 的具体要求

### 4.1 WebSocket 事件（现在就要定义，不要以后改）

```python
# Agent C 必须发送以下事件 (通过现有的 WS 广播机制):

# 1. 计划就绪
await ws_broadcast({
    "type": "multi_agent:plan_ready",
    "data": {
        "phases": [{"id": str, "name": str, "lessons": int}],
        "strategy": str,
        "estimated_minutes": int,
        "risk_areas": [str]
    }
})

# 2. Step 开始
await ws_broadcast({
    "type": "multi_agent:step_start",
    "data": {
        "phase": str, "lesson": str, "step": str,
        "step_index": int, "total_steps": int
    }
})

# 3. 验证完成 (每个 Step)
await ws_broadcast({
    "type": "multi_agent:verify_done",
    "data": {
        "text_pass": bool, "visual_pass": bool, "api_pass": bool,
        "verdict": "pass" | "fail",
        "text_score": float  # optional
    }
})

# 4. 诊断发现
await ws_broadcast({
    "type": "multi_agent:diagnosis",
    "data": {
        "finding": str,
        "severity": "high" | "medium" | "low",
        "step": str
    }
})

# 5. 完成
await ws_broadcast({
    "type": "multi_agent:done",
    "data": {
        "report_path": str,
        "pass_rate": float,
        "total_steps": int,
        "failures": int
    }
})
```

### 4.2 Test Runner UI 预留

Agent A 会在 Test Runner 页面预留以下 UI 位置：

```
┌─ Test Runner ─────────────────────────────┐
│ [Browser Eval] [Multi-Agent]  ← 模式切换   │
│                                            │
│ Strategy: [full ▾]  Phases: [all ▾]       │
│ Estimated: 18 min                          │
│                                            │
│ ┌─ Multi-Agent 进度 ────────────────────┐  │
│ │ Planner ✓  Plan generated (5 phases)  │  │
│ │ Phase 1/5: "嵌入式硬件"               │  │
│ │   Day 3 Step 2: Verifying...          │  │
│ │   ✓ Text:4.2  ✓ Visual  ✗ API        │  │
│ │   → verdict: PASS (2/3)               │  │
│ └───────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

### 4.3 降级策略

当 Schema 或 MCP 不可用时，Multi-Agent 应优雅降级：
- Schema 缺失 → Planner 返回空计划 + warning
- MCP 不可用 → Verifier 跳过 API 通道 (只用 Text+Visual)
- Visual 不可用 → Verifier 跳过 Visual 通道 (只用 Text+API)
- 极端情况 → 退回现有的单通道 BrowserEvaluator 模式

---

*Agent A — 2026-08-05*
