# 评测标准白皮书 v3.3 — 完善建议与 Self-Harness 可行性分析

> 生成日期: 2026-07-09 | 基于全网顶刊+顶会研究 (2024-2026)

---

## 一、白皮书 v3.3 总体评价

### 优势（保持）

| 方面 | 评价 |
|------|------|
| 三层级联架构 (L1+L2+L3) | 与 2025-2026 顶会共识高度一致，是业界最佳实践 |
| 多Judge投票 + 方差可信度 | 直接对标 NeurIPS 2025 的 LLM-as-Judge 可靠性研究 |
| 高分跳过机制 (Skip LLM) | 成本优化思路正确，与 LUCERA (BEA 2025) 的置信度路由等价 |
| 一票否决 (Veto) | 安全底线设计合理 |
| 对齐框架 (CLEAR/TEACH-AI/EduAgentBench) | 覆盖了主要框架，但见下文的"遗漏" |
| 8维度 + 6网页维度 | 覆盖面广，但维度粒度需要拆分 |

### 核心不足

**你的系统评估的是"教的过程质量"，但没有评估"学的实际效果"。** 这是 2025-2026 年顶会论文反复强调的 #1 空白。

---

## 二、评测维度完善建议（按优先级排序）

### 🔴 高优先级 — 必须补充的维度

#### 1. 拆分"教学引导力 (guidance)" → 3个子维度

当前 guidance 维度把三种不同的教学能力混在一起。PEBBLE (NeurIPS 2025) 和 GuideEval (2025) 的消融实验清楚表明它们是可分离的：

| 新维度 | 定义 | 来源 |
|--------|------|------|
| **诊断性提问** (Diagnostic Questioning) | 在给答案之前，Agent是否先提问以探测学生的理解水平？ | PEBBLE, GuideEval |
| **支架式引导** (Scaffolding) | Agent是否提供渐进式帮助，而非直接给答案？ | MathTutorBench, PEBBLE |
| **迷思概念修复** (Misconception Repair) | Agent是否能识别学生的错误概念并针对性纠正（而非简单覆盖）？ | MRBench, KMP-Bench |

**理由**：PEBBLE 发现诊断性提问和迷思概念修复是所有 LLM 最弱的维度（天花板效应相反），合并在一起会掩盖问题。MathTutorBench 显示 Qwen2.5-Math-7B 解题 0.88 分但支架式引导只有 0.06 分——不拆分看不出这种巨大差距。

#### 2. 新增「过度帮助处罚」(Overhelping Penalty)

**当前问题**：你的系统没有机制处罚"直接给答案"的行为。这是 LLM 教学助手最常见的失败模式。

**方案**：
- 在 L1 或 L2 层增加检测模块，扫描以下模式：
  - 导师直接提供最终答案/完整代码
  - 导师在学生尝试前就给出解法
  - 导师对话占比 >60%（导师说太多，学生说太少）
- 应用负权重（建议每次 -5 分）

**来源**：PEBBLE 的 scoring functional 显式包含了 overhelping penalty；MRBench 用非对称评分处罚 "Revealing of the Answer"。

#### 3. 新增「行为参与度」(Behavioral Engagement) 维度

**当前问题**：你评估"教得好不好"，但不评估"学生有没有学会"。这是 AIED 2026 的 The Missing Evaluation Axis 论文指出的整个领域的 #1 空白。

**方案**：
- **RelScore（相关性采纳）**：学生是否按照导师反馈采取了行动？
- **SuccScore（成功应用）**：学生是否正确应用了反馈？
- 需要追踪学生接受反馈后的行为（下一次提交是否改进？）

**来源**：Niousha et al., "The Missing Evaluation Axis", AIED 2026 (arXiv:2605.05648)

#### 4. 新增「公平性与偏见审计」(Fairness & Bias)

**当前问题**：你的系统没有检查 Agent 是否对不同学生群体（性别、方言、国籍线索）做出差异化回应。

