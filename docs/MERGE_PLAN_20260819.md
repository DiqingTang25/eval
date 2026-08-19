# 合并方案 — 分支 `worktree-agents-20260819` (3276cf2) → main

> 作者: agent5-integration · 2026-08-19 · 供主会话执行
> 基座: 分支 `worktree-chat-explorer-intervention` @3276cf2 (已推送, 未合并 main)
> 实际 worktree 分支: `worktree-agents-20260819` (在 `.claude/worktrees/agents-20260819`)
> 主工作区: `/home/jennifer07/agent_eval` (有大量未提交 WIP, 只读源)

---

## ① 分支 3276cf2 改过的 12 个文件 (已推送, 未合并)

| # | 文件 | 类型 | 内容 |
|---|------|------|------|
| 1 | `backend/api/explorer.py` | 修改 | 3 个 `/api/explorer/chat/*` 端点 |
| 2 | `backend/api/tests.py` | 修改 | `/api/tests/intervention/{respond,pending}` 端点 |
| 3 | `backend/services/explorer_chat.py` | **新增** | 对话式探索器状态机 (394 行) |
| 4 | `backend/services/test_service.py` | 修改 | `ask_user()` 阻塞干预 + 3 卡点 |
| 5 | `docs/DESIGN_CHAT_EXPLORER_EVAL_INTERVENTION.md` | **新增** | 交互重构设计文档 (125 行) |
| 6 | `frontend/index.html` | 修改 | 聊天面板 + 干预弹窗 |
| 7 | `frontend/js/app.js` | 修改 | WS `eval:need_input` + 10s 轮询兜底 |
| 8 | `frontend/locales/en.json` | 修改 | i18n keys |
| 9 | `frontend/locales/zh.json` | 修改 | i18n keys |
| 10 | `src/browser_evaluator.py` | 修改 | 干预 hooks (登录失败/Day 出错/Schema 缺失) |
| 11 | `src/multi_agent/orchestrator.py` | 修改 | 干预编排调用 |
| 12 | `src/platform_probe/api_keys.py` | **新增** | APIKeyRegistry + load_dotenv (175 行) |

## ② 与主工作区 WIP 的冲突清单及逐文件合并决策

> 方向说明: "MAIN" = 主工作区未提交 WIP; 各 agent 已在 worktree 分支上完成移植/合并,
> 分支当前状态即合并目标 — **merge 时预期无文本冲突**, 冲突风险主要在 untracked 文件 (见 §③)。

### A. 分支改动 + MAIN 同时有 WIP (真正需要合并的文件) — 已由对应 agent 合并

| 文件 | MAIN WIP 内容 | 合并结果 (worktree 现状) | 负责 |
|------|--------------|--------------------------|------|
| `backend/api/explorer.py` | /health, /profile/latest, 懒加载 | 已合并 (保留 chat 端点 + MAIN 增强), py_compile PASS | agent1 ✅ |
| `backend/services/explorer_service.py` | QuestionBridge 交互问答桥 | 已移植 (ask_callback 探测签名), py_compile PASS | agent1 ✅ |
| `backend/services/test_service.py` | DIAG 打印 (含 logger NameError 修复) | 已移植 + 审计日志 v2, 冒烟 22/22 PASS | agent2 ✅ |
| `backend/api/tests.py` | 无实质 WIP (行尾差异) | 分支版为准, 端点未动 | agent2 ✅ |
| `frontend/index.html` `js/app.js` `locales/*` | 前端 WIP | 已合并: WIP(08-05/06 Dashboard修复/i18n 645键)为底 + 分支聊天面板/干预弹窗全量移植; Dashboard P0 三处根因已修(catch兜底/Chart重试10次/_profilePolling未声明); chart.umd.min.js 入库; locales 652键双语一致; node check+5 smoke PASS | agent3 ✅ |
| `src/browser_evaluator.py` | MAIN 有修改 | 分支版 + MAIN 差异已核对, 冒烟 PASS | agent2 ✅ |
| `src/multi_agent/orchestrator.py` | MAIN 有修改 | 已移植, 编排器冒烟 5/5 PASS | agent2 ✅ |
| `src/platform_probe/api_keys.py` | MAIN 为旧 untracked 版 | **分支版为准** (agent5 已验证语义一致: 仅行尾差异, 分支版含 load_dotenv) | agent5 ✅ |

