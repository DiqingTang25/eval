# Phase 1 证据链地基 — 全终端同步文档

> 会话日期: 2026-07-22 | 操作终端: Claude | 分支: main | 服务器: 124.174.108.70

---

## 零、决策背景

原始方案需要 **TOS 对象存储**（额外付费），经讨论决定改为 **纯 MySQL 存储**。

**效果不打折**：证据链的核心是 SHA-256 指纹，不是存储介质。MySQL 原生 LONGTEXT（最大4GB）完全够用，且额外支持 SQL JOIN 查询，比 TOS 更灵活。

---

## 一、快速定位（其他终端必读）

### 1.1 如果你在改前端
**本次会话未触碰以下目录，你的工作不受影响：**
- `frontend/` — 零改动
- `dashboard/` — 零改动
- `backend/api/` — 零改动
- `backend/services/` — 零改动
- `config/` — 零改动

### 1.2 如果你在改后端 Python 代码
**以下文件发生了变更，合并时注意：**

| 文件 | 操作 | 冲突风险 |
|------|------|---------|
| `backend/models/eval_score.py` | ✏️ 证据字段改名 | 🔴 如有本地修改需手动合并 |
| `backend/models/evidence_trail.py` | ✏️ 重写整文件 | 🟡 新文件，低风险 |
| `backend/models/test_session.py` | ✏️ 加 3 个索引 | 🟢 仅新增 index=True |
| `backend/models/__init__.py` | ✏️ +1 行导出 | 🟢 低风险 |
| `src/db_recorder.py` | ✏️ 重写 _stamp_evidence | 🔴 如有本地修改需手动合并 |
| `src/async_queue.py` | ✏️ 重写 _process_message | 🟡 新文件改动 |
| `requirements.txt` | ✏️ 删 boto3 | 🟢 低风险 |
| `tests/test_phase1_evidence.py` | ✏️ 重写 | 🟡 测试文件 |

### 1.3 如果你在改数据库
**已执行两次 migration（0004→0005），云端 MySQL 结构已更新。**

---

## 二、新增文件（5个）

### 2.1 `src/evidence_hasher.py` — 证据哈希核心
```
EvidenceHasher
├── sha256_hex(data) → str          # SHA-256 计算
├── sha256_file(path) → (hash,size) # 文件哈希
├── hash_conversation(conv,score)   # 场景级复合指纹
├── hash_artifact(json) → str       # 文件级指纹
├── store_evidence(db,...) → str    # 直接写 MySQL（3条 evidence_trail）
└── verify(db, eval_score_id) → dict # 审计校验
```
**用法示例：**
```python
from src.evidence_hasher import EvidenceHasher
h = EvidenceHasher()
fingerprint = h.store_evidence(db, session_id, score_id, idx, conv_json, score_json)
# 审计验证
result = h.verify(db, score_id)  # → {"match": True, "tampered": []}
```

### 2.2 `src/async_queue.py` — Redis Streams 异步队列
```
EvidenceQueue
├── enqueue(...) → msg_id           # 入队（Redis不可用时降级同步）
├── consume_one() → bool            # 消费一条
├── consume_loop()                  # 持续消费
└── reclaim_pending() → int        # 回收超时消息
```
**消息消费逻辑**：队列 → `EvidenceHasher.store_evidence()` → 直接写 MySQL

### 2.3 `backend/models/evidence_trail.py` — 证据追踪表 ORM

| 字段 | 类型 | 说明 |
|------|------|------|
| id | CHAR(36) PK | UUID |
| session_id | VARCHAR(64) | 冗余，方便按 Session 聚合 |
| eval_score_id | CHAR(36) FK | 关联 eval_scores |
| artifact_type | VARCHAR(32) | conversation / scoring / hash_list |
| artifact_path | VARCHAR(512) | 逻辑路径 |
| sha256 | CHAR(64) | **不可篡改指纹（核心）** |
| file_size | BIGINT | 字节数 |
| content_type | VARCHAR(64) | application/json |
| data_json | LONGTEXT | **原始证据 JSON（MySQL 直存）** |
| storage_tier | VARCHAR(16) | hot / warm / cold |
| worm_locked | BOOLEAN | 应用层 WORM 锁 |
| metadata_json | JSON | 扩展元数据 |
| created_at / updated_at | TIMESTAMP | 自动 |

### 2.4 `backend/alembic/versions/0004_evidence_chain.py`
DDL：添加证据字段 + 新建 evidence_trail 表 + 修复 5 个索引缺口

### 2.5 `backend/alembic/versions/0005_mysql_evidence_store.py`
DDL：字段重命名（去 TOS）+ 新增 data_json LONGTEXT + 删除 4 个 TOS 字段

---

## 三、修改文件（5个）

### 3.1 `backend/models/eval_score.py`
```diff
+ evidence_hash:  CHAR(64)     # SHA-256 场景级指纹
+ evidence_path:  VARCHAR(512) # 逻辑路径
+ merkle_root:    CHAR(64)     # Merkle Tree Root（Phase 4 用）
+ chain_tx_hash:  VARCHAR(128) # 区块链交易哈希（Phase 4 用）
- evidence_tos_key              # 已删除
- evidence_tos_url              # 已删除
```

### 3.2 `backend/models/test_session.py`
```diff
+ session_id:  index=True   # 已有 UNIQUE，加显式索引
+ agent_id:    index=True   # 🆕 按 Agent 查历史不再全表扫描
+ profile:     index=True   # 🆕 按画像筛选不再全表扫描
  (test_scenarios)
+ qa_pair_id:  index=True   # 🆕 FK 列加索引
  (conversation_turns)
+ turn_index:  index=True   # 🆕 按轮次排序加速
```

