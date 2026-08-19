# Agent B → Agent A/C 同步文档 (Session 4 — 最终)

> **日期**: 2026-08-05  
> **版本**: Agent B Session 4 (云端诊断 + 根因修复)  
> **关键发现**: graph-source 是扁平结构，steps 不在 API 中

---

## 0. 本轮云端诊断结果

```
✅ 96/96 routes have response_sample  (之前 0/96 — JSON parsing bug fixed)
✅ Schema: security_node=True         (之前缺失)
✅ Confidence: 73%/80%/60%/75%/73%    (之前 0%)
⚠️  Steps: 0                         (根因: API响应无嵌套step数据)
⚠️  duration: 0.0s                   (l4_schema设置0后被explorer覆盖 — 已修复)
⚠️  JWT: 未提取                      (localStorage无标准token key — 已增强匹配)
```

---

## 1. 🔴 根因: graph-source API 没有嵌套 steps

### 真实数据结构
```json
// graph-source (1581B)
{
  "courses": [
    {"id": "blender-automation", "lessonId": 22, "title": "Blender AI 自动化 3D 工作流"},
    {"id": "agent-handoff", "lessonId": 23, "title": "能力模块与 Agent Handoff"},
    ...  // ~20个扁平course对象
  ],
  "requiredPrerequisites": [...]
}

// careers (15301B)
{
  "categories": [{...}, {...}],
  "competencies": [{...}, {...}]  // L2 parser从这里提取30 lessons
}
```

**graph-source 的每个 course 只有 `{id, lessonId, title}`，没有任何嵌套的 modules/steps。**  
**careers 的 competencies 也是扁平对象，没有嵌套 steps。**

### 为什么
平台是 React SPA。Lesson/Step 详情渲染在页面 DOM 中（从 React state），不经过 API 调用。SPA 导航是客户端路由，不触发新 API 请求。

### 修复
- **L2 parser 新增 DOM fallback**: API 找到 phases+lessons 但 0 steps 时，自动从 `PageSnapshot` 中提取 step-like 内容
- Step 提取策略: 页面标题 + interactive_elements + 文本中的编号模式（`Step 1:`, `1. ` 等）
- 当 steps 被分配后，lessons 的 `step_count` 被更新

### 对你（Agent A）的影响
**需要更好的 DOM 采集**:
1. 在 BFS/SPA 探索中，点击 course/lesson 卡片后，对每个课程内页做 PageSnapshot
2. 确保课程内页的 `interactive_elements` 包含 step 进度条、step 按钮等
3. `PageSnapshot.text_content` 应该包含 step 列表文本

---

## 2. 🟡 修复清单

| # | 问题 | 根因 | 修复 | 文件 |
|---|------|------|------|------|
| 1 | response_sample=Null | `json.loads(body)` bytes解析失败 | 改用 `response.text()` → JSON | l1_capture.py |
| 2 | capture.json截断 | `_safe_sample` 500字节太小+返回string | 改为5000字节+返回dict | l1_capture.py |
| 3 | 0 steps | API扁平无嵌套 | DOM fallback提取 | l2_structure.py |
| 4 | security节点缺失 | fuzz为空时不生成 | 始终生成(含`fuzzer_ran`标志) | l4_schema.py |
| 5 | duration=0.0s | l4_schema设0后explorer未覆盖 | `max(0.1, elapsed)` + log | explorer.py |
| 6 | JWT提取失败 | 只匹配含'token'等key | 增加JWT-like值匹配(base64+点号格式) | explorer.py |
| 7 | auth_confidence regex | 只认`confidence=X`格式 | 兼容`conf=`/`confidence:`等 | explorer.py |

---

## 3. 部署

```bash
cd "//wsl.localhost/Ubuntu-24.04/home/jennifer07/agent_eval"
tar czf - --exclude='__pycache__' \
  src/platform_probe/models.py \
  src/platform_probe/confidence.py \
  src/platform_probe/l2_structure.py \
  src/platform_probe/l3_classify.py \
  src/platform_probe/l4_schema.py \
  src/platform_probe/explorer.py \
  src/platform_probe/l1_capture.py \
  | ssh -i ~/.ssh/volc_ecs_rsa root@124.174.108.70 \
  "cd /opt/agent_eval && tar xzf - && systemctl restart agent-eval"
```

---

## 4. Agent C 同步

> Agent C 的前端测评器需要知道: 平台只有 5 个 API 端点，lesson/step 数据在 DOM 中。Schema 的 structure 节点来自 API+DOM 混合提取。如果测评器需要精确的 step 列表，需要从页面 DOM 中抓取，而非依赖 API。

---

*Agent B — 2026-08-05 Session 4*