### B. MAIN 独有 WIP (分支未动) — agent5 已移植, merge 无冲突

| 文件 | WIP 内容 | 状态 |
|------|---------|------|
| `backend/main.py` | startup 清理残留 running 会话 | 已移植 ✅ py_compile PASS |
| `backend/api/settings.py` | 新增 xjtlu_qwen3vl/xjtlu_gpt4o provider、has_vision、密码脱敏 | 已移植 ✅ |
| `backend/api/calibration.py` | /items 增加 limit/unscored_only、/generate 支持 body | 已移植 ✅ |
| `src/platform_probe/explorer.py` | 六阶段流水线重写 (220→680 行, 含 ask_callback/auth_state_path) | 已移植 ✅ |
| `src/platform_probe/confidence.py` | agent 模式词表扩充、STEP_TYPE_INDICATORS 增强 | 已移植 ✅ |
| `src/platform_probe/l0_auth.py` | 自适应版 (3 模式: 表单/预认证/交互, 含 ask_callback) | 已移植 ✅ |
| `src/platform_probe/l1_capture.py` | `_safe_sample`、双模式拦截 (route.fetch P0 修复)、WS 捕获 | 已移植 ✅ |
| `src/platform_probe/l2_structure.py` | StructureAPIParser (API 驱动结构提取) | 已移植 ✅ |
| `src/platform_probe/l3_classify.py` | page_url、LLMEnumerator 完整实现 | 已移植 ✅ |
| `src/platform_probe/l4_schema.py` | teaching_structure 参数、_build_structure | 已移植 ✅ |
| `src/platform_probe/models.py` | SessionState 默认值、fuzz_findings 字段 | 已移植 ✅ |
| `src/multi_agent/planner.py` | Schema 来源 DIAG 打印、跳过空 schema | 已移植 ✅ |
| `docs/PHASE1_IMPLEMENTATION.md` | 08-05 更新版实现清单 | 已移植 ✅ |

### C. 语义一致无需移植 (行尾/空白差异, 分支版为准)

`src/platform_probe/{__init__,__main__}.py` · `src/multi_agent/{__init__,executor,verifier,reporter,models}.py`
· `src/{coverage_tracker,llm_client,mcp_server,self_healing,visual_assertion}.py`
· `tests/test_{coverage_tracker,mcp_server,multi_agent,self_healing,visual_assertion}.py`
· `config/explorer_config.yaml` · `docs/{ARCHITECTURE_PX,INTEGRATION_POINTS}.md`
· `backend/api/{health,mcp}.py` · `backend/models/exploration_session.py` · `backend/alembic/versions/0008_exploration_sessions.py` · `src/{anomaly_detector,schema_adapter}.py`

### D. MAIN 已删除的文件 (D) — merge 时注意

| 文件 | MAIN 状态 | 建议 |
|------|----------|------|
| `deploy/deploy.sh` `deploy/nginx.conf` | 已删除 (工作树) | ✅ agent4 已在 worktree 同步删除 (被 deploy-systemd.sh/nginx-agent-eval.conf 取代, 08-12 融合决定) — merge 后 main 同样删除 |
| `docker-compose.yml` | 已删除 (工作树) | 保留仓库版; 若确定弃用由主会话后续单独删除 |

### E. 双方均 untracked 的文件 (需随合并 commit, 先在 MAIN 备份)

`src/platform_probe/{deep_explorer,dom_step_discovery,l0_interactive,l1_js_analyzer,l2_vision,l3_fuzzer,step_extractor}.py`
`src/platform_probe/prompts/` · `src/{eval_interactive,question_bridge}.py`
`frontend/js/chart.umd.min.js` (agent3 新增, Chart.js 4.4.1 — 此前仓库缺失导致新部署图表 404)
`deploy/{agent-eval-ci.service,agent-eval-ci.timer,agent-eval.service,deploy-docker.sh,deploy-systemd.sh,nginx-agent-eval.conf,archive/}`
`docs/` 18 份未跟踪文档 (见附录 B) · `tests/` 15 个脚本 (已整理, 见附录 C)

