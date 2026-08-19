# 🤖 双AI并行分工方案 — Platform Explorer

> 基于 `docs/SYNC_EXPLORER_GAP_ANALYSIS.md` 的完整差距分析
> 两个AI独立工作，互不冲突，共享 `docs/` 下的同步文档

---

## 分工原则

```
AI Agent A: 数据采集层          AI Agent B: 智能分析层 + 后端修复
══════════════════              ══════════════════
L0 (认证) + L1 (流量/JS逆向)      L2 (结构) + L3 (分类/LLM) + L4 (Schema)
新文件: l1_js_analyzer.py        新文件: l3_fuzzer.py, l2_vision.py
                                 后端Bug修复 (13个) + 前端完善
```

**互不冲突**: A改 `l0_auth.py, l1_capture.py`; B改 `l2_structure.py, l3_classify.py, l4_schema.py, explorer.py`
**共享**: `models.py` (A先加, B可读), `docs/SYNC_EXPLORER_GAP_ANALYSIS.md` (真相来源)

---

## AI Agent A: 数据采集层

### 负责文件
| 文件 | 当前状态 | 目标 |
|------|---------|------|
| `l0_auth.py` | ✅ 4路径认证 | +balage-core集成 +WAF对抗 |
| `l1_capture.py` | ⚠️ 响应体broken | **P0修复** + WS拦截 |
| `l1_js_analyzer.py` | ❌ 不存在 | **NEW: JS Bundle逆向** |
| `models.py` | ✅ 基础模型 | +JS/WS相关dataclass |

### P0任务 (阻塞性 — 先做)

**1. 响应体捕获修复** (`l1_capture.py`)
- 目标: `page.route()` + `route.fetch()` 替代 `page.on("response")`
- 当前bug: fetch/XHR响应体拿不到，`route.fetch()` 超时
- 调试方向: 检查Playwright版本兼容性(1.61.0)，尝试仅对API URL做route拦截
- 验收: capture.json中 `response_sample` 不为空

**2. JS Bundle下载与解析** (`l1_js_analyzer.py` 新文件)
```python
class JSBundleAnalyzer:
    def download_scripts(self, page) -> list[str]: ...
    def extract_api_paths(self, js_content: str) -> list[str]: ...
    def try_sourcemap(self, js_url: str) -> dict | None: ...
```
- 下载所有 `<script src="...">` 
- 正则提取: `["'/](api/[^"'\s]+)`, `["'/](/v\d/[^"'\s]+)`
- 尝试下载 `.map` 文件还原源码
- 验收: 从平台JS中提取到至少3个之前未发现的API路径

### P1任务 (核心能力)

**3. WebSocket拦截** (`l1_capture.py`)
- 监听 `page.on("websocket")` 
- 记录WS URL + 收发消息
- 验收: 捕获到至少1个WS连接

**4. Bug修复**
- #1: 清理 `models.py:88` 重复 `@dataclass`
- #2: 删除 `l1_capture.py:375-451` 死代码
- #3: `max_depth/max_pages` 截断加warning日志

### P2任务 (扩展)

**5. balage-core集成** (`l0_auth.py`)
- 安装 `npm install balage-core`
- 或直接用Python实现F1=0.93等效的ML分类
- 区分: 登录表单 / 搜索框 / 注册表单

### 不碰的文件
- ❌ `l2_structure.py`, `l3_classify.py`, `l4_schema.py` (B负责)
- ❌ `explorer.py` (B负责，但B会读取A新增的capture数据)
- ❌ `backend/`, `frontend/` (B负责)

---

## AI Agent B: 智能分析层 + 全栈修复

