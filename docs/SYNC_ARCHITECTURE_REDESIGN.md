# 🏗️ 探索器架构根本缺陷 — 诊断与重设计方案

> **时间**: 2026-08-05  
> **问题**: 探索22 Phase成功，但0 Lesson/0 Step — 不是小bug，是架构性缺陷  
> **患者**: 人工验证目标平台有大量Step，探索器完全没发现

---

## 一、为什么0 Lesson/0 Step — 根本原因

### 当前探索器实际做了什么

```
L0 登录 → 等待页面渲染
L1 BFS → 遍历 <a href> 链接 (深度限制2层/10页)
        → 从不点击 Phase/Course 卡片进入课程
        → 从不触发 Lesson/Step 页面的API请求
L1.5 → 下载JS文件，正则提取URL字符串
L1.6 → 尝试重放API请求 (需要JWT，但JWT提取失败)
L2   → API驱动解析 (期待API响应中有Phase/Lesson/Step)
L3   → 分类
L4   → 生成Schema
```

### 22个Phase是怎么来的？

**不是通过探索课程结构**，而是碰巧 `careers` API 返回了22个 competency 对象，L2 把它们当成了 Phase。

### 为什么0 Lesson/0 Step？

**因为 graph-source API 的响应体从未被捕获。**

链式失败：
1. `TrafficInterceptor` 用 `page.on("response")` 不捕获响应体
2. `_capture_api_data` 需要JWT才能重放API → JWT提取失败 → 返回 `{"jwt":""}`
3. L1.55浏览器fetch (我刚加的) 用了 `page.evaluate(fetch())` → 因为 `verbose=False` 看不到输出，无法确认是否成功
4. L2 `StructureAPIParser` 的 `extract_structure()` 遍历 `capture.routes`，只处理 `response_sample is not None` 的route
5. graph-source 的 `response_sample` 是 None → 被跳过
6. 只有 careers API 有 `response_sample` → 解析出22个Phase
7. Lesson/Step层次的数据在 graph-source 里，parser根本没看到

---

## 二、更深层问题 — 探索策略根本错误

当前策略是 **被动观察**（passive observation）：监听流量，解析响应。

对现代教学平台的正确策略应该是 **主动交互**（active exploration）：

```
正确做法:
  首页 → 识别所有"卡片"(Phase入口) 
      → 点击第一个卡片 → 进入Phase详情页
      → 识别Lesson列表 → 点击第一个Lesson 
      → 进入Lesson详情页 → 观察Step结构
      → 对每个Step类型分类

当前做法:
  首页 → BFS收集链接 → 不做交互 → 等API自己暴露结构
```

### 具体缺失的能力

| 需要的 | 当前 | 差距 |
|--------|------|------|
| 点击卡片进入课程 | ❌ BFS只跟链接 | 🔴 核心缺失 |
| 识别页面状态变化 | ❌ 无状态追踪 | 🔴 核心缺失 |
| 递归深入探索 | ❌ 深度硬限制为2 | 🔴 |
| 页面DOM结构理解 | ❌ 无VLM | 🟡 |
| API响应体捕获 | ❌ JWT提取失败 | 🔴 |
| 探索状态持久化 | ❌ 无记忆 | 🟡 |

---

## 三、架构重设计方案

### 新架构: L0 → L1(主动交互) → L2(多源融合) → L3/L4

#### L1 重设计: 分层交互探索

```
L1a: 首页探索
  - 截图首页 → VLM识别"卡片"/"入口"元素
  - 生成交互候选列表 [{selector, text, type: "phase_card"}]

L1b: Phase层探索
  - 逐个点击Phase卡片
  - 观察URL变化 + DOM变化 + 新API请求
  - 截图Phase页面 → VLM识别Lesson列表
  - 记录: {phase_id, phase_name, lesson_list}

L1c: Lesson层探索  
  - 点击Lesson进入
  - 观察URL变化 + 新API请求
  - 识别Step列表 (侧边栏/序号/进度条)
  - 记录: {lesson_id, lesson_name, step_list}

L1d: Step类型分类
  - 点击每个Step
  - 截图 → VLM识别类型 (video/quiz/coding/reading)
  - 提取交互元素 (视频播放器/代码编辑器/选择题)
```