## ③ 建议的合并执行步骤 (主会话执行)

### 前置 (主工作区 /home/jennifer07/agent_eval)

```bash
# 1. 备份全部 WIP (含 untracked) — 双保险: stash + 物理备份
cd /home/jennifer07/agent_eval
git status --short            # 确认与附录 A 清单一致
git stash push -u -m "WIP-backup-20260819"      # -u 包含 untracked
mkdir -p /tmp/wip_backup_20260819 && git stash show -p stash@{0} > /dev/null 2>&1
# 也可 tar 备份: tar czf /tmp/wip_backup_20260819.tar.gz backend src frontend docs tests config deploy docker-compose.yml .env.example README.md

# 2. 回到干净 main 并合并
git fetch origin
git checkout main
git merge worktree-agents-20260819        # 预期干净合并; 若 3276cf2 未含全部 WIP 移植, 用分支最新状态
# merge 前若提示 untracked 文件会被覆盖 → 说明 stash -u 未覆盖全, 手工移走同名文件
```

### 验证点 (merge 后)

```bash
# 3. 代码完整性
python3 -m py_compile backend/main.py backend/api/*.py src/platform_probe/*.py src/multi_agent/*.py
node --check frontend/js/app.js
# 4. 冒烟 (agent4 venv 修复后): 聊天状态机 22/22 + 干预 22/22 + 编排器 5/5 + 凭证解析 8 项
# 5. git status 干净; git log --oneline -3 确认 main 顶端 = 合并 commit
```

### 收尾 (主工作区)

```bash
# 6. untracked 决策文件入库 (docs/tests 决策见附录 B/C)
git add docs/ tests/ src/platform_probe/prompts/ .gitignore(如有输出目录忽略)
# 建议: output/ 已加入 .gitignore (本会话已执行)
# 7. 若需恢复旧 WIP 对照: git stash pop (会与已合并内容冲突, 仅作人工核对, 核对后丢弃)
git push origin main
```

> ⚠️ 重要: merge 前 MAIN 的 untracked 文件 (api_keys.py, deep_explorer.py 等与分支 commit 同名者)
> 必须先备份/移除, 否则 `git merge` 会拒绝 ("untracked working tree files would be overwritten")。
> `git stash -u` 即可解决。

## ④ 合并后建议: push + 部署云端 (概述, 细节以 agent4 结论为准)

1. `git push origin main` 后:
   - 本地 WSL: 用修复后的 venv 重跑全链路冒烟 (T4)
   - rsync 代码到云端: 按 `deploy/sync.sh` (agent4 已审查) 或新的 deploy-systemd.sh
2. 云端: 更新代码 → `systemctl restart agent-eval` (systemd 单元: `deploy/agent-eval.service`, CI 定时器 `agent-eval-ci.timer`)
3. 数据: alembic 迁移已含 `0008_exploration_sessions` (在库中), 如云端库旧则执行 `alembic upgrade head`
4. 验收: 对话式探索 (chat 端点) + 评测卡点干预 (eval:need_input) 端到端, 见设计文档验收清单

---

## 附录 A — 主工作区 WIP 完整清单 (2026-08-19 核实, wip_list.sh 分目录)

```
M  .env.example · README.md · docker-compose.yml(D)
M  backend/main.py · api/{calibration,explorer,settings,tests}.py · services/{explorer_service,test_service}.py
M  deploy/{README.md,sync.sh} · D deploy/{deploy.sh,nginx.conf}
M  docs/PHASE1_IMPLEMENTATION.md
M  frontend/{index.html,js/app.js,locales/en.json,locales/zh.json}
M  src/multi_agent/planner.py · src/browser_evaluator.py
M  src/platform_probe/{explorer,confidence,l0_auth,l1_capture,l2_structure,l3_classify,l4_schema,models}.py
?? deploy/{agent-eval-ci.service,agent-eval-ci.timer,agent-eval.service,deploy-docker.sh,deploy-systemd.sh,nginx-agent-eval.conf,archive/}
?? docs/ 18 份 (见附录 B)
?? src/{eval_interactive.py,question_bridge.py}
?? src/platform_probe/{api_keys,deep_explorer,dom_step_discovery,l0_interactive,l1_js_analyzer,l2_vision,l3_fuzzer,step_extractor}.py · prompts/
?? tests/ 15 个临时脚本 (已整理, 见附录 C)
?? output/ (生成物, 建议 gitignore)
```
注: 实测 MAIN 全部文件为 CRLF 行尾、仓库存 LF (core.autocrlf=true), wip_list 的 "differ" 多为行尾噪音,
以上清单已按语义 diff 清洗。

