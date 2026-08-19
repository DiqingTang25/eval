# Agent B Session 5 — LLM Step 提取全链路验证

> **日期**: 2026-08-06
> **里程碑**: LLM (DeepSeek) 成功从云端教学平台页面提取 steps

---

## ✅ 已验证：LLM Step 提取端到端有效

```
云端测试流程:
1. Playwright 登录 → ✅ 
2. 发现 30 个 career cards (button.ci-shell-career-card) → ✅
3. 点击 "嵌入式系统工程师" → ✅ 进入 career 选择页
4. 页面文本包含 "步骤 1 选择未来职业" → ✅
5. DeepSeek LLM 提取 2 steps: → ✅
   - 选择未来职业 [selection]
   - 在原平台选择兴趣与课程 [selection]
```

**LLM API**: DeepSeek (deepseek-chat), ~1s 响应, 0 元成本

---

## ⚠️ 当前限制

### Steps 在 2 层导航之后
```
首页 → [点career card] → Career选择页 → [点"开始学习"] → 课程Lesson页 (教学steps在这里)
         ✅ 已验证               ❌ 未实现
```

当前 L1.8 只做了第一层点击（career card），提取到的 "步骤" 是 career 选择流程的步骤，不是教学 steps。需要再加一层点击进入实际课程。

### 探索速度
- BFS + SPA 探索: 180s（`_explore_spa_fast` 做了 3 层卡片点击，每层最多 8 张卡）
- L1.8 LLM 提取: ~3s per course（点击 + 等待 + LLM API）

### 架构建议
```
BFS (快速, 只收集URL) → L0-L4 (当前)
                        → L1.8 LLM Step 发现 (点击 career → 进入 lesson → LLM提取)
```

---

## 📊 当前状态

| 指标 | 值 |
|------|-----|
| Phases | 27 (graph-source + careers) |
| Lessons | 30 (careers competencies) |
| Steps (API) | 0 (API不含step数据) |
| Steps (LLM) | ~2 per course (需进入课程页) |
| Response capture | 96/96 routes ✅ |
| Security node | ✅ |
| Confidence | 73% |

---

## 🔑 LLM 模型清单

| 模型 | Provider | 状态 | 用途 |
|------|----------|------|------|
| DeepSeek V3 | OPENAI_API_KEY → api.deepseek.com | ✅ 在线 | 文本分析/Step提取 |
| GPT-4o | XJTLU_GPT4O_API_KEY → XJTLU Gateway | ✅ 在线 | VLM截图分析 |
| Qwen3-VL-8B | XJTLU_QWEN3VL_API_KEY | ❌ 未配置 | VLM备用 |
| Doubao Seed 2.1 | XJTLU_JUDGE_DOUBAO_API_KEY | ✅ 在线 | VLM备用/多Judge |

---

## 📁 新增文件

- `src/platform_probe/l1_8_llm_explorer.py` — LLM/VLM step 提取
- `src/platform_probe/l1_7_step_discovery.py` — DOM step 发现（慢，备用）
- `tests/test_llm_step_extract.py` — LLM 提取测试

---

*Agent B — 2026-08-06*
