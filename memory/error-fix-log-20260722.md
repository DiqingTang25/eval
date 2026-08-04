# Error Fix Log — 2026-07-22 (Session 2)

## 问题概述

1. **Agent 选择**: 前端只显示"HiAgent API测试"一个选项，实际有4个HiAgent Phase Agent需要分别测试
2. **监控黑箱**: 启动测评后平台监控页面无任何显示，无法判断测试是否真的启动、进展到哪一步、有无报错

## 根因分析

### 问题1: Agent选择
- 前端 `index.html` 硬编码了 `<select>` 选项，只有 `platform` 和 `web_test`
- 后端 `GET /api/agents` 返回6个Agent但从未被前端调用
- `web_test` 未在 agent_registry 中注册
- "HiAgent API测试"实际发送的是 `agent_id="platform"` (→PlatformAgent)，不是HiAgent

### 问题2: 监控黑箱
- WebSocket路径硬编码为 `/test/ws`，直连 `:8000` 时路径错误导致静默失败
- 前端只处理6种事件类型，TestRunner实际发出15+种事件
- 错误只传 `str(e)` 不传完整traceback
- 无WS连接状态指示器、无计时器、无步骤追踪
- 错误日志不持久化，刷新即丢失

## 修改清单（全部增量，未删任何已有代码）

### 后端 (4 files)

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 1 | `src/agents/agent_registry.py` | +8行 | 新增 `web_test` agent 注册 (WebTestAgent) |
| 2 | `src/test_runner.py` | ~+8行 | 错误事件新增 `traceback` 和 `stage` 字段 |
| 3 | `backend/services/test_service.py` | +20行 | ①错误广播含traceback ②事件日志缓冲区 `_event_log_buffer` (2000条/session) ③`get_logs()` 静态方法 |
| 4 | `backend/api/tests.py` | +5行 | 新增 `GET /api/tests/sessions/{session_id}/logs` 端点 |

### 前端 (3 files)

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 5 | `frontend/index.html` | ~200行 | ①API/WS路径自动检测 ②动态Agent列表 ③实时状态面板(WS/计时/步骤/错误/进度) ④15+事件完整处理 ⑤错误堆栈展开 |
| 6 | `frontend/js/pages/dashboard.js` | ~150行 | 同上全部功能(ES模块版) |
| 7 | `frontend/js/pages/test_runner.js` | ~150行 | 同上全部功能(测试运行页) |

### 前端详细改动

#### index.html
- **API路径**: `const API = '/test'` → 自动检测 `/test` 前缀
- **WS路径**: `ws://host/test/ws` → 自动检测前缀
- **Agent下拉**: 硬编码2选项 → 动态调用 `GET /api/agents` (默认选中 hi_phase5)
- **状态面板**: 新增 `#evalStatusBar` 含5项指标
- **事件处理**: `handleEvalEvent()` 从6种事件扩展到18种
  - 🆕 agent_start, agent_ready, prologue, send
  - 🆕 generating_followup, followup, followup_end, conversation_end
  - 🆕 turns_done, boundary_start, boundary_done, scoring
  - 🆕 scenario_done, cancelled
  - ✅ test_start, scenario_start, response, score_done, done, error (增强)
- **错误展示**: 可展开的 `<details>` 完整traceback
- **计时器**: `_startTimer()`/`_stopTimer()` 每秒更新已用时间

#### dashboard.js / test_runner.js
- 新增 `_loadAgentOptions()` — 从API动态加载
- 新增 `_updateWSStatus()`, `_startTimer()`, `_stopTimer()`, `_updateStep()`, `_updateProgress()`, `_incErrors()`, `_addLog()`
- `handleEvalEvent()`/`handleEvent()` 扩展为18种事件完整处理

## 新增API

### `GET /api/tests/sessions/{session_id}/logs?last_n=500`
返回指定会话的事件日志（历史回放），可用于页面刷新后恢复监控状态。

Response:
```json
{
  "session_id": "session_20260722_...",
  "total_events": 42,
  "returned": 42,
  "events": [
    {"ts": "2026-07-22T10:00:00Z", "event": "test_start", "data": {...}},
    ...
  ]
}
```

## 验证方法

1. 打开 http://124.174.108.70:8000
2. 检查Agent下拉框应有7个选项（Phase1-5 + 平台 + WebTest + Mock）
3. 选择 "Phase 5 — 具身智能控制"，点击"开始测评"
4. 观察状态面板：WS指示器变绿、计时器启动、当前步骤实时更新
5. 观察事件日志：每一步（连接→发送→回复→边界→评分→完成）都可见
6. 如有错误，点击"📋 完整错误堆栈"可展开查看完整traceback

## 注意事项

- 未修改 `frontend/` 以外的任何前端代码（dashboard/、cli/、scripts/ 零改动）
- 未删除任何已有功能，全部为增量添加
- API路径和WS路径现在自动适配 `/test/` 前缀和直接访问两种部署方式
