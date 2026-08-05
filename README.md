# 🤖 AI Agent 全自动化测评系统 v3.6

[![Tests](https://github.com/DiqingTang25/eval/actions/workflows/tests.yml/badge.svg)](https://github.com/DiqingTang25/eval/actions/workflows/tests.yml)

面向 **AI 教学助手 Agent** 的全自动化测评平台。通过浏览器操控被测 Agent → LLM 生成测试问题 → 多轮追问 → 10 维度评分（三层级联：L1 规则 + L2 语义 + L3 LLM Judge 投票）→ 边界合规检测 → 证据链封存 → 可视化报告。

**被测目标**: 西交利物浦大学 AI 教学助手（HiAgent 平台 / 实训教学平台）

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────┐
│  前端 SPA (Vanilla JS + Chart.js)                        │
│  ┌──────────┬──────────┬──────────┬──────────┬────────┐ │
│  │Dashboard │TestRunner│ Reports  │Calibration│Platform│ │
│  │          │          │          │           │ Health │ │
│  └──────────┴──────────┴──────────┴───────────┴────────┘ │
│  i18n: 505键 zh/en 双语 · WebSocket 实时推送              │
├──────────────────────────────────────────────────────────┤
│  FastAPI 后端 (Python 3.12)                               │
│  ┌──────────┬──────────┬──────────┬────────────────────┐ │
│  │ REST API │WebSocket │ Health   │ i18n 自适应补齐     │ │
│  │ 8 模块   │ 实时日志 │ 后台刷新  │ 启动扫描+文件监控   │ │
│  └──────────┴──────────┴──────────┴────────────────────┘ │
│  中间件: CORS · Basic Auth · Rate Limit · Metrics        │
├──────────────────────────────────────────────────────────┤
│  核心评测引擎 (src/)                                       │
│  ┌─────────────┬──────────────┬────────────────────────┐ │
│  │ 三层级联评分 │ 边界检测      │ 对抗性测试              │ │
│  │ L1规则 30%  │ 关键词+KB检索 │ 跨模型族 Judge 投票     │ │
│  │ L2语义 30%  │ 一票否决机制  │ CV 置信度量化           │ │
│  │ L3 LLM 40%  │ 合规分级      │ 需人工复核标记          │ │
│  └─────────────┴──────────────┴────────────────────────┘ │
│  Agent: Platform API · HiAgent · WebTest(Playwright)     │
│  证据链: SHA-256 封存 · 三层记忆(Redis+KB+MySQL)          │
├──────────────────────────────────────────────────────────┤
│  数据层: SQLite(开发) / MySQL RDS(生产) / Redis(缓存)     │
└──────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 本地开发

```bash
# 1. 克隆
git clone https://github.com/DiqingTang25/eval.git
cd eval

# 2. 环境
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. 配置
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY (DeepSeek)

# 4. 启动
python main.py                    # CLI 测评
python main.py dashboard          # Web 面板 → http://localhost:8000
uvicorn backend.main:app --reload # 纯 API 模式
```

### Docker

```bash
docker build -t agent_eval .
docker run -p 8000:8000 --env-file .env agent_eval
```

---

## 📊 测评流程

```
用户选择配置 (巡检/全平台/深度/自定义)
  │
  ▼
问题生成 (黄金QA库 → 分层抽样 或 LLM 生成)
  │
  ▼
逐场景执行 (最多22个教学Day × N轮对话)
  ├── 1. 浏览器操控被测Agent (Playwright)
  ├── 2. 发送问题 → 获取Agent回复
  ├── 3. LLM 生成追问 (最多N轮)
  ├── 4. 边界检测 (课程边界合规)
  └── 5. 多Judge评分 (并行, 跨模型族投票)
  │
  ▼
WebSocket 实时推送到前端 (每轮对话/每条日志)
  │
  ▼
报告生成 (JSON + MD + HTML)
  ├── 维度得分 + 综合分 + 置信度CV
  ├── 证据链 SHA-256 封存
  ├── Judge 共识分析
  └── 改进方案
```

---

## 🎯 10 维度评分体系

| 维度 | 层级 | 说明 |
|------|------|------|
| **正确性** | L1+L3 | 答案事实准确，无幻觉 |
| **相关性** | L2+L3 | 回答紧扣问题，不跑题 |
| **完整性** | L2+L3 | 覆盖关键知识点 |
| **引导力** | L3 | 启发思考，不直接给答案 |
| **追问质量** | L3 | 追问是否切中要害 |
| **边界合规** | L1+L2 | 拒绝回答超出课程范围的问题 |
| **过度帮助** | L1 | 检测是否直接给答案/代码 |
| **轮次一致性** | L3 | 多轮对话前后不矛盾 |
| **知识递进** | L3 | 由浅入深，循序渐进 |
| **安全性** | L1 | 拒绝有害/敏感内容 |

---

## 📁 项目结构

```
agent_eval/
├── backend/               # FastAPI 后端
│   ├── main.py           # 应用入口 + SPA fallback + 健康检查
│   ├── api/              # REST API (8模块)
│   ├── services/         # 业务逻辑层
│   ├── models/           # ORM 模型 (SQLAlchemy)
│   ├── middleware/        # CORS/Auth/RateLimit/Metrics
│   └── ws/               # WebSocket 管理
├── frontend/              # 单页应用
│   ├── index.html        # 主页面
│   ├── js/pages/         # ES模块页面组件
│   ├── js/i18n.js        # 双语系统
│   ├── locales/          # zh.json / en.json
│   └── css/              # 样式
├── src/                   # 核心评测引擎
│   ├── test_runner.py    # 流水线编排器
│   ├── evaluator.py      # 多维度评分
│   ├── boundary_detector.py  # 边界检测
│   ├── reporter*.py      # 报告生成 (JSON/MD/HTML)
│   ├── agents/           # Agent 实现
│   ├── rules/            # 规则引擎 (L1)
│   └── evidence_memory.py # 三层记忆系统
├── config/                # YAML 配置
├── tests/                 # 测试套件
├── deploy/                # 部署脚本 + Nginx + Docker
├── scripts/               # 运维工具
└── reports/               # 生成的报告
```

---

## 🔧 配置

核心配置在 `config/test_config.yaml`:

```yaml
test:
  agent_id: "platform"      # 被测目标
  num_questions: 3          # 场景数
  max_turns: 3              # 每场景最大轮次
  n_judges: 3               # Judge 数量
  rule_weight: 0.30         # L1 规则权重
  llm_weight: 0.70          # L3 LLM 权重
  use_boundary: true        # 边界检测
  use_rag: true             # RAG 增强
```

测评模式 (`config/eval_profiles.yaml`):
- **🔍 巡检** (~5min): 每 Phase 抽 1 Day
- **📋 全平台** (~18min): 22 Days + Quiz 验证
- **🔬 深度** (~30min): 双模式 + 逐 Step

---

## 🌐 部署

目标: 火山引擎 ECS `124.174.108.70`

```bash
# 一键同步 + 重启
bash deploy/sync.sh

# 或手动
rsync -rlptz --delete --exclude .git --exclude venv \
  -e 'ssh -i ~/.ssh/volc_ecs_rsa' \
  ./ root@124.174.108.70:/opt/agent_eval/
ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 'systemctl restart agent-eval'
```

详见 [deploy/README.md](deploy/README.md)

---

## 🧪 测试

```bash
# 全量
pytest tests/ -v

# 分层
python tests/test_rule_engine.py      # L1 规则引擎
python tests/calibration.py --self-test  # 校准自测
python tests/regression_benchmark.py  --check  # 回归基准
```

GitHub Actions CI: `syntax → unit → content → prd_check → llm`

---

## 📝 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn |
| 浏览器自动化 | Playwright |
| LLM | DeepSeek (OpenAI 兼容 API) |
| 多模型 Judge | XJTLU AI Gateway (GLM-5.2 + Doubao) |
| 向量/Embedding | XJTLU Embedding API (替代 BGE-M3) |
| 知识库 | 火山引擎 KB (4 Phase collections) |
| 数据库 | SQLite (开发) / MySQL RDS (生产) |
| 缓存 | Redis |
| 前端 | Vanilla JS + Chart.js |
| 部署 | Docker + systemd + Nginx |

---

## 📄 许可证

Internal use — 西交利物浦大学 AI Agent 测评项目
