# v3.4 交接摘要 — 评分透明化 + 动态测试问题

> 2026-07-09 · 供另一终端 Claude 同步 · 平台 http://124.174.108.70 (不用代理/7897)

## 🆕 本轮增量 (2026-07-09 晚 · 运维+清理)

### A. 云服务改用 systemd 托管(开机自启+崩溃自愈)
- 服务文件 `/etc/systemd/system/agent-eval.service`,`enable`+`active`。
- 运维:`systemctl restart agent-eval`(加载新代码) / `journalctl -u agent-eval -f`(日志) / `/var/log/agent_eval.log`。
- **旧的 nohup 手动启动方式作废**,服务器开机即自动在线。

### B. 彻底移除 Vercel(被测目标统一为 http://124.174.108.70)
- 删除:`src/agents/vercel_agent.py`、`src/pages/`(vercel DOM 页面对象)、`tests/{test_agent,manual_test_agent,diagnose,test_pages}.py`、`scripts/{explore_vercel,vercel_probe}.py`、服务器根目录孤立 `auto_test.py`。
- 注册表 `agent_registry.py` 只剩 **platform / web_test / mock**,默认 `platform`。
- `config/test_config.yaml`: `agent_id: platform`、`share_url: http://124.174.108.70`(原默认是 vercel — 曾导致"Agent 未注册")。
- 前端(index.html + 死代码 JS + dashboard/app.py)选项统一为「HiAgent API测试 / 网站测试(Playwright)」。
- 「网站测试」逻辑 `src/agents/web_test_agent.py` 已指向 `PLATFORM_URL`,内联选择器,不依赖已删的 page objects。