### 负责文件
| 文件 | 当前状态 | 目标 |
|------|---------|------|
| `l3_classify.py` | ⚠️ LLMEnum空壳 | **P1 LLM枚举实现** |
| `l2_structure.py` | ⚠️ 仅Phase级 | +VLM +KaBOOM |
| `l4_schema.py` | ✅ 基础生成 | +OpenAPI +验证增强 |
| `explorer.py` | ✅ 流水线 | +新步骤集成 |
| `backend/api/calibration.py` | 🔴 前后端断裂 | **P1 4处契约修复** |
| `frontend/js/app.js` | ⚠️ | View/DL Schema完善 |
| `l3_fuzzer.py` | ❌ 不存在 | **NEW** |
| `l2_vision.py` | ❌ 不存在 | **NEW** |

### P1任务 (核心能力)

**1. LLM端点枚举实现** (`l3_classify.py LLMEnumerator.enumerate()`)
```python
def enumerate(self, known_endpoints, js_bundle_content=""):
    # 1. 筛选 gray_zone 端点 (conf 0.50-0.70)
    # 2. 构建Prompt: 已知端点 + JS路由片段
    # 3. 调用LLM (DeepSeek/Haiku) → 推断隐藏端点
    # 4. GET/OPTIONS试探验证
    # 5. 返回验证通过的端点
```
- 创建 `prompts/api_enumeration.txt` (A2A论文风格Prompt)
- 验收: 在测试平台上发现至少1个新API端点

**2. 参数Fuzzing基础版** (`l3_fuzzer.py` 新文件)
- URL参数篡改 (id=123→124, 0, -1, "admin")
- 重放并比较响应状态码/长度
- 验收: 检测到至少1个参数化端点

**3. 后端校准系统修复** (4处契约不匹配)
- #5: `calSubmit` → 对齐请求体格式
- #6: `calLoad` → 支持 `limit` + `unscored_only` 参数
- #7: `calStats` → 对齐返回结构
- #8: `calGenBtn` → 使用 `count` 参数

### P2任务 (扩展)

**4. VLM截图理解** (`l2_vision.py` 新文件)
- 页面区块截图 → GPT-4o/Qwen-VL识别
- 输出: 区域类型 (导航/内容/广告) + 文本内容

**5. KaBOOM语义选择器** (`l2_structure.py`)
- Shadow DOM穿透 (查找 `shadowRoot`)
- 语义定位替代CSS选择器

### P3任务

**6. Bug修复**
- #4: `l4_schema.py` 硬编码 auth_conf → 使用L0真实置信度
- #9: `tests.py` 可变默认参数
- #12: `settings.py` 添加认证检查
- #13: 创建 `prompts/api_enumeration.txt` 等空文件

**7. OpenAPI 3.0生成** (`l4_schema.py`)
- 在现有 platform_schema.yaml 基础上生成标准OpenAPI格式

**8. 前端完善**
- View Schema: 嵌入显示 (已完成)
- Download Schema: blob下载 (已完成)
- Schema指示器联动
- 探索历史: View/Download按钮

### 不碰的文件
- ❌ `l0_auth.py`, `l1_capture.py` (A负责)
- ❌ 新文件 `l1_js_analyzer.py` (A负责)

---

## 共享约定

1. **`models.py` 修改**: A先加JS/WS相关字段，提交后B可读
2. **`explorer.py` 修改**: B负责集成新步骤，A新增的捕获数据通过 `CaptureResult` 传递
3. **沟通**: 通过 `docs/` 下的 `.md` 文件同步进展
4. **不破坏MVP**: 任何改动不能破坏现有端到端流程 (探索→生成schema)
5. **测试**: 每个P0/P1任务完成后在云端运行一次完整探索验证

---

## 两AI的起点文档

| AI | 必读文档 |
|----|---------|
| A | `SYNC_EXPLORER_GAP_ANALYSIS.md` §二(L0/L1) + §七(Bug #1-3) |
| B | `SYNC_EXPLORER_GAP_ANALYSIS.md` §二(L2/L3/L4) + §七(Bug #4-13) |
| Both | `PHASE1_IMPLEMENTATION.md` (了解已实现内容) |