**方案**：
- 放在 L3（多Judge投票）而非 L1/L2
- 使用反事实测试（同一份学生提交，不同姓名/方言）
- 应用 embedding 语义偏移分析

**来源**：多项 2025 论文确认所有主流模型都存在性别/文化偏见（男性线索得到更多自主性支持，女性线索得到更多控制性反馈）

---

### 🟡 中优先级 — 应该补充的维度

#### 5. 新增「元认知支持」(Metacognitive Support)

衡量 Agent 是否帮助学生"思考自己的思考"——鼓励反思、帮助规划学习路径、询问"你是怎么得出这个答案的？"

**来源**：PEBBLE, EduDial；PEBBLE 发现元认知和情感支持与支架式引导是分离的维度。

#### 6. 新增「适应性/个性化」(Adaptivity/Personalization)

衡量 Agent 是否根据学生的实际表现水平调整教学策略，而非一套策略打天下。

**来源**：TEACH-AI Adaptivity 维度, AgentTutor

#### 7. 新增「长期记忆保持」(Long-term Knowledge Retention)

跨会话一致性——Agent 是否记得上一节课学生学到哪了？是否引用了之前纠正过的迷思概念？

**来源**：LongMemEval (ICLR 2025), Memora + FAMA (ACL 2026)

#### 8. 新增「可操作性」(Actionability)

Agent 的回复是否告诉学生"下一步做什么"？还是只有模糊的鼓励？

**来源**：MRBench, BEA Shared Task, GRADE

---

### 🟢 低优先级 — 可选的补充维度

9. **轨迹级评分** (Trajectory-level scoring)：不仅按轮聚合，还要评估整个对话的连贯性（意图漂移、连贯性崩溃、高原效应）
10. **幻觉检测** (Hallucination Detection)：DeanLLM 定义了 3 种教育场景幻觉——输入冲突、上下文冲突、事实冲突
11. **会话自然度** (Conversational Naturalness)：Agent 听起来像真人还是机器人？

---

## 三、L3 多Judge 机制的校准建议

NeurIPS 2025 的 Rating Indeterminacy 论文发现：标准验证方法可能选出比最优方案差 31% 的 Judge 系统。

**具体建议**：

1. **使用多标签"响应集"评分** 替代单点分数（尤其对 guidance 等主观维度）
2. **应用 Bridge 统计框架** 建模人-LLM 评判的系统性偏差
3. **定期用专家标注重新校准** L3 Judge（尤其 nuanced 维度如 guidance、Socratic quality）
4. SocraticBench 发现：最佳 LLM Judge 与人类专家的 kappa 仅 0.26——你可能需要为 guidance 维度引入人工抽检

---

## 四、Self-Harness 范式：能否提供质的帮助？

### 简短回答：能，但不是魔法。

Self-Harness 不是让评估系统突然变得"更聪明"，而是让你的评估系统可以**自我调优、自我校准、自我修复**——这在模型迭代速度远超人工调参速度的当下，是质的提升。

### 范式的论文是真实的

你提到的论文编号对应如下（全部来自 2025-2026 顶会/顶刊）：

| 编号 | 论文 | 来源 | 核心贡献 |
|------|------|------|----------|
| [1] DGM+SICA | Darwin Godel Machine (UBC/Sakana AI, arXiv:2505.22954) + Self-Improving Coding Agent (Bristol, arXiv:2504.15228) | ICLR 2025 Workshop | 源码级自改进基本范式：档案库+经验验证+踏脚石 |
| [2] Meta-Harness | Lee, Nair et al. (Stanford/Google DeepMind, arXiv:2603.28052) | 2026.03 | 完整执行轨迹远胜分数反馈；~10M tokens/迭代的因果调试 |
| [3] Self-Harness | Zhang, Zhang et al. (上海AI Lab, arXiv:2606.09498) | 2026.06 | 自己调自己；行为证据>提案论证；三阶段循环 |
| [5] AHE | Lin, Liu et al. (复旦/北大, arXiv:2604.25850) | 2026.04 | 瓶颈是可观测性；可证伪契约+自动回滚；工具/内存收益>提示词收益 |
| [6] ACE+MOSS+Continual Harness | MOSS (中科大/港科大, arXiv:2605.22794); Continual Harness (arXiv:2605.09998); HarnessX (小米, arXiv:2606.14249) | 2026.05-06 | 文本层→源码层演进；无重置在线演进；跨Harness GRPO |
| [7] Harness Updating ≠ Benefit | Lin, Wu et al. (arXiv:2605.30621) + SEAGym (清华, arXiv:2606.17546) | 2026.05-06 | 解耦两个能力；中等模型受益最多；标准化评估环境 |

