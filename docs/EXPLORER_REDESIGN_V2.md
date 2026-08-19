# Platform Explorer 设计修订 v2.0

> 基于 2026-08-12 全量直接探索实践的发现
> 方法: Playwright + API拦截 + DOM捕获 + 多轮职业/兴趣组合探索
> 覆盖: 22门课程 / 33个API / 14门Agent测试

---

## 一、原探索器 vs 实际平台 — 差距清单

| # | 原设计假设 | 实际发现 | 影响 |
|---|-----------|---------|------|
| 1 | L2结构推断通过API响应JSON自动提取 | API `graph-source` 只返回课程标题+ID+lessonId，**模块信息在track API中** | L2必须调用多个API才能还原完整结构 |
| 2 | 课程内容在API响应中 | ✅ 正确 — `GET /v1/courses/{id}` 返回完整步骤(guide/detailed/standard三模式) | API直调即可获取，不需要爬DOM |
| 3 | Agent是无状态的独立服务 | Agent **必须有浏览器上下文**，直接API调用100%返回500 | Agent测试必须走浏览器 |
| 4 | Agent响应是JSON HTTP | Agent响应是 **SSE流式传输**，HTTP body为空 | 需WebSocket/SSE拦截或DOM捕获 |
| 5 | URL可以直接导航到课程 | SPA不支持URL路由 — 必须通过点击UI元素导航 | 爬虫必须用click-based navigation |
| 6 | 22门课 = 22个Phase | 22门课分属**4个教学模块**，不是Phase | Schema结构需重构 |
| 7 | `page.route()` 可以捕获所有API | ✅ 正确，但Agent的SSE流式响应是例外 | SSE需要特殊处理 |
| 8 | 登录一次即可访问全部内容 | ✅ 正确 — JWT有效期足够 | - |

## 二、已验证的API端点完整清单

```
认证层:
  POST /personalized-secure-api/auth/login          → {accessToken, user}

数据层:
  GET  /personalized-secure-api/v1/graph-source     → {courses, requiredPrerequisites}
  GET  /personalized-secure-api/v1/careers          → {categories, competencies}
  GET  /personalized-secure-api/v1/courses/{id}     → {course, content}   (22门课, 110步骤)

学习路径:
  POST /personalized-secure-api/v1/tracks           → 创建个性化路径
  GET  /personalized-secure-api/v1/tracks/{id}      → 路径详情(模块/目标/边)
  GET  /personalized-secure-api/v1/progress/{id}    → 学习进度

Agent:
  POST /personalized-secure-api/v1/agent/sessions     → 创建会话 (需浏览器上下文!)
  POST /personalized-secure-api/v1/agent/sessions/{id}/messages → 发送消息 (SSE响应)

节点进度:
  GET  /personalized-secure-api/v1/tracks/{id}/nodes/{nodeId}/progress

埋点:
  POST /personalized-secure-api/v1/events
  POST /personalized-secure-api/v1/activity-events/batch
```

## 三、探索器需要修改的地方

### 3.1 l1_capture.py — 添加SSE拦截
```python
# 当前: page.on("response") 只能捕获HTTP JSON
# 需要: 添加 page.route() 拦截SSE流
def on_route(route):
    if "agent/sessions" in route.request.url and "/messages" in route.request.url:
        # 捕获SSE流式响应
        response = route.fetch()
        body = response.text()
        # 解析 "data: {...}" 格式
        ...
```

### 3.2 l2_structure.py — 多API结构合并
```python
# 当前: 只从 graph-source 提取
# 需要: graph-source + track API + course API 三者合并
# graph-source → 课程ID/标题/lessonId
# track API → 模块归属(moduleId)
# course API → 步骤详情
```

### 3.3 explorer.py — Agent处理
```python
# 当前: 没有Agent处理逻辑
# 需要: 
#   1. 浏览器进入课程页面
#   2. 点击"学习伙伴"按钮
#   3. 检查 textarea disabled状态
#   4. 发送问题
#   5. 等待SSE响应或DOM变化
#   6. 从DOM提取Agent回复
```

### 3.4 导航策略 — 必须用click-based
```python
# 当前: 尝试URL导航
# 需要: 
#   登录 → 跳过职业 → 选择兴趣 → 连接 → 生成路径 → 点击课程卡片
#   这是进入课程的唯一方式
```

## 四、课程Agent响应模式

通过对14门课的实际测试，Agent行为模式如下:

| 特征 | 值 |
|------|-----|
| Agent名称 | "学习伙伴" (constant) |
| Agent ID | default_learning_agent |
| 上下文感知 | 根据当前课程自动调整 |
| 响应格式 | Markdown |
| 响应速度 | 1-18分钟 (取决于课程复杂度) |
| 激活条件 | 必须进入具体课程后 |
| 离线时状态 | textarea disabled, placeholder="进入一项学习内容后即可提问" |

**各模块Agent回答特点**:
- embedded_perception: 提供硬件清单、接线指导、GitHub资源链接
- ai_agent: 提供模型评测策略、工程链路说明
- embodied_projects: 提供交互设计、控制逻辑
- ai_manufacturing: 提供CAD/CAM流程、加工参数

## 五、建议的探索器执行流程 (修订版)

```
Phase 0: 认证
  1. POST /auth/login → 获取JWT
  2. 验证token有效性

Phase 1: 数据采集 (API直调, 无浏览器)
  3. GET /v1/graph-source → 课程清单
  4. GET /v1/careers → 职业/能力数据
  5. FOR each course: GET /v1/courses/{id} → 步骤详情
  
Phase 2: 学习路径探索 (浏览器)
  6. 对每组兴趣: 浏览器导航 → 生成学习路径
  7. 调用 track API 获取模块归属
  8. 合并数据 → 完整课程-模块-步骤树

Phase 3: Agent测试 (浏览器, 可选)
  9. 进入每门课程
  10. 打开Agent → 发送标准问题 → 等待响应 → DOM捕获
  11. 记录响应特征(长度/主题/资源引用)

Phase 4: Schema生成
  12. 汇总 Phase 0-3 所有数据
  13. 生成 platform_schema.yaml + platform_profile.json
```

## 六、已确认的平台局限性

1. **只有4个教学模块, 22门课程** — 第5个职业分类("软件/产品")无对应课程
2. **Agent是单例系统** — 不是每门课独立的Agent, 而是同一Agent根据课程上下文回答
3. **课程内容托管在外部GitHub** — 平台只做个性化编排, 实际教材在GitHub仓库
4. **无传统Quiz系统** — Quiz功能存在但通过API, 不在当前探索范围内