### C. Embedding 改为云端 API(不再本地跑 torch)
- `src/metrics.py` 的 `EmbeddingSimilarity` 从本地 `SentenceTransformer`(~2GB torch)改为 **硅基流动 SiliconFlow bge-m3**(OpenAI 兼容,免费),余弦相似度用 numpy。
- 环境变量(.env):`SILICONFLOW_API_KEY`(**待填** → https://siliconflow.cn 注册)、`SILICONFLOW_BASE_URL`(默认 `https://api.siliconflow.cn/v1`)、`EMBEDDING_MODEL`(默认 `BAAI/bge-m3`)。
- **优雅降级**:缺 key 或 API 运行时失败(网络/额度/鉴权)→ 自动跳过语义相似度维度,**不再崩溃**(`evaluator.py` 实例化处 + `evaluate()` compute 处双重 try/except)。
- 填入 key 后 `config/test_config.yaml` 已 `use_embedding: true`,下次评测自动启用。

### D. 部署方式(本地=源,rsync 推送到服务器)
- 本地曾比服务器新很多(evaluator 等 v3.4 代码服务器缺失),本轮已 **全量 rsync 同步** 到 `/opt/agent_eval`。
- 命令(WSL 内):`rsync -rlptz --exclude .git --exclude venv --exclude .venv_wsl --exclude .env --exclude data --exclude logs --exclude reports --exclude __pycache__ -e "ssh -i ~/.ssh/volc_ecs_rsa" ./ root@124.174.108.70:/opt/agent_eval/` → 再 `systemctl restart agent-eval`。
- **切记**:`.env`/`data`/`venv` 不同步(含密钥/数据/环境);删除文件 rsync 不带 `--delete`,需在服务器手动 `rm`。

---

## 本轮做了什么(两件事)

### 1. 总分重构 + 评分全透明(修掉"只用4维"缺陷)
- **旧**: `overall = 0.30×规则分 + 0.70×avg(correctness,relevancy,completeness,guidance)` — 漏了5维。
- **新**: `overall = Σ(维度分 × 重要性权重)`,10维教学质量导向权重,缺失维度自动重归一化。旧值存 `overall_legacy`。
- 权重(config/dimension_weights.yaml → `importance`): correctness .18 / guidance .17 / overhelping .14 / completeness .11 / boundary .10 / relevancy .09 / fairness_bias .06 / knowledge_scaffolding .06 / followup .05 / turn_consistency .04
- **fairness_bias = 第10维**: 单次对话不评,矩阵层 `_compute_fairness()` 做反事实(同课时跨画像回答给LLM打分)后回填并重算总分。
- evaluate() 返回值新增: `breakdown[dim]`(l1/l2/l3/权重/贡献/置信度)、`l1_modules`、`overhelping_detail`、`guidance_sub`、`judge_reasons`、`importance_weights`、`overall_legacy`。

### 2. 动态测试问题(30%规则 + 70%LLM)
- 固定5画像(P1-P5),但**每轮问题不再写死**: 30%规则定意图+硬约束(必覆盖 概念/追问/卡住/挑战/索要代码/越界),70% DeepSeek 按详细画像+场景+历史生成,失败回退写死。
- 越界题从 `OOS_POOL` 固定池取(保证真越界)。

## 改了哪些文件
| 文件 | 变更 |
|------|------|
| `config/dimension_weights.yaml` | 新增 `importance` 段(10维和为1) |
| `src/evaluator.py` | `IMPORTANCE_WEIGHTS`常量 + `_weighted_overall()`/`_effective_importance()`; `_aggregate_three_layer` 建 breakdown+暴露全子分数; guidance子维度prompt |
| `src/persona_question_generator.py` | **新增** — 动态问题生成器 |
| `src/persona_tester.py` | PERSONAS加`profile`+每轮`constraint`; `dynamic`开关; `_compute_fairness()`/`_build_matrix()`; finalize传`extra`+最终总分 |
| `src/reporter.py` | generate_report加`extra`参数; dims加overhelping/fairness_bias |
| `src/html_reporter.py` | render_agent_eval重写: Chart.js雷达图+能力矩阵热力图+总分计算过程+overhelping专项+guidance三子维度+公平性表+Judge评语 |
| `src/metrics.py` | 🆕 `EmbeddingSimilarity` 改云端 API(硅基流动 bge-m3),删本地 torch 依赖 |
| `src/agents/{agent_registry,__init__,web_test_agent}.py` | 🆕 移除 vercel,只留 platform/web_test/mock |
| `config/test_config.yaml` | 🆕 默认 agent_id=platform, use_embedding=true, share_url=平台 |

## 怎么跑(venv 在 WSL)
```bash
wsl -d Ubuntu-24.04 -- bash -lc "cd /home/jennifer07/agent_eval && source venv/bin/activate && \
  python3 -m src.persona_tester --mode standard --turns 7 --interval 5 --dynamic"
# 模式: smoke(P1×课时4) | standard(3画像×4课时) | deep(5×4) | custom --personas P1,P4 --lessons 4
# --static 回退写死问题; --interval 平台QPS限流间隔秒
```
输出: `reports/report_<ts>.{json,md,html}`(HTML为多模态自包含报告)。

## 依赖与坑
- LLM: OpenAI SDK 调 DeepSeek(`OPENAI_API_KEY`/`OPENAI_BASE_URL`,.env)。
- Embedding: 硅基流动 bge-m3(`SILICONFLOW_API_KEY`,.env,**待填**);缺则自动降级,不再需要本地 torch。
- 平台: `src/platform_client.py`(login/get_lessons/chat),**有QPS限流**已内置节流+退避。
- WSL venv 有 openai/requests;系统 python3 无。所有命令走 `wsl -d Ubuntu-24.04 ... source venv/bin/activate`。
- 云服务器: systemd 托管(`agent-eval.service`),改代码后 `systemctl restart agent-eval` 生效。

## 实测结论(平台Agent真实短板)
- 回答模板化 → guidance≈1.5(引导弱);overhelping中等;boundary≈4.0(不越界)。
- fairness_bias≈2.0: 对零基础/进阶学生给几乎相同模板回答,缺针对性 → 系统性不公平。
- 动态生成显著优于写死: P4能问到 PWM定时器中断/DMA/RTOS优先级,探到平台能力边界。

## 待办(P2起)
- P2: Harness阶段2 — DSPy/GEPA优化L3 Judge(需先攒200-500条人工标注)。
- P3: Playwright测视频/代码编辑器UI。