### 3.3 `src/db_recorder.py`
`_stamp_evidence()` 方法重写：
- **之前**：只算 SHA-256 → 异步入队到 Redis → worker 调 TOS
- **现在**：算 SHA-256 → 调 `EvidenceHasher.store_evidence()` → 直接写 MySQL（3 条 evidence_trail）

### 3.4 `src/async_queue.py`
- `_process_message()` 重写：去掉 TOS 上传逻辑，改为调用 `EvidenceHasher.store_evidence()`
- `_update_db()` 删除（逻辑合并到 `store_evidence`）
- Docstring 更新

### 3.5 `requirements.txt`
```diff
- boto3>=1.34.0    # 不再需要（不用 TOS S3 协议）
```

---

## 四、数据库变更摘要（可直接在控制台查看）

### 4.1 eval_scores 表变化
```sql
-- 去 MySQL 控制台执行可验证:
SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'eval_scores'
  AND COLUMN_NAME IN ('evidence_hash','evidence_path','merkle_root','chain_tx_hash');
```
应返回 4 行。`evidence_tos_key` 和 `evidence_tos_url` 已不存在。

### 4.2 evidence_trail 表
```sql
DESC evidence_trail;
-- 应包含 data_json(LONGTEXT) 和 artifact_path
-- 不应包含 tos_key, tos_bucket, tos_etag, tos_url
```

### 4.3 新增索引
```sql
SHOW INDEX FROM test_sessions WHERE Key_name IN ('idx_sessions_agent', 'idx_sessions_profile');
SHOW INDEX FROM test_scenarios WHERE Key_name = 'idx_scenarios_qa_pair';
SHOW INDEX FROM conversation_turns WHERE Key_name = 'idx_turns_turn_index';
```

---

## 五、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    一次完整评测的证据链                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  评测完成                                                    │
│    ↓                                                        │
│  DBRecorder.record()                                        │
│    ├── 写入 test_sessions / test_scenarios / eval_scores    │
│    ├── _stamp_evidence()                                    │
│    │     ├── EvidenceHasher.hash_conversation() → SHA-256   │
│    │     ├── 更新 eval_scores.evidence_hash                  │
│    │     └── 写入 evidence_trail × 3:                       │
│    │           ├── conversation (完整对话 JSON)               │
│    │           ├── scoring (完整评分 JSON)                   │
│    │           └── hash_list (manifest + 指纹汇总)           │
│    └── EvidenceQueue.enqueue() [可选异步]                     │
│          └── Worker → EvidenceHasher.store_evidence()        │
│                                                             │
│  审计时                                                      │
│    ↓                                                        │
│  EvidenceHasher.verify(db, eval_score_id)                   │
│    ├── 从 evidence_trail 取出 data_json                      │
│    ├── 重新计算 SHA-256                                       │
│    ├── 比对 → match / tampered                               │
│    └── 返回完整审计报告                                       │
│                                                             │
│  篡改检测                                                     │
│    ↓                                                        │
│  任何证据 JSON 的字节级改动 → SHA-256 不匹配 → 标记 tampered  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、云服务器操作记录

```bash
# 1. 安装依赖（已执行）
/opt/agent_eval/venv/bin/pip install boto3  # 后来不需要了

# 2. 同步代码（已执行）
rsync -rlptz --exclude '.git/' --exclude 'venv/' --exclude '.env' \
  --exclude '__pycache__/' -e 'ssh -i ~/.ssh/volc_ecs_rsa' \
  /home/jennifer07/agent_eval/ root@124.174.108.70:/opt/agent_eval/

# 3. 执行 migration 0004（已执行）
cd /opt/agent_eval
PYTHONPATH=/opt/agent_eval /opt/agent_eval/venv/bin/alembic \
  -c alembic/alembic.ini upgrade head
# → Running upgrade 0003 -> 0004 ✅

# 4. 复制 migration 0005 到 alembic 目录（已执行）
cp backend/alembic/versions/0005_mysql_evidence_store.py \
   alembic/versions/0005_mysql_evidence_store.py

# 5. 执行 migration 0005（已执行）
PYTHONPATH=/opt/agent_eval /opt/agent_eval/venv/bin/alembic \
  -c alembic/alembic.ini upgrade head
# → Running upgrade 0004 -> 0005 ✅

# 6. 重启服务（已执行）
systemctl restart agent-eval
# → Active: active (running) ✅
```

---

## 七、MySQL 连接信息

| 配置项 | 值 |
|--------|-----|
| Host | `mysql877b303b0151.rds.ivolces.com` |
| Port | `3306` |
| User | `agent_eval` |
| Password | `AgentEval2026!` |
| Database | `agent_eval` |

> ⚠️ 本地 `.env` 中 MYSQL_USER 和 MYSQL_PASSWORD 是占位符，如本地要用 MySQL 模式需同步更新。

---

## 八、测试结果

```
$ pytest tests/test_phase1_evidence.py -v
======================== 12 passed in 0.86s =========================

$ pytest tests/test_evaluator.py tests/test_rule_engine.py tests/test_boundary.py -v
======================== 9 passed (no regression) ===================
```

---

## 九、Phase 2 预告（未开始）

- 向量化历史测试结果
- 金标准 RAG 注入 LLM Judge Prompt
- 长短期记忆分离（Redis + 火山 KB）

---

> 📎 同步给其他终端时：重点看**第一节（快速定位）**确认自己的文件是否冲突，以及**第四节（数据库变更）**确认 MySQL 结构变更。