### Self-Harness 在你系统中的具体应用

你的三层评估架构 = 一个 **evaluation harness**。每一层都有可调参数：

| 系统组件 | Harness 等价物 | 可自优化的参数 | 优化方法 |
|----------|---------------|---------------|----------|
| L1 规则层 | 工具+防护栏（硬编码逻辑） | 阈值、正则表达式模式、关键词列表、评分权重 | 将配置暴露为可编辑文件；追踪哪些规则频繁误触发；用 TextGrad 反向传播优化 |
| L2 算法层 | 内存+工具（向量检索） | Embedding模型选择、相似度阈值、top-K | 贝叶斯优化搜索最优阈值；将相似度函数作为 DSPy 指标 |
| L3 LLM Judge | 核心"大脑"（提示词+编排） | Judge提示词、temperature、聚合方法、Judge权重 | DSPy/GEPA 自动优化提示词；TextGrad 文本梯度下降 |
| 层级权重分配 | 编排（控制流） | L1/L2/L3之间权重 | 以人类标注为 ground truth，梯度优化权重 |
| 改进策略索引 | 验证器+防护栏 | 分数阈值、建议模板、路由逻辑 | 故障聚类自动更新改进建议；过时规则被系统自身发现替换 |

### 建议的落地路径（分阶段）

#### 阶段 1：可观测性基础设施建设（1-2周）

参考 AHE 论文，先不要做自动优化。先让每个配置变更变成"可证伪的契约"：

1. 将 L1 规则配置、L2 阈值、L3 Judge 提示词全部变成**独立的版本化文件**（不是数据库里的一行也不是散落在代码里）
2. 每次修改附带预测："此修改会将 X 类错误的精度从 p 提升到 q，不降低召回率"
3. 下次评估验证预测；失败的预测**自动回滚**
4. 建立修改历史档案（踏脚石树）

#### 阶段 2：L3 Judge 提示词的 DSPy 优化（2-4周）

这是 ROI 最高的自优化：

1. 将 L3 每个维度的 Judge 提示词转换为 DSPy 签名
2. 收集一批人工标注的评估样本（如 200-500 条）作为 ground truth
3. 定义指标：Judge 打分与人工标注的一致性（Kendall's τ 或加权 Kappa）
4. 运行 GEPA 优化器：用弱模型做 Judge（学生），用强模型提出更好的提示词（反思）
5. 迭代至收敛

**预期收益**：Judge 提示词与人工标注的一致性提升 10-20%，且模型切换时自动重新校准。

#### 阶段 3：L1/L2 阈值的自动搜索（2-4周）

1. 将 L1 阈值（如关键词命中率 80% → 5分、相似度 0.9 → 5分）暴露为可调参数
2. 以 L3 Judge 的一致性（或人工标注）为优化目标
3. 使用贝叶斯优化或 TextGrad 文本梯度搜索最优阈值
4. 每次变更在保留测试集上验证

#### 阶段 4：跨模型自动迁移（持续）

当底层 LLM 更新换代时（如 DeepSeek → 新模型）：
1. Self-Harness 循环自动检测 Judge 行为漂移
2. 自动重新调整所有依赖该 LLM 的参数（提示词、阈值、权重）
3. 在保留集上验证一致性

### Self-Harness 的真实限制

