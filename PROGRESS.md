# AI Agent 全自动化测评系统 — 进度总览 v3.6

> 最后更新: 2026-07-22 12:40 CST | 平台: http://124.174.108.70 | 云端: root@124.174.108.70:/opt/agent_eval/

## 🔥 2026-07-22 Phase 1 证据链地基完成 (Claude Terminal)

### 背景
结合"测试平台"定位 + 区块链审计需求 + 火山引擎技术栈，设计了**大厂级可信AI测评平台架构**。
核心逻辑：MySQL 做索引，证据 JSON 直存 MySQL，SHA-256 做指纹，后续区块链做公证。

### 决策：纯 MySQL 存储（零额外费用）
原方案需要 TOS 对象存储（按量付费），经评估后改为 **MySQL LONGTEXT 直存证据 JSON**。
SHA-256 指纹是证据链核心，存储介质不影响可信性。

### 完成清单
| # | 操作 | 文件 | 状态 |
|---|------|------|------|
| 1 | MySQL 全表诊断 | 10 张表 + 3 个 migration | ✅ 发现 5 个索引缺口，全部修复 |
| 2 | 证据哈希核心 | `src/evidence_hasher.py` (新建) | ✅ SHA-256 + store_evidence + verify |
| 3 | 异步证据队列 | `src/async_queue.py` (新建→改写) | ✅ Redis Streams + 降级同步 |
| 4 | 证据追踪模型 | `backend/models/evidence_trail.py` (新建→改写) | ✅ 15字段, 5索引, data_json LONGTEXT |
| 5 | EvalScore 扩展 | `backend/models/eval_score.py` (修改) | ✅ evidence_hash/path/merkle/chain |
| 6 | 索引修复 | `backend/models/test_session.py` (修改) | ✅ agent_id/profile/qa_pair/turn 索引 |
| 7 | DBRecorder 扩展 | `src/db_recorder.py` (修改) | ✅ _stamp_evidence 直写 MySQL |
| 8 | Migration 0004 | `backend/alembic/versions/0004` | ✅ 证据字段 + evidence_trail 表 |
| 9 | Migration 0005 | `backend/alembic/versions/0005` | ✅ 去 TOS + data_json 新增 |
| 10 | 测试 | `tests/test_phase1_evidence.py` | ✅ 12/12 PASS, 0 回归 |
| 11 | 云端部署 | rsync + alembic + systemctl | ✅ health=ok, migration 已执行 |
| 12 | 同步文档 | `docs/phase1_evidence_chain_20260722.md` | ✅ 全终端同步 |

### MySQL 变更
- eval_scores: +4字段(evidence_hash/path/merkle/chain), -2字段(tos_key/tos_url)
- evidence_trail: 新建表, 15字段含 data_json LONGTEXT
- test_sessions: +2索引(agent_id, profile)
- test_scenarios: +1索引(qa_pair_id)
- conversation_turns: +1索引(turn_index)

### 架构
```
评测完成 → DBRecorder → SHA-256 → eval_scores.evidence_hash
                              ↓
                        evidence_trail × 3 (conversation + scoring + manifest)
                              ↓
                        审计: verify() → 取出 data_json → 重算 SHA-256 → 比对
```

### Phase 2 待开始
- 向量化历史测试结果 (evidence_memory.py)
- 金标准 RAG 注入 LLM Judge Prompt
- 长短期记忆分离 (Redis + 火山 KB)

---
## 2026-07-16 全终端变更汇总

### 1. /phase3-api 双API前缀发现 (Terminal A — Claude)
前端JS逆向(247KB, P0="/phase3-api")发现真实API前缀。此前`/api/`仅为兼容层(Quiz/Agent/Profile全404/500)。
**文件**: `src/platform_client.py` 重构 → 双前缀自动登录 + 智能路由 + 9新方法
**验证**: 云端100% health | 5 Phase Quiz全可用(45题) | Agent Chat正常

### 2. 平台交互功能全量测评体系 (Terminal A)
| 新模块 | 功能 | 结果 |
|--------|------|------|
| `src/platform_interaction_evaluator.py` (700行) | 13功能全量测试 | 88%健康度, 11 working, 0 P0阻塞 |
| `src/quiz_evaluator.py` (240行) | 5 Phase Quiz专项 | 45题, 结构完整率100% |
| `tests/test_quiz.py` | 独立Quiz脚本 | 30/30 PASS |

**13功能状态**: ✅Quiz(启+提) ✅Agent对话 ✅Step进度/Next ✅画像(6维) ✅知识搜索 ✅事件 ✅Agent反馈 ✅资源 ✅学习模式 ⚠️视频 ❌证据上传(406)

### 3. 前端产品化清理 (Terminal B)
`scripts/cleanup_ui.py` + `cleanup_ui2.py`: 移除v3.4版本号/I18N双语/EN切换 → `frontend/index.html` 纯中文SPA

### 4. 后端API扩展 (Terminal C)
`backend/api/calibration.py`(18 methods): 人类vsLLM校准(Cohen's κ/Spearman ρ/MAE)
`backend/api/tests.py`(9 methods): /run /cancel /health /sessions + Watchdog
`backend/api/kb.py` + `backend/services/kb_service.py`: 4 Phase火山KB管理
`backend/middleware/rate_limit.py`(13 methods): 滑动窗口限流

### 5. Agent注册表 + Dashboard + CLI (Terminals D/E/F)
`src/agents/agent_registry.py`: 8 Agent(4 HiAgent Phase + Platform + WebTest + Mock)
`dashboard/app.py`(928行): FastAPI+WebSocket监控面板
`cli/explore_agent.py`: Playwright页面探查

### 6. 前端新页面 (Terminal G)
`frontend/js/pages/web-eval.js` / `web_evaluator.js`: Web评测+6维结果
`frontend/js/pages/dashboard.js`: 🔴 平台健康度面板(13功能+Quiz覆盖)

### 7. 测试与配置 (Terminal H)
新增: `test_quiz.py` `test_ab_comparator.py` `test_watchdog.py` `calibration.py` `regression_benchmark.py`
配置: `eval_profiles.yaml` `test_config.yaml` `l1_thresholds.yaml` `l3_judge_prompts/`

### 8. 白皮书 v3.6 (Terminal A)
`docs/whitepaper_v3.6.md`(794行): v3.3→v3.6迭代, 新增第五部分(平台交互测评)+第六部分(完整测评流程/人类操作指南/底层L1L2L3伪代码/产业级交付标准)

### P0/P1 进度
P0: 10/12✅ | P1: 11/~16✅ | 平台交互: 12/13✅ | Quiz: 5 Phase×45题✅

### 部署
```bash
wsl bash -c "cd /home/jennifer07/agent_eval && rsync -rlptz --exclude .git --exclude venv \
  --exclude .env -e 'ssh -i ~/.ssh/volc_ecs_rsa' ./ root@124.174.108.70:/opt/agent_eval/ && \
  ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 'systemctl restart agent-eval'"
```

---
# 🚀 分布式节点实时进度看板 (本地/云端双轨版)
> 规则：后台每5秒心跳 | 状态标签: [ENV:LOCAL] [ENV:DEPLOY] [ENV:CLOUD] | 严禁覆盖
