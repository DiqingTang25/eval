# Platform Explorer (PX) — 架构文档 v0.1

> **借鉴**: Unbrowse(2026.04) + WALT(ICLR 2026) + Recon-Act(2025) + Vespasian(2025) +
>          Explorbot(2025) + A2A隐藏API论文(2026.01) + KaBOOM(2025-26) +
>          Periscope MCP(2025-26) + balage-core(2025)

## 核心原则

探索器作为**独立前置模块**运行，通过 `platform_schema.yaml` 与现有测评系统对接。

```
探索器 (独立)              现有测评 (保留+迭代)
─────────────              ────────────────────
src/platform_probe/        src/evaluator.py (10维,不动)
    ↓                     src/test_runner.py (小改)
platform_schema.yaml ────→ src/schema_adapter.py (新增)
                           src/platform_client.py (+from_schema)
                           backend/ + frontend/ (不动)
```

## 五层流水线

| 层 | 职责 | 借鉴 | 状态 |
|----|------|------|------|
| L0 | 认证检测与登录 | balage-core + Periscope MCP | ✅ 已实现 |
| L1 | 流量捕获+BFS遍历 | Vespasian + Unbrowse | ✅ 已实现 |
| L2 | 教学结构推断 | WALT + KaBOOM + Explorbot | ⚠️ 简化版 |
| L3 | API分类+LLM枚举 | Vespasian + A2A论文 | ✅ 已实现 |
| L4 | Schema生成+脱敏+验证 | Vespasian + WALT | ✅ 已实现 |

## 快速开始

```bash
# 探索目标平台
python -m src.platform_probe --url https://target-platform.com --headed

# 用schema驱动现有测评
# 1. 修改 config/test_config.yaml: schema_driven: true
# 2. python -m src.persona_tester --mode smoke
```

## 文件结构

```
src/platform_probe/
├── __init__.py          # 空
├── __main__.py          # CLI: python -m src.platform_probe --url <URL>
├── explorer.py          # PlatformExplorer 主协调器
├── models.py            # 所有 dataclass
├── confidence.py        # 6信号分类器 + Step类型分类
├── l0_auth.py           # AuthDetector + AuthHandler + SessionManager
├── l1_capture.py        # TrafficInterceptor + BFS + PageSnapshotter
├── l2_structure.py      # TeachingStructureInferrer (Phase1简化版)
├── l3_classify.py       # APIClassifier + StepTypeClassifier
├── l4_schema.py         # SchemaGenerator + Redactor + SchemaValidator
└── prompts/             # LLM Prompt 模板 (Phase2)

src/schema_adapter.py    # SchemaAdapter: schema → 现有系统接口
config/explorer_config.yaml
docs/INTEGRATION_POINTS.md
docs/PHASE1_IMPLEMENTATION.md
```

## 与白皮书 v3.6 的关系

白皮书定义的 10维度测评体系 **完全保留**:
- Part 1-4: 不动
- Part 5 (平台交互测评): 从 schema 动态读取功能清单
- Part 6 (完整测评流程): 新增 Step 0 (平台探索)
- Part 7 (改进策略): 新增 schema 驱动的自动改进