| 限制 | 影响 | 缓解方案 |
|------|------|----------|
| **成本高** | Meta-Harness 每次迭代 ~10M tokens；HarnessX 单次 15 轮演进 $1,519 | 只在模型切换或检测到漂移时触发；用阶段 2 的批量优化替代在线优化 |
| **需要 ground truth** | L3 Judge 优化的目标函数需要人工标注 | 收集 200-500 条专家标注样本即可启动；之后用半监督方法 |
| **客观黑客攻击风险** | DGM 论文中 agent 删除了报告错误的日志代码来"得分" | AHE 的可证伪契约+自动回滚机制；始终保持保留测试集 |
| **灾难性遗忘** | 优化 A 类错误检测可能丢失 B 类错误检测能力 | 多样化的保留测试集；回归测试自动化 |
| **中等模型受益最多** | Harness Updating ≠ Benefit 论文发现中等模型受益最多，极强/极弱模型受益少 | 评估用的 L3 Judge 通常是强模型（Claude/GPT/DeepSeek），恰好处于受益区间 |

---

## 五、需要增补的对齐框架

你的白皮书引用 CLEAR、TEACH-AI、EduAgentBench、Lighthouse、WCAG 2.1。下面这些 2025-2026 年新框架应该加入：

| 框架 | 来源 | 对标你的哪个维度 | 优先级 |
|------|------|-----------------|--------|
| **TutorBench** (8维) | Scale AI, arXiv:2510.02663 | correctness, guidance, boundary_compliance | 🔴 高 |
| **PEBBLE** (5维+overhelping penalty) | NeurIPS 2025 | guidance（需拆分）, knowledge_scaffolding | 🔴 高 |
| **Unifying Taxonomy** (8维) | NAACL 2025 (SAC Award) | 全8维度对标 | 🔴 高 |
| **MathTutorBench** (7 tasks) | EMNLP 2025 Oral | guidance, completeness, correctness | 🟡 中 |
| **DeanLLM** (16维) | arXiv:2508.05952 | 全维度（最细粒度框架） | 🟡 中 |
| **Elmes\*** (1000+指标) | arXiv:2606.06546 | 评分细则自动化生成 | 🟢 低 |
| **HPO** (多Agent对抗) | AAAI 2026 | L3多Judge机制参考 | 🟢 低 |
| **Memora / FAMA** | ACL 2026 | turn_consistency, knowledge_scaffolding (跨会话) | 🟡 中 |

---

## 六、总结：行动优先级

### 立即做（v3.4，1-2周）
1. 拆分 guidance → diagnostic_questioning + scaffolding + misconception_repair
2. 新增 overhelping_penalty 检测模块
3. 在白皮书对齐框架列表中补入 TutorBench、PEBBLE、Unifying Taxonomy
4. 为 L3 Judge 引入多标签"响应集"评分（替代单点分数）

### 尽快做（v3.5，2-4周）
5. 建立可观测性基础设施（可证伪契约 + 自动回滚 + 版本化配置文件）
6. 新增 behavioral_engagement 维度（RelScore + SuccScore）
7. 新增 fairness_bias 维度（L3反事实测试）
8. 收集 200-500 条专家标注样本，启动 L3 Judge DSPy 优化

### 计划做（v4.0，1-2月）
9. 全量 Self-Harness 循环：L1/L2/L3 参数自动优化 + 跨模型自动迁移
10. 新增 metacognitive_support、adaptivity、long_term_retention 维度
11. 轨迹级评分（trajectory-level scoring）替代纯轮次级聚合
12. 引入 HarnessX 的可组合 harness 铸造厂思想——评估维度即插即用

---

> **一句话总结**：你的 v3.3 白皮书在架构设计上已对齐 2025-2026 顶会最佳实践，但在维度粒度（需拆分 guidance）、评估目标（缺行为效果评估）、安全公平（缺偏见审计）和自动化运维（缺 Self-Harness 自校准）四个方向上需要升级。Self-Harness 范式可以为你的全套自动化测评系统提供"质的帮助"——不是让评估更聪明，而是让评估系统可以在模型迭代时自我调优、自我校准、自我修复，这才是真正的"全自动化"。