#### L2 增强: 多源融合

```
数据源1: API响应 (graph-source API — 获取完整Course/Module/Step树)
数据源2: DOM观察 (页面标题/URL模式/面包屑)
数据源3: VLM理解 (截图→语义区域→Step类型)
数据源4: 交互行为 (点击了什么→得到了什么)

融合策略: API > VLM > DOM > 规则推断
```

### 需要的资源

| 资源 | 用途 | 状态 |
|------|------|------|
| GPT-4o VLM | 页面截图理解、元素识别、Step分类 | ✅ 已有Key |
| Qwen3-VL | 备用VLM | ✅ 已有Key |
| 页面截图存储 | 保存探索证据 | 本地文件系统即可 |
| 探索状态记忆 | 避免重复点击、回溯 | JSON文件/内存 |
| API Key (DeepSeek) | LLM枚举隐藏端点 | ✅ 已有 |

不需要额外对象存储或知识库。核心瓶颈是**探索器没有主动交互的代码**。

---

## 四、分工方案

### Agent A: 数据采集层大修 (主动交互)

```
A-1 🔴 页面交互引擎 (新文件 l1_interactor.py)
   - 点击元素 → 等待变化 → 检测URL/DOM/API变化
   - 截图 + 保存状态
   - 递归深入探索 (深度可配置)

A-2 🔴 响应体捕获修复 (l1_capture.py)
   - 修复JWT提取: 从浏览器localStorage/cookie直接读
   - 确保graph-source API响应体被捕获

A-3 🟡 交互候选生成 (l1_capture.py或新文件)
   - DOM扫描 → 找到所有可点击卡片/链接
   - 分类: phase_card / lesson_item / step_item / nav_link
```

### Agent B (我): 分析层增强 (多源融合)

```
B-1 🔴 L2增强 — 多源融合引擎 (l2_structure.py)
   - API数据 + DOM观察 + VLM理解 → 统一的TeachingStructure
   - 处理graph-source的嵌套响应结构

B-2 🔴 L1.5增强 — VLM辅助探索 (l2_vision.py 集成到探索流程)
   - 截图→GPT-4o识别"这是课程卡片" "这是Lesson列表" "这是Step内容区"
   - 输出可操作的交互指令

B-3 🟡 L4增强 (l4_schema.py)
   - Schema中包含完整的Phase→Lesson→Step树
   - 每个Step标注类型 + 置信度 + 证据来源
```

---

## 五、第一优先级的MVP改动

不要贪多。先做最核心的一个改动：**让探索器点击Phase卡片，进入课程内部**。

改动量最小但收益最大的方案：

### B-1a: 在explorer.py中，L1之后增加交互探索步骤

```python
# L1.X: 交互探索Phase卡片
for card_selector in ["[class*='career-card']", "[class*='course-card']"]:
    cards = page.locator(card_selector).all()
    for card in cards[:5]:  # 只探索前5个Phase
        card.click()
        time.sleep(3)
        # 观察变化
        new_url = page.url
        new_title = page.title()
        # 截图 → VLM理解
        # 提取可交互元素 (Lesson入口)
        # 记录到capture.pages
        page.go_back()
```

### A-1a: 修复JWT提取

```python
# 从浏览器直接获取token (不需要截获auth/login)
token = page.evaluate("() => localStorage.getItem('accessToken')")
```

---

## 六、验收标准

```
✅ Phase: ≥22 (当前22)
✅ Lesson: ≥50 (当前0)  
✅ Step: ≥100 (当前0)
✅ API: ≥6 (当前4)
✅ 每个Phase下有关联的Lesson
✅ 每个Lesson下有关联的Step
✅ 整体置信度 ≥ 0.75
```
