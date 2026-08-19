# 交互模式设计 — 对话式探索器 + 评测器卡点干预

> 2026-08-19 实施
> 两条设计原则:
> 1. **探索器**: 以 LLM 对话交流为主, 固定填写为辅
> 2. **评测器**: 以自动化流程为主, 遇到卡点必须暴露出来并询问用户更多信息

---

## 一、探索器 — LLM 对话为主

### 交互模型

```
用户自然语言 ──→ ExplorerChatService 状态机
                    │  LLM 意图解析 (DeepSeek > GLM > Doubao, 无key降级正则)
                    ▼
           collecting (缺什么问什么) → confirm (展示计划待确认) → running (复用现有流水线)
```

| 用户说 | 系统行为 |
|--------|---------|
| 「探索 https://x.com」 | 提取 URL → 反问「需要登录吗？」 |
| 「账号 111 密码 123456」 | 补齐凭证 → 展示探索计划, 等「开始」 |
| 「开始」/「go」 | 调用现有 `ExplorerService.start_explore()` 启动 (同一单例, 与表单路径共享状态) |
| 「进度如何」 | 返回当前进度 |
| 「取消」 | 取消探索 |
| 「用上次的平台」 | 从 `platform_profile.json` 载入上次 URL+凭证 |
| 一次给全「URL + user/pass + 开始」 | 直接启动 (用户已明示开始, 免二次确认) |

### 固定表单的定位 (辅助)

- 前端 Explorer 页: 聊天面板为主界面; 原配置表单折叠进 `<details>`「探索配置（可选）」
- 表单值在开启对话时自动作为**预填默认参数** (`POST /api/explorer/chat/start`)
- 表单的「Start Exploration」按钮保留 — 直接走 `/api/explorer/run` 的老路径

### API

```
POST /api/explorer/chat/start          {chat_id?, target_url?, username?, password?, headless?, max_depth?, max_pages?}
                                       → {chat_id, reply, missing_fields, action}
POST /api/explorer/chat/message        {chat_id, message} → {reply, action, missing_fields, explore_session_id, params}
GET  /api/explorer/chat/history/{id}   → {messages, status, params}
```

- `action`: `none` | `started` | `cancelled` | `status` | `expired`
- LLM 调用走 `src/platform_probe/api_keys.py` 的 `APIKeyRegistry.get_text_llm()` (OpenAI-compatible `/chat/completions`), 失败自动降级确定性正则解析
- 会话内存态, 4 小时过期; 60 条消息上限

### 文件

| 文件 | 改动 |
|------|------|
| `backend/services/explorer_chat.py` | **新增** 状态机 + LLM/正则解析 |
| `backend/api/explorer.py` | +3 个 chat 端点 (懒加载, 注入 ExplorerService 单例) |

---

## 二、评测器 — 自动化为主 + 卡点暴露询问

### 交互模型

```
评测线程遇卡点 ──→ TestService.ask_user(session_id, question, options, timeout_s, default)
                        │  ① WS 广播 eval:need_input (前端弹窗)
                        │  ② 阻塞等待 POST /api/tests/intervention/respond
                        │  ③ 超时 → 返回 default (自动化优先, 不无限等待)
                        ▼
                   继续 / 重试 / 跳过 / 终止 (取决于用户回答)
```

**关键设计**: 超时走默认动作 = 无人值守时流程照常推进; 有人值守时获得卡点控制权。

### 卡点挂接点 (v1)

| 位置 | 卡点 | 选项 | 默认(超时) |
|------|------|------|-----------|
| `browser_evaluator.run()` 登录失败 (循环最多3次) | 凭证无效/平台变更 | 重试登录 / 提供新凭证 / 终止测评 | 终止测评 (300s) |
| `browser_evaluator.run()` Day 测评出错 | 元素缺失/页面异常 | 跳过此Day继续 / 终止测评 | 跳过此Day继续 (120s) |
| `multi_agent.orchestrator.run()` Schema 缺失 | 计划无法生成 | 终止 / 先运行探索器 / 继续(仅文本验证) | 终止 (300s) |

- 凭证解析 `BrowserEvaluator._parse_credentials()`: 支持 `user/pass`、`user:pass`、`账号xx密码yy`、`user pass`, 并剥离「提供新凭证: 」选项前缀 (仅剥离含中文的前缀, 避免误伤 `u1:pw...`)
- 注入方式: `TestService._run_browser_eval` 设置 `evaluator._ask_cb`; `_run_multi_agent` 传 `ask_user=` 给编排器
- **独立运行兼容**: 未注入回调时 `ask_user()` 直接返回 default — 原自动流程零变化

### API

```
POST /api/tests/intervention/respond   {session_id, answer} → {status: ok|timeout}
GET  /api/tests/intervention/pending   → {pending: false} | {pending: true, question, options, timeout_s, ...}
```

### 前端

- `eval:need_input` WS 事件 → 全屏弹窗: 问题 + 选项按钮 + 自由文本输入 + 倒计时提示
- 提交: `选项: 文本` (或纯文本/纯选项) → `POST /api/tests/intervention/respond`
- 10s 轮询 `intervention/pending` 兜底 (WS 断开时)

### 文件

| 文件 | 改动 |
|------|------|
| `backend/services/test_service.py` | +`ask_user` / `respond_intervention` / `pending_intervention`; 注入回调 |
| `backend/api/tests.py` | +2 个 intervention 端点 |
| `src/browser_evaluator.py` | +`ask_user` / `_parse_credentials`; 登录+Day 两处卡点 |
| `src/multi_agent/orchestrator.py` | +`ask_user` 参数; Schema 缺失卡点 |
| `frontend/index.html` | 干预弹窗 + 聊天面板 + CSS |
| `frontend/js/app.js` | 聊天逻辑 + 干预弹窗 + 轮询 + WS 分支 |
| `frontend/locales/{zh,en}.json` | +7 个 i18n 键 |

---

## 三、验证记录

- `py_compile` 全部通过 (6 个后端文件)
- 聊天状态机冒烟: 11 项 PASS (URL→凭证→计划→确认→启动→进度→取消 / 免登录 / 一步到位 / 会话过期)
- 干预机制冒烟: 6 项 PASS (应答唤醒 / pending 可见 / 超时默认 / 迟到应答拒绝)
- 凭证解析: 8 项 PASS
- `node --check app.js` 通过; locales JSON 合法; index.html 标签闭合校验通过

## 四、后续可扩展 (v2)

- 探索器: 运行中的自然语言干预 (改深度/暂停/重定向); 探索结果问答
- 评测器: 更多卡点 (Quiz 答题失败、Agent 无响应、报告生成失败); 卡点历史记录入库
- 干预审计: 每次 ask/answer 记入 `data/intervention_log.json`
