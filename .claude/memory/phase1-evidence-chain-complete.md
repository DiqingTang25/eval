---
name: phase1-evidence-chain-complete
description: Phase 1 证据链地基已全部完成，纯 MySQL 方案，准备进入 Phase 2
metadata:
  type: project
---

## Phase 1 完成状态 (2026-07-22)

### 决策
原计划 TOS 对象存储 → 改为 **纯 MySQL 存储**（零额外费用）。SHA-256 指纹是证据链核心，存储介质不影响可信性。

### 核心新增
- `src/evidence_hasher.py` — SHA-256 计算 + store_evidence() + verify() 审计
- `src/async_queue.py` — Redis Streams 异步队列（Redis 不可用时降级同步）
- `backend/models/evidence_trail.py` — 证据追踪表（data_json LONGTEXT 存原始 JSON）

### 数据库变更
- eval_scores: evidence_hash, evidence_path, merkle_root, chain_tx_hash
- evidence_trail: 新建表，15 字段含 data_json
- 索引修复: test_sessions(agent_id, profile), test_scenarios(qa_pair_id), conversation_turns(turn_index)

### 验证
- 本地测试: 12/12 PASS
- 云端: migration 0004+0005 已执行, health=ok
- 同步文档: docs/phase1_evidence_chain_20260722.md

### 云端
- 服务器: root@124.174.108.70:/opt/agent_eval/
- 数据库: mysql877b303b0151.rds.ivolces.com / agent_eval / agent_eval / AgentEval2026!
- 服务: systemctl restart agent-eval

### 下一阶段
Phase 2: 向量化历史测试 + 金标准 RAG + 长短期记忆分离
开始条件: 新窗口说"开始 Phase 2"
