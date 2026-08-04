# 自主学习平台全流程测评方案 v1.0

> 平台: AI+硬件实训平台 (http://124.174.108.70)
> 生成日期: 2026-07-09
> 基于: 实际 API 探索 + 白皮书 v3.4 9维评分体系

---

## 一、平台结构总览

### 1.1 学习阶段

| 阶段 | Phase ID | 课时 | 内容 |
|------|----------|------|------|
| 测试阶段 | 1 (vod-test) | 3 课时 | 平台导学 / 硬件演示 / 项目提交说明 |
| 主学习阶段 | 2 (phase3) | 6 课时 (Day1-6) | 电子硬件→传感器→边缘AI→超声波→视觉→音频 |

### 1.2 每课时结构

```
课时 N (如 Day 1: 电子硬件入门)
├── 📖 知识库资源 (Markdown → RAG检索)
├── 📹 教学视频 (VOD点播)
├── 📋 步骤任务 (5-6 steps, 逐级递进)
│   ├── Step 1: preparation (准备阶段, ~7-8min)
│   ├── Step 2: preparation / practice
│   ├── Step 3: practice / core (核心练习)
│   ├── Step 4: guided / practice (引导练习)
│   ├── Step 5: challenge (挑战项目, ~15-25min)
│   └── Step 6: challenge (可选)
└── 🤖 AI Agent 对话 (侧边栏, 课程知识库驱动)
```

### 1.3 交互功能点

| 功能 | 类型 | 是否可自动化测试 |
|------|------|:---:|
| **AI Agent 对话** | NLP交互 | ✅ 可 (API: POST /api/agent/chat) |
| **知识库检索** | RAG | ✅ 可 (通过Agent回答验证检索质量) |
| **视频播放** | VOD | ⚠️ 可检查播放URL/加载状态 |
| **代码编辑器** | IDE | ⚠️ 前端组件, 需Playwright截图 |
| **串口监视器** | 硬件通信 | ❌ 需要真实硬件 |
| **步骤完成/解锁** | 状态机 | ⚠️ 前端状态 + 可能后端API |
| **项目提交** | 文件上传 | ✅ 可模拟 |

### 1.4 解锁机制

- 步骤之间: 完成前一步才能进入下一步 (前端状态控制)
- 课时之间: 完成当前课时所有步骤才能解锁下一课时
- 阶段之间: 完成 Phase 1 全部 3 课时 → 解锁 Phase 2

---

## 二、一次完整测试的定义

### "一次完整测评" = 1个学生画像 × 1个学习阶段(Phase) × 全课时 × 每课时全步骤交互

```
一次完整测评流程:

Phase 选择 → 课时1 → Step1 → Step2 → ... → Step N → Agent对话N轮
                         ↓ (解锁)
                      课时2 → Step1 → Step2 → ... → Step N → Agent对话N轮
                         ↓ (解锁)
                      课时3 → ...
                         ↓ (解锁)
                       ... → 课时M → 综合报告
```

### 物理课时 vs 测评课时

| 项目 | 完整物理课时 | 测评抽样方案 |
|------|:----------:|:----------:|
| Phase 1 | 3 课时 | 1 课时 (抽样: 课时1 平台导学) |
| Phase 2 | 6 课时 | 3 课时 (Day1/Day3/Day5 或 Day2/Day4/Day6) |
| **一次完整测评** | **9 课时** | **4 课时 (抽样)** |

> 抽样策略: 每个 Phase 至少覆盖首/中/尾三种课时类型。完整深度测评可跑全部 9 课时。

### 每课时的测评对话轮次

| 交互阶段 | 轮次 | 测试内容 | 对应维度 |
|----------|:--:|---------|----------|
| **Step 开始前** | 1 | 学生:"这个课时要学什么?" | correctness, relevancy, completeness |
| **Step 中遇到问题** | 2-3 | 学生:"GPIO输入输出模式怎么设置?"<br>学生追问:"那INPUT_PULLUP和INPUT_PULLDOWN有什么区别?" | guidance, followup_quality, overhelping |
| **Step 卡住/错误** | 4 | 学生:"我的LED不亮,代码没错啊" | guidance(diagnostic_questioning), completeness |
| **挑战项目阶段** | 5-6 | 学生:"呼吸灯项目怎么做?"<br>学生:"能直接给我完整代码吗?" | overhelping(核心), boundary_compliance |
| **越界测试** | 7 | 学生:"ESP32能做无人机飞控吗?" | boundary_compliance |
| **知识递进** | 8 | 学生:"好的我懂了LED,那传感器呢?" | knowledge_scaffolding, turn_consistency |
| **综合复习** | 9 | 学生:"帮我总结今天学了什么" | completeness, guidance |

**每课时: 5-9 轮 Agent 对话 (推荐 7 轮标准)**

---

## 三、多画像学生测评策略

### 3.1 学生画像定义

| 画像 ID | 类型 | 知识水平 | 学习风格 | 典型行为 | 账号 |
|----------|------|---------|---------|---------|------|
| **P1** | 零基础 | 无编程/硬件经验 | 依赖型 | 频繁求助,需要基础概念解释,容易卡住 | student001 |
| **P2** | 有编程基础 | 会Python但不会硬件 | 探索型 | 自己先试,卡住才问,问题偏深度 | student002 |
| **P3** | 硬件爱好者 | 会Arduino但没学过ESP32 | 对比型 | 用已知概念类比,问差异性问题 | student003 |
| **P4** | 进阶学习者 | 有完整嵌入式经验 | 挑战型 | 跳过基础,直奔项目,问优化问题 | student004 |
| **P5** | 非技术背景 | 零基础+对技术恐惧 | 焦虑型 | 反复确认,需要鼓励,容易放弃 | student005 |

### 3.2 画像 × 课时测试矩阵

```
完整测评矩阵 (5画像 × 4课时):

            课时1(导学)  课时4(Day1)  课时6(Day3)  课时8(Day5)  课时9(Day6)
P1 零基础      ✅          ✅           ✅           ✅           -
P2 有编程      ✅          ✅           ✅           -            ✅
P3 硬件爱好者   ✅          ✅           -            ✅           ✅
P4 进阶        -           ✅           ✅           ✅           ✅
P5 非技术      ✅          ✅           ✅           -            -

✅ = 执行完整7轮Agent对话
-  = 跳过(该画像在该课时表现预期已达天花板)
```

### 3.3 每画像的专用测试话术

**P1 零基础 (student001)**:
```
第1轮: "老师好,我什么都不会,这节课学什么?"
第3轮: "GPIO是什么?INPUT和OUTPUT是什么意思?"
第6轮: "能直接给我完整代码吗?我自己不会写"
第7轮: "ESP32能控制无人机吗?"
```

**P2 有编程基础 (student002)**:
```
第1轮: "我在Python里用过GPIO库,ESP32的GPIO操作有什么不同?"
第3轮: "为什么用pinMode设置INPUT_PULLUP而不是直接读?"
第6轮: "我想用状态机优化这个LED控制,有什么建议?"
第7轮: "ESP32的FreeRTOS和Python的asyncio有什么区别?"
```

**P3 硬件爱好者 (student003)**:
```
第1轮: "Arduino UNO的GPIO是5V,ESP32是3.3V,电平转换怎么处理?"
第3轮: "analogRead在UNO是10位,ESP32是12位,精度差异大吗?"
第6轮: "我用过HC-SR04超声波,课程里的和那个一样吗?"
```

**P4 进阶学习者 (student004)**:
```
第1轮: "跳过基础吧,直接告诉我ESP32的DMA+PWM怎么配置?"
第3轮: "代码里用digitalWrite太慢了,用寄存器操作会不会更好?"
第6轮: "这个呼吸灯太简单,我想做音乐频谱可视化,给个思路"
```

**P5 非技术背景 (student005)**:
```
第1轮: "我怕弄坏硬件,这个安全吗?烧了要赔吗?"
第3轮: "我做错了会不会把电脑烧了?"
第6轮: "我对这些完全不懂,是不是不适合学这个?"
```

---

## 四、测评执行方案

### 4.1 一次完整测评的会话数

| 业务目标 | 会话数 | Agent对话总轮数 | 预计耗时 |
|---------|:-----:|:-------------:|:------:|
| **快速验证** (1画像×1课时) | 1 | 7轮 | ~15min |
| **标准测评** (3画像×4课时) | 12 | 84轮 | ~2h |
| **深度测评** (5画像×4课时) | 20 | 140轮 | ~3-4h |
| **全量测评** (5画像×9课时) | 45 | 315轮 | ~6-8h |

### 4.2 推荐: 标准测评

```
3画像 × 4课时 × 7轮对话 = 84轮Agent测评

画像选择: P1(零基础) + P2(有编程) + P4(进阶)
课时选择: Lesson 4(Day1) + Lesson 6(Day3) + Lesson 8(Day5) + Lesson 1(导学)

覆盖:
  ✅ 所有5种Step类型 (preparation/practice/core/guided/challenge)
  ✅ 3种学生水平 (零基础/中等/进阶)
  ✅ 4种知识领域 (基础硬件/传感器/AI/视觉)
  ✅ 9维度全量评分 (含3个多轮维度)
```

### 4.3 一次会话 = 一次 evaluator.evaluate() 调用

```python
# 伪代码
for persona in [P1, P2, P4]:
    for lesson in [4, 6, 8, 1]:
        session = login(persona.username, persona.password)
        turns = []
        
        for round_num, prompt in persona.prompts[lesson.id]:
            # 发送消息到Agent
            resp = session.post("/api/agent/chat", {
                "lesson_id": lesson.id,
                "message": prompt
            })
            
            turns.append({
                "turn": round_num,
                "question": prompt,
                "response": {
                    "status": "success",
                    "response": resp["answer"],
                    "duration": resp.elapsed
                }
            })
        
        # 调用测评系统
        score = evaluator.evaluate(
            question=persona.prompts[0],  # 初始问题
            agent_answer=format_conversation(turns),
            golden_answer=lesson.golden_answer,
            goal=lesson.goal,
            turns=turns,
            boundary_result=boundary_detector.check(...),
        )
        
        # 生成改进方案
        plan = improvement_engine.propose(score, evidence)
        
        results.append({
            "persona": persona.id,
            "lesson": lesson.id,
            "score": score,
            "plan": plan,
        })
    
# 汇总报告
reporter.generate_report(results, improvement_plan=plan)
```

### 4.4 单次完整测评的输出

```
reports/
├── report_20260709_143000.json       # 原始评分数据
├── report_20260709_143000.md         # Markdown报告
├── report_20260709_143000.html       # HTML可视化报告
└── improvement_plan_20260709.json    # 改进方案
```

---

## 五、特殊考量

### 5.1 解锁机制处理

由于平台有步骤解锁机制,测评时有两种策略:

**策略A (真实模拟)**: 
- 按顺序完成每个Step (发送Step完成请求)
- 等待解锁下一个Step
- 在每个Step中插入Agent对话

**策略B (独立测评)**: 
- 假设所有Step已解锁 (使用已完成全部Step的学生账号)
- 聚焦Agent对话质量,不做Step状态变更
- 适用于纯Agent能力测评

> 推荐: 策略A用于端到端完整测试,策略B用于Agent专项测试。

### 5.2 代码/硬件交互的测评边界

| 可测评 | 不可测评 |
|--------|---------|
| Agent是否正确解释了GPIO概念 | 学生是否真的连对了电路 |
| Agent是否给出了正确的代码结构 | 代码在真实硬件上是否正常运行 |
| Agent是否引导学生排查错误 | 串口监视器的实际输出 |
| Agent是否在引导前泄露了答案 | 硬件是否有物理损坏 |

> 原则: 测评系统评估Agent的教学能力,不评估硬件的物理状态。

### 5.3 画像公平性测试

P1和P4面对同一问题(如"LED不亮怎么办"),Agent的回答应该:
- 内容实质相同(正确的排查步骤)
- 但表述方式/引导深度适应学生水平
- 不应系统性歧视任何画像

通过对比P1和P4在相同问题上的评分差异,可量化评估公平性:
```python
fairness_gap = |score_P1["correctness"] - score_P4["correctness"]|
# 若 gap > 1.0 且非由学生行为差异导致 → 存在偏见
```

---

## 六、与测评系统 v3.4 的对接

### 6.1 维度映射

| 平台交互 | → 测评维度 |
|---------|-----------|
| Agent解释概念的正确性 | correctness |
| Agent是否回答了学生真正的问题 | relevancy |
| Agent是否覆盖了知识库的所有关键点 | completeness |
| Agent是否用Socratic方法引导,先问后答 | guidance (diagnostic + scaffolding) |
| Agent面对追问是否深化而非重复 | followup_quality |
| Agent是否在课程知识边界内回答 | boundary_compliance |
| 多轮间是否有矛盾信息 | turn_consistency |
| 后续轮次知识是否递进 | knowledge_scaffolding |
| Agent是否直接给代码/答案 | overhelping |

### 6.2 新增测试用例生成器

需要在 `src/` 下新增 `src/persona_tester.py`:

```python
class PersonaTester:
    """多画像学生测评执行器"""
    
    PERSONAS = {
        "P1_zero_basis": {...},
        "P2_coding_background": {...},
        "P3_hardware_hobbyist": {...},
        "P4_advanced": {...},
        "P5_non_technical": {...},
    }
    
    def run_standard_eval(self) -> dict:
        """3画像 × 4课时 标准测评"""
        ...
    
    def run_deep_eval(self) -> dict:
        """5画像 × 4课时 深度测评"""
        ...
```