## 附录 B — docs/ 18 份未跟踪文档决策 (agent5)

**结论: 全部保留入库** (均为设计契约/过程记录, 且 MEMORY 索引引用其中多份; 总大小 ~140KB, 无维护成本)。
按性质分类:

| 分类 | 文件 | 决策 |
|------|------|------|
| 设计/契约 (核心) | `EXPLORER_REDESIGN_V2.md` · `AGENT_A_REQUIREMENTS_FOR_C.md` · `SYNC_EXPLORER_GAP_ANALYSIS.md` · `SYNC_ARCHITECTURE_REDESIGN.md` · `SYNC_ROUND3_P0_BODY_CAPTURE.md` · `SYNC_FRONTEND_DESIGN_REVIEW.md` · `AI_WORK_DIVISION.md` | 保留 |
| 过程同步快照 | `SYNC_AGENT_B_20260805.md` · `SYNC_AGENT_B_ROUND3.md` · `SYNC_AGENT_B_SESSION4/5/6.md` · `SYNC_ROUND2_QUALITY_FIX.md` · `SYNC_ROUND4_AGENT_A_SUMMARY.md` · `SYNC_ROUND5_AGENT_A_SUMMARY.md` · `SESSION_SUMMARY_20260806.md` | 保留 (历史过程记录, 已过期但无害; 可选后续移 docs/archive/) |
| 报告 (HTML) | `PROGRESS_REPORT_20260805.html` · `weekly_report_20260812.html` | 保留 |
| 本会话 | `PROGRESS_AGENTS_20260819.md` (协调进度, 只追加) · `MERGE_PLAN_20260819.md` (本文档) | 保留 |
| 舍弃 | 无 | — |

## 附录 C — tests/ 15 个临时脚本决策 (agent5, 已执行整理)

| 决策 | 脚本 | 理由 |
|------|------|------|
| **保留 tests/ 根** (7) | `test_llm_step_extract.py` · `test_capture_jwt.py` · `test_fetch_eval.py` · `test_jwt_extract.py` · `test_route_fetch.py` · `ws_test.py` · `ws_test_nginx.py` | P0 响应体捕获/JWT/LLM 提取/WS 契约的回归验证脚本, 有复用价值 |
| **移入 tests/archive/** (8, 已移动) | `browser_login_test.py` · `confirm_ac.py` · `diag_test.py` · `final_check.py` · `fix_profile.py` · `quick_test.py` · `review_bc.py` · `run_evo_test.py` | 一次性云端诊断/审查脚本, 硬编码 /opt/agent_eval 路径 |
| 删除 | 无 | archive 保留历史 |

## 附录 D — agent5 移植验证结果

- py_compile: 12 个移植 .py 文件全 PASS; platform_probe 全 18 文件 PASS (PYTHONUTF8=1)
- 修复: `src/platform_probe/l0_interactive.py` L218 中文引号内嵌 ASCII `"` 语法错误 (改为单引号) — 双方工作区原文件均存在此 bug
- 交叉 import: `discover_steps`/`inject_steps_into_structure` (dom_step_discovery) · `DeepExplorer` (deep_explorer) · `extract_steps_deep` (step_extractor) · `run_l3_fuzzer` (l3_fuzzer) · `run_l0_auth`…`run_l4_schema` 入口全部存在
- ask_callback 链路: `explorer.explore(ask_callback=None)` → `run_l0_auth(ask_callback=...)` 签名一致 (agent1 已确认)
- 环境限制: 本机 Windows venv 缺 playwright/yaml/requests → 完整 import 冒烟待 agent4 修好 WSL venv 后重验 (静态编译与入口检查已全过)
- 未归属 untracked 文件 `src/eval_interactive.py` · `src/question_bridge.py` 编译通过, 建议随合并保留
